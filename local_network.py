"""Windows IPv4 network autodetection. No external commands beyond stock PowerShell."""
import ipaddress
import json
import subprocess

PS = r"""$routes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Where-Object { $_.NextHop -ne '0.0.0.0' } | Sort-Object { $_.RouteMetric + $_.InterfaceMetric }); foreach ($r in $routes) { $a = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $r.InterfaceIndex -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '169.254*' } | Select-Object -First 1; if($a) { [PSCustomObject]@{ ip=$a.IPAddress; prefix=[int]$a.PrefixLength; gateway=$r.NextHop; interface=$r.InterfaceAlias } | ConvertTo-Json -Compress; break } }"""


def parse_config(text):
    """Return validated IPv4 network record or None. No guessing a /24."""
    try:
        obj = json.loads(text.strip())
        ip = ipaddress.IPv4Address(obj['ip'])
        gw = ipaddress.IPv4Address(obj['gateway'])
        prefix = int(obj['prefix'])
        network = ipaddress.ip_network(f'{ip}/{prefix}', strict=False)
        if not network.is_private or not gw in network or prefix < 24:
            # Keep the product's <=256 address scan safety limit.
            return None
        return {'subnet': str(network), 'gateway': str(gw), 'ip': str(ip),
                'interface': str(obj.get('interface', ''))}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def detect_local_network():
    try:
        p = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',PS],
                           capture_output=True,text=True,errors='replace',timeout=9,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return parse_config(p.stdout) if p.returncode == 0 else None
    except (OSError,subprocess.TimeoutExpired):
        return None
