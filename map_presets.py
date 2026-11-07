"""Map presets affect the canvas without changing device coordinates."""
PRESETS = {
    'Readable': dict(bg='#101a2a', grid='#26364c', card='#17263a',
                     selected='#243d58', border='#4c6988', text='#f1f6ff',
                     secondary='#bdcde0', name=14, detail=11),
    'High contrast': dict(bg='#080c14', grid='#243247', card='#172334',
                          selected='#294869', border='#7897b9', text='#ffffff',
                          secondary='#dae8fa', name=16, detail=12),
    'Light blueprint': dict(bg='#e8f0f8', grid='#ccdbea', card='#f9fcff',
                            selected='#cce6fc', border='#5e7b99', text='#14283e',
                            secondary='#344f6b', name=14, detail=11),
}
DEFAULT_MAP = dict(preset='Readable', address=True, status=True, badges=True,
                   colors={}, vendor_icons={})

COLOR_FIELDS = {
    'bg': 'Background', 'grid': 'Grid', 'card': 'Card fill',
    'selected': 'Selected card fill', 'border': 'Card border',
    'selection': 'Selection outline', 'text': 'Names and icons',
    'secondary': 'IP addresses', 'inferred': 'Inferred links',
    'online': 'Online', 'offline': 'No ping reply',
    'unknown': 'Not checked', 'slow': 'High latency',
}
SHARED = dict(selection='#60afff', inferred='#566477', online='#4adea2',
              offline='#fb7185', unknown='#94a3b8', slow='#facc59')


def palette(preset, overrides=None):
    base = dict(SHARED, **PRESETS.get(preset, PRESETS['Readable']))
    if overrides:
        for key, color in overrides.items():
            if key in COLOR_FIELDS and isinstance(color, str) and len(color) == 7 and (
                    color.startswith('#') and all(c in '0123456789abcdefABCDEF' for c in color[1:])):
                base[key] = color
    return base
