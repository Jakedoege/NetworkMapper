"""Qt controls for editing section and cable properties."""
import ipaddress

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QLineEdit, QMessageBox, QSpinBox)


from color_controls import ColorButton
from designer import LINK_TYPES


def edit_properties(parent, title, original, fields, validate):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    form = QFormLayout(dialog)
    controls = {}
    for key, label, options in fields:
        value = original[key]
        if key == 'color':
            widget = ColorButton(dialog, value, value)
            read = lambda control=widget: control.value
        elif isinstance(value, bool):
            widget = QCheckBox()
            widget.setChecked(value)
            read = widget.isChecked
        elif isinstance(value, int):
            widget = QSpinBox()
            widget.setRange(*options)
            widget.setValue(value)
            read = widget.value
        elif options:
            widget = QComboBox()
            for text, entry in options:
                widget.addItem(text, entry)
            widget.setCurrentIndex(max(0, widget.findData(value)))
            read = widget.currentData
        else:
            widget = QLineEdit(str(value))
            read = widget.text
        controls[key] = read
        form.addRow(label, widget)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    while dialog.exec():
        result = dict(original, **{key: read() for key, read in controls.items()})
        try:
            if not QColor(result['color']).isValid():
                raise ValueError('Enter a color name or a hex color such as #53b8ce.')
            validate(result)
        except ValueError as exc:
            QMessageBox.warning(dialog, title, str(exc))
        else:
            return result
    return None


def edit_section(parent, section, kinds):
    def validate(data):
        if not data['name'].strip():
            raise ValueError('Enter a section name.')
        if data['subnet']:
            data['subnet'] = str(ipaddress.IPv4Network(data['subnet'], strict=False))
    return edit_properties(parent, 'Section properties', section, [
        ('name', 'Name', None), ('description', 'Description', None),
        ('color', 'Color', None), ('subnet', 'Match IPv4 range (optional)', None),
        ('kind', 'Match device type', [('Any / no type rule', '')] + [(k, k) for k in kinds]),
    ], validate)


def edit_cable(parent, link, device_name):
    return edit_properties(parent, 'Logical cable properties', ({'kind': 'Generic', 'ports': ''} | link), [
        ('kind', 'Connection type', [(kind, kind) for kind in LINK_TYPES]),
        ('ports', 'Port labels', None),
        ('route', 'Route', [(r, r) for r in ('Straight', 'Curved', 'Right angle')]),
        ('width', 'Width', (1, 12)), ('color', 'Color when monitoring is off', None),
        ('dashed', 'Dashed', None), ('label', 'Label', None),
        ('monitor', 'Monitor endpoint', [('Off', '')] +
         [(device_name(ip), ip) for ip in (link['a'], link['b'])]),
        ('latency', 'Show monitored endpoint latency', None),
    ], lambda data: None)


def edit_note(parent, note):
    return edit_properties(parent, 'Map annotation', note, [
        ('note', 'Type', [(kind, kind) for kind in ('Note', 'Title', 'Legend', 'Floor plan')]),
        ('name', 'Title', None), ('description', 'Text', None),
        ('color', 'Color', None), ('locked', 'Lock position and size', None),
    ], lambda data: None)
