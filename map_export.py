"""Render the current map to an image or a vector PDF."""
import math
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPageLayout, QPageSize, QPdfWriter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QLineEdit, QMessageBox)

from map_view import DeviceItem


class MapExport:
    def export_map(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Export map')
        form = QFormLayout(dialog)
        title = QLineEdit('Network map')
        kind = QComboBox()
        kind.addItems(['PNG', 'PDF'])
        legend = QCheckBox()
        legend.setChecked(True)
        private = QCheckBox()
        form.addRow('Title', title)
        form.addRow('Format', kind)
        form.addRow('Include ping legend', legend)
        form.addRow('Hide identifying labels and imported artwork', private)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if not dialog.exec():
            return
        suffix = kind.currentText().lower()
        filename, _ = QFileDialog.getSaveFileName(self, 'Save map', f'Network map.{suffix}',
                                                  f'{suffix.upper()} (*.{suffix})')
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != f'.{suffix}':
            path = path.with_name(path.name + f'.{suffix}')
        try:
            render_map(self.view, path, title.text(), legend.isChecked(), private.isChecked())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Export map', str(exc))
        else:
            self.status.setText(f'Exported {path.name}')


def render_map(view, path, title, legend=True, private=False):
    scene = view.scene()
    selected = scene.selectedItems()
    visible = [item for item in scene.items() if item.isVisible()]
    if not visible:
        raise ValueError('There are no visible map items to export.')
    bounds = QRectF()
    for item in visible:
        bounds = bounds.united(item.sceneBoundingRect())
    bounds.adjust(-24, -24, 24, 24)
    view.export_aliases = {
        ip: f'Device {i}' for i, ip in enumerate(view.items_by_ip, 1)
    } if private else None
    if private:
        title = 'Network map'
    painter = QPainter()
    try:
        scene.clearSelection()
        view.update_links()
        header = 42 if title else 0
        footer = 32 if legend else 0
        if path.suffix.lower() == '.pdf':
            device = QPdfWriter(str(path))
            device.setResolution(96)
            device.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            device.setPageOrientation(QPageLayout.Orientation.Landscape)
            device.setTitle(title)
        else:
            scale = min(2.0, 5000 / max(bounds.width(), bounds.height() + header + footer))
            device = QImage(math.ceil(max(500, bounds.width()) * scale),
                            math.ceil((bounds.height() + header + footer) * scale),
                            QImage.Format.Format_RGB32)
        if not painter.begin(device):
            raise OSError(f'Could not write {path.name}.')
        canvas = QRectF(painter.viewport())
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(canvas, QColor(view.style['bg']))
        painter.setPen(QColor(view.style['text']))
        font = QFont('Segoe UI')
        font.setPixelSize(22)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(20, 0, canvas.width() - 40, header),
                         Qt.AlignmentFlag.AlignVCenter, title)
        area = canvas.adjusted(0, header, 0, -footer)
        ratio = min(area.width() / bounds.width(), area.height() / bounds.height())
        target = QRectF(0, 0, bounds.width() * ratio, bounds.height() * ratio)
        target.moveCenter(area.center())
        scene.render(painter, target, bounds)
        if legend:
            for index, (key, label) in enumerate((
                    ('online', 'Online'), ('offline', 'No ping reply'),
                    ('slow', 'High latency'), ('unknown', 'Not checked'))):
                x = index * canvas.width() / 4
                y = canvas.height() - footer
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(view.style[key]))
                painter.drawEllipse(QRectF(x + 8, y + 10, 10, 10))
                DeviceItem.text(painter, label, QRectF(x + 20, y, canvas.width() / 4 - 22, footer),
                                12, view.style['text'])
        painter.end()
        if isinstance(device, QImage) and not device.save(str(path), 'PNG'):
            raise OSError(f'Could not write {path.name}.')
    finally:
        if painter.isActive():
            painter.end()
        view.export_aliases = None
        for item in selected:
            item.setSelected(True)
        view.update_links()
