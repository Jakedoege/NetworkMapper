"""Versioned map storage and designer layout algorithms."""
import ipaddress
import json
import math
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from identity import smart_positions

VERSION = 1
LINK_TYPES = ('Generic', 'Ethernet', 'Fiber', 'Wi-Fi')
LAYOUTS = ('Hierarchical', 'Grid', 'Radial', 'Sections / Zones', 'Freeform')


def cable(a, b):
    return dict(a=a, b=b, route='Straight', width=2, color='#53b8ce',
                dashed=False, label='', latency=False, monitor='')


def load_map(path):
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    version = data.get('version', 0)
    if version not in (0, VERSION):
        raise ValueError(f'Unsupported map version: {version}')
    if version == 0:
        data['links'] = [cable(a, b) for a, b in data.get('links', [])]
    return data


def save_map(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(data, version=VERSION), indent=2, allow_nan=False)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False, mode='w',
                                encoding='utf-8') as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def grid(ips, x=0, y=0, columns=None):
    columns = columns or min(12, max(1, math.ceil(math.sqrt(len(ips)))))
    return {ip: (x + i % columns * 195, y + i // columns * 125)
            for i, ip in enumerate(ips)}


def positions(mode, devices, gateway):
    ips = sorted(devices, key=ipaddress.ip_address)
    if mode == 'Hierarchical':
        return smart_positions(devices, gateway)
    if mode != 'Radial' or not ips:
        return grid(ips)
    center = gateway if gateway in devices else ips[0]
    ips.remove(center)
    result = {center: (0, 0)}
    # Fill rings from the center out; cap each ring by card separation.
    offset = 0
    radius = 225
    while offset < len(ips):
        capacity = max(1, int(math.pi / math.asin(105 / radius)))
        ring = ips[offset:offset + capacity]
        for i, ip in enumerate(ring):
            angle = 2 * math.pi * i / len(ring) - math.pi / 2
            result[ip] = (radius * math.cos(angle), radius * math.sin(angle))
        offset += len(ring)
        radius += 220
    return result


def section_members(section, devices):
    members = set(section['members'])
    subnet = ipaddress.ip_network(section['subnet'], strict=False) if section['subnet'] else None
    for ip, data in devices.items():
        if ((subnet and ipaddress.ip_address(ip) in subnet)
                or (section['kind'] and section['kind'] == data.get('type'))):
            members.add(ip)
    return sorted(members.intersection(devices), key=ipaddress.ip_address)
