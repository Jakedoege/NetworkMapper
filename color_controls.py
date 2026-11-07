"""Color pickers shared by the canvas palette and individual device cards."""
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QPushButton


def readable_ink(color):
    channels = [color.redF(), color.greenF(), color.blueF()]
    linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
              for value in channels]
    luminance = sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    return '#151515' if luminance > .18 else '#ffffff'


class ColorButton(QPushButton):
    def __init__(self, parent, base, value=''):
        super().__init__(parent)
        self.set_color(base, value)
        self.clicked.connect(self.choose)

    def set_color(self, base, value=''):
        self.base, self.value = base, value
        effective = QColor(value or base)
        self.setText(value.upper() if value else 'Default')
        self.setToolTip(effective.name().upper())
        self.setStyleSheet(f'background: {effective.name()}; color: {readable_ink(effective)};'
                           'border: 1px solid #74849b; padding: 4px 8px;')

    def choose(self):
        color = QColorDialog.getColor(QColor(self.value or self.base), self, 'Choose color')
        if color.isValid():
            self.set_color(self.base, color.name())
