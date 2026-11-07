"""Conservative device identity hints, not proof of physical topology.

No third-party online MAC lookup: MAC addresses never leave the LAN.
"""
import ipaddress
import re
import subprocess

from oui_registry import BY_PREFIX
from vendors import WEB_MARKERS

# Only prefixes of common virtualization platforms whose meaning is sufficiently stable.
VIRTUAL_PREFIXES = {
    'BC:24:11': 'Proxmox virtual NIC',
    '52:54:00': 'QEMU / KVM virtual NIC',
    '00:0C:29': 'VMware virtual NIC',
    '00:50:56': 'VMware virtual NIC',
    '00:05:69': 'VMware virtual NIC',
    '08:00:27': 'VirtualBox virtual NIC',
    '00:15:5D': 'Hyper-V virtual NIC',
}
# The port list is deliberately small and non-invasive.
SERVICE_PORTS = {
    8006: 'Proxmox VE management',
    3389: 'Remote Desktop',
    445: 'SMB file sharing',
    5985: 'WinRM HTTP',
    9100: 'Network printing (JetDirect)',
    631: 'IPP printing',
    554: 'RTSP streaming',
    22: 'SSH',
}
GENERIC_HTTP = re.compile(r'(?i)^(?:\d{3}[\s:-]|moved(?:\s|$)|redirect(?:ing)?\b|sign in$|login$|index of /|default page|unidentified device)')


def mac_hint(mac):
    if not mac:
        return '', ''
    mac = mac.upper().replace('-', ':')
    try:
        first = int(mac[:2], 16)
    except ValueError:
        return '', ''
    if first & 2:
        # Some virtual NICs intentionally use locally administered addresses.
        for prefix, name in VIRTUAL_PREFIXES.items():
            if mac.startswith(prefix):
                return name, 'Known virtualization prefix'
        return 'Locally administered MAC', 'MAC address bit'
    for prefix, name in VIRTUAL_PREFIXES.items():
        if mac.startswith(prefix):
            return name, 'Known virtualization prefix'
    vendor = BY_PREFIX.get(mac.replace(':', '')[:6], '')
    return (vendor, 'IEEE MAC prefix') if vendor else ('', '')


def meaningful_web(title):
    title = re.sub(r'\s+', ' ', title or '').strip()
    if not title or GENERIC_HTTP.match(title):
        return ''
    title = re.sub(r'(?i)^(?:sign in|log in|login)\s*[-–—|:]\s*', '', title)
    return title[:70]


def determine_identity(ip, data, gateway=''):
    """Produce a suggested class with justification and evidence, never a fabricated hostname."""
    ports = set(data.get('ports') or [])
    mac = data.get('mac', '')
    vendor, vendor_source = mac_hint(mac)
    name = (data.get('hostname') or '').lower()
    web = meaningful_web(data.get('web_title'))
    kind, confidence, reason = 'Unknown', 'Unknown', 'No identifying service detected'
    if ip == gateway:
        kind, confidence, reason = 'Router', 'High', 'Matches this PC\'s default gateway'
    elif 'proxmox' in web.lower():
        kind, confidence, reason = 'Server', 'High', 'Web interface identifies itself as Proxmox'
    elif 'idrac' in web.lower() or 'integrated lights-out' in web.lower():
        kind, confidence, reason = 'Server', 'High', 'Server management web interface'
    elif 8006 in ports:
        kind, confidence, reason = 'Server', 'Medium', 'TCP 8006 responds, commonly used by Proxmox VE'
    elif 9100 in ports or 631 in ports:
        kind, confidence, reason = 'Printer', 'Medium', 'Standard printing service responds'
    elif 554 in ports:
        kind, confidence, reason = 'Camera', 'Low', 'RTSP responds (could also be recorder/media server)'
    elif 5985 in ports:
        kind, confidence, reason = 'PC', 'Low', 'WinRM responds (could also be a Windows server)'
    elif 'printer' in name:
        kind, confidence, reason = 'Printer', 'Medium', 'Hostname suggests printer'
    elif 'switch' in name:
        kind, confidence, reason = 'Switch', 'Low', 'Hostname suggests switch'
    elif 22 in ports or 445 in ports:
        confidence, reason = 'Low', 'SSH or SMB responds; service does not identify a device type'
    web_vendor = next((brand for brand, markers in WEB_MARKERS
                       if any(marker in web.lower() for marker in markers)), '')
    badge = web_vendor or (vendor if vendor_source == 'IEEE MAC prefix' else '')
    if not badge and vendor == 'Proxmox virtual NIC':
        badge = 'Proxmox virtual NIC'
    return {
        'badge_hint': badge,
        'suggested_type': kind, 'confidence': confidence, 'reason': reason,
        'vendor_hint': vendor, 'vendor_source': vendor_source,
        'service_hint': web,
    }


def default_gateway():
    """Pick lowest metric default IPv4 route on Windows. Return empty on error."""
    try:
        p = subprocess.run(['route', 'print', '-4'], capture_output=True, text=True,
                           errors='replace', timeout=5,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        found = []
        for line in p.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == parts[1] == '0.0.0.0':
                try:
                    gateway = str(ipaddress.IPv4Address(parts[2]))
                    metric = int(parts[4])
                    if gateway != '0.0.0.0':
                        found.append((metric, gateway))
                except (ValueError, ipaddress.AddressValueError):
                    pass
        return min(found)[1] if found else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def smart_positions(devices, gateway=''):
    """Topology-style *grouping*, not a claim of physical connections."""
    tiers = [[], [], [], []]
    infrastructure = {'Router', 'Switch', 'Access point'}
    for ip, data in sorted(devices.items(), key=lambda pair: ipaddress.ip_address(pair[0])):
        kind = data.get('type') or data.get('suggested_type') or 'Unknown'
        tier = 0 if ip == gateway else 1 if kind in infrastructure else 2 if kind == 'Server' else 3
        tiers[tier].append(ip)
    result = {}
    y = -310
    for tier, ids in enumerate(tiers):
        if not ids:
            continue
        cols = 6
        for start in range(0, len(ids), cols):
            row = ids[start:start + cols]
            spacing = 195
            x0 = -spacing * (len(row) - 1) / 2
            for index, ip in enumerate(row):
                result[ip] = (float(x0 + index * spacing), float(y))
            y += 145
        y += 70
    return result
