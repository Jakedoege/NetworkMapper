"""Bounded, ICMP-only discovery and background status checking on Windows."""
import ipaddress
import socket
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QThread, Signal
from identity import SERVICE_PORTS


def ping_once(ip: str):
    """Return latency in ms or None. A responding address need not be a mapped device."""
    try:
        result = subprocess.run(
            ['ping', '-n', '1', '-w', '700', ip],
            capture_output=True, text=True, errors='replace', timeout=3,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode != 0:
            return None
        # Windows output is localized; even when latency parsing fails, return online.
        match = re.search(r'(?:time|Zeit|temps)\s*([=<])\s*(\d+)\s*ms', result.stdout, re.I)
        if match:
            return float(match.group(2)) if match.group(1) == '=' else 1.0
        return 0.0
    except (OSError, subprocess.TimeoutExpired):
        return None


class ScanWorker(QThread):
    found = Signal(str, object)
    progress = Signal(int, int)
    scan_done = Signal()

    def __init__(self, subnet: str):
        super().__init__()
        self.subnet = subnet

    def run(self):
        hosts = [str(a) for a in ipaddress.ip_network(self.subnet, strict=False).hosts()]
        with ThreadPoolExecutor(max_workers=32) as pool:
            futures = {pool.submit(ping_once, ip): ip for ip in hosts}
            for idx, future in enumerate(as_completed(futures), 1):
                latency = future.result()
                if latency is not None:
                    self.found.emit(futures[future], latency)
                self.progress.emit(idx, len(hosts))
        self.scan_done.emit()


class MonitorWorker(QThread):
    checked = Signal(str, object)

    def __init__(self, ips):
        super().__init__()
        self.ips = list(ips)

    def run(self):
        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = {pool.submit(ping_once, ip): ip for ip in self.ips}
            for future in as_completed(futures):
                self.checked.emit(futures[future], future.result())


def reverse_dns(ip: str):
    """Query an IP's PTR record without blocking the GUI or requiring extra packages.

    nslookup is available on Windows; a short process timeout bounds bad DNS.
    No record does not mean the device is offline.
    """
    try:
        result = subprocess.run(
            ['nslookup', '-timeout=1', '-retry=1', ip],
            capture_output=True, text=True, errors='replace', timeout=4,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        output = result.stdout
        # Windows nslookup PTR results usually contain 'Name: host.example'.
        # Other builds return '<reverse-address> name = host.example'.
        candidates = re.findall(r'(?im)^\s*Name\s*:\s*(\S+)', output)
        candidates += re.findall(r'(?im)\bname\s*=\s*(\S+)', output)
        for candidate in candidates:
            candidate = candidate.strip().rstrip('.')
            if candidate and candidate != ip and not candidate.endswith('in-addr.arpa'):
                return candidate[:253]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ''


def netbios_name(ip: str):
    """Try Windows NetBIOS node status; only hosts advertising NetBIOS respond."""
    try:
        result = subprocess.run(
            ['nbtstat', '-A', ip], capture_output=True, text=True,
            errors='replace', timeout=3,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        # Prefer unique workstation/server names, not group records or MAC addresses.
        for row in result.stdout.splitlines():
            match = re.match(r'^\s*([^<>\s]{1,15})\s+<00>\s+UNIQUE\b', row, re.I)
            if match:
                name = match.group(1).strip()
                if name and name != '__MSBROWSE__':
                    return name
        for row in result.stdout.splitlines():
            match = re.match(r'^\s*([^<>\s]{1,15})\s+<20>\s+UNIQUE\b', row, re.I)
            if match:
                return match.group(1).strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ''


def browse_mdns(ips, duration=5.0):
    """Passively collect hostnames advertised by local mDNS services.

    mDNS uses link-local multicast. It generally cannot cross routed networks,
    and many servers/devices do not advertise services. Fail gracefully when
    zeroconf is not installed or multicast is blocked.
    """
    try:
        from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
    except ImportError:
        return {}, 'zeroconf not installed'
    wanted = set(ips)
    discovered = {}
    lock = threading.Lock()

    class Listener(ServiceListener):
        def add_service(self, zc, service_type, name):
            try:
                info = zc.get_service_info(service_type, name, timeout=700)
                if info is None:
                    return
                server = (info.server or '').rstrip('.')
                if not server:
                    return
                for address in info.parsed_addresses():
                    if address in wanted:
                        with lock:
                            discovered.setdefault(address, server[:253])
            except Exception:
                pass

        def remove_service(self, zc, service_type, name):
            pass

        def update_service(self, zc, service_type, name):
            self.add_service(zc, service_type, name)

    # Service types selected for device identification, not exhaustive.
    service_types = [
        '_workstation._tcp.local.', '_device-info._tcp.local.',
        '_http._tcp.local.', '_ssh._tcp.local.',
        '_smb._tcp.local.', '_printer._tcp.local.',
        '_ipp._tcp.local.', '_airplay._tcp.local.',
    ]
    zc = None
    try:
        zc = Zeroconf()
        listener = Listener()
        browsers = [ServiceBrowser(zc, t, listener) for t in service_types]
        time.sleep(duration)
        return dict(discovered), ''
    except Exception as exc:
        return dict(discovered), f'mDNS unavailable: {type(exc).__name__}'
    finally:
        if zc is not None:
            zc.close()


class HostnameWorker(QThread):
    resolved = Signal(str, str, str)
    done = Signal(str)

    def __init__(self, ips):
        super().__init__()
        self.ips = list(ips)

    def run(self):
        # Step 1: DNS, then NetBIOS for devices without PTR records.
        results = {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            dns_futures = {pool.submit(reverse_dns, ip): ip for ip in self.ips}
            for future in as_completed(dns_futures):
                ip = dns_futures[future]
                name = future.result()
                if name:
                    results[ip] = (name, 'Reverse DNS')
                    self.resolved.emit(ip, name, 'Reverse DNS')
            unresolved = [ip for ip in self.ips if ip not in results]
            nbt_futures = {pool.submit(netbios_name, ip): ip for ip in unresolved}
            for future in as_completed(nbt_futures):
                ip = nbt_futures[future]
                name = future.result()
                if name:
                    results[ip] = (name, 'NetBIOS')
                    self.resolved.emit(ip, name, 'NetBIOS')

        # Step 2: discover devices that explicitly advertise mDNS services.
        remaining = [ip for ip in self.ips if ip not in results]
        mdns, note = browse_mdns(remaining)
        for ip, name in mdns.items():
            self.resolved.emit(ip, name, 'mDNS')
        self.done.emit(note)


def arp_neighbors():
    """Read Windows' already-known IPv4 neighbor cache; no admin rights needed.

    This is authoritative only for L2 neighbors visible from the current PC.
    Do not treat the MAC as a hostname or claim it identifies a VM behind a router.
    """
    found = {}
    try:
        run = subprocess.run(['arp', '-a'], capture_output=True, text=True,
                             errors='replace', timeout=5,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for line in run.stdout.splitlines():
            match = re.match(r'^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})\s+', line)
            if not match:
                continue
            ip, mac = match.groups()
            try:
                addr = ipaddress.ip_address(ip)
                first = int(mac[:2], 16)
                if addr.is_multicast or addr.is_unspecified or mac.lower() == 'ff-ff-ff-ff-ff-ff' or first & 1:
                    continue
                found[ip] = mac.upper().replace('-', ':')
            except ValueError:
                continue
    except (OSError, subprocess.TimeoutExpired):
        pass
    return found


def http_identity(ip, endpoints=((80, False), (443, True), (8006, True))):
    """Optional low-impact web metadata (title) on port 80/443, not a hostname.

    A title is labeled as a web service hint and is never written into hostname.
    """
    from html import unescape
    for port, ssl_enabled in endpoints:
        try:
            sock = socket.create_connection((ip, port), timeout=0.65)
            sock.settimeout(0.8)
            with sock:
                if ssl_enabled:
                    import ssl
                    context = ssl._create_unverified_context()  # Metadata probe ONLY; never login or send credentials.
                    try:
                        sock = context.wrap_socket(sock, server_hostname=ip)
                    except (OSError, ssl.SSLError):
                        continue
                with sock:
                    sock.sendall(b'GET / HTTP/1.0\r\nHost: ' + ip.encode('ascii') + b'\r\nConnection: close\r\n\r\n')
                    chunks = bytearray()
                    deadline = time.monotonic() + 1
                    while len(chunks) < 16384 and (remaining := deadline - time.monotonic()) > 0:
                        sock.settimeout(remaining)
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        chunks.extend(chunk)
                        if b'</title>' in chunks.lower():
                            break
                    blob = chunks.decode('utf-8', 'replace')
            title = re.search(r'<title[^>]*>(.*?)</title>', blob, re.I | re.S)
            if title:
                label = re.sub(r'\s+', ' ', unescape(title.group(1))).strip()
                if label:
                    return label[:80]
        except (OSError, ValueError):
            pass
    return ''


def probe_services(ip, ports=SERVICE_PORTS):
    """Low-impact bounded TCP connect checks; no credentials or content access."""
    open_ports = []
    for port in ports:
        try:
            with socket.create_connection((ip, port), timeout=0.25):
                open_ports.append(port)
        except OSError:
            pass
    return open_ports


class IdentityWorker(QThread):
    """Discover ARP identity and optional web-service titles off the UI thread."""
    identified = Signal(str, str, str, object)  # ip, mac, web title, ports
    done = Signal(int)

    def __init__(self, ips, deep=False):
        super().__init__()
        self.ips = list(ips)
        self.deep = deep

    def run(self):
        neighbors = arp_neighbors()
        with ThreadPoolExecutor(max_workers=24 if self.deep else 12) as pool:
            futures = {pool.submit(self.collect, ip): ip for ip in self.ips}
            for future in as_completed(futures):
                ip = futures[future]
                try:
                    title, ports = future.result()
                except Exception:
                    title, ports = '', []
                self.identified.emit(ip, neighbors.get(ip, ''), title, ports)
        if self.deep:
            # Probes can populate the Windows cache even when ICMP is filtered.
            neighbors.update(arp_neighbors())
            for ip in self.ips:
                if ip in neighbors:
                    self.identified.emit(ip, neighbors[ip], '', None)
        self.done.emit(sum(bool(neighbors.get(ip)) for ip in self.ips))

    def collect(self, ip):
        web = ((80, False), (443, True), (8006, True))
        if self.deep:
            web += ((8080, False), (8443, True), (5000, False), (5001, True))
        ports = probe_services(ip, (*SERVICE_PORTS, *(port for port, _ in web)))
        endpoints = [(port, tls) for port, tls in web if port in ports]
        # Prefer the dedicated management service when several web servers answer.
        endpoints.sort(key=lambda endpoint: endpoint[0] != 8006)
        return http_identity(ip, endpoints), ports
