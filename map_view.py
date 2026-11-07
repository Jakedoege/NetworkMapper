"""The visual map canvas and its editable graphics items."""
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsObject, QGraphicsScene,
                               QGraphicsView, QMenu)

from designer import LINK_TYPES
from map_presets import DEFAULT_MAP, palette
from brand_paths import BRAND_PATHS, BRAND_PNGS
from color_controls import readable_ink
from vendors import BADGES

CARD_SIZES = {'Compact': (132, 76), 'Standard': (160, 90), 'Large': (190, 116)}
CARD_FIELDS = ('IP address', 'Hostname', 'Model / service', 'Location', 'Tags', 'Ping latency')

TYPE_SYMBOL = dict.fromkeys(('Unknown', 'Router', 'Switch', 'Server', 'PC',
                            'Printer', 'Camera', 'Access point'))
NO_BUTTON = Qt.MouseButton.NoButton
NO_PEN = Qt.PenStyle.NoPen
CENTER = Qt.AlignmentFlag.AlignCenter
MOVABLE = QGraphicsItem.GraphicsItemFlag.ItemIsMovable
SELECTABLE = QGraphicsItem.GraphicsItemFlag.ItemIsSelectable


def device_name(ip, data):
    return (data.get('name') or data.get('hostname') or data.get('service_hint')
            or ((data.get('vendor_hint') + ' · ' + ip.rsplit('.', 1)[-1])
                if data.get('vendor_hint') and data.get('vendor_source') != 'MAC address bit' else ip))


def health(data, style):
    online = data.get('online')
    if online is None:
        return style['unknown']
    if not online:
        return style['offline']
    return style['slow' if (data.get('latency') or 0) >= 150 else 'online']


def vendor_icon(vendor, uploaded=''):
    payload = uploaded or BRAND_PNGS.get(vendor, '')
    if payload:
        return QPixmap.fromImage(QImage.fromData(QByteArray.fromBase64(payload.encode('ascii'))))
    paths = BRAND_PATHS.get(vendor)
    if not paths:
        return QPixmap()
    body = ''.join(f'<path d="{path}"/>' for path in paths)
    svg = QSvgRenderer(QByteArray((
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#142235">'
        f'{body}</svg>').encode('ascii')))
    pixmap = QPixmap(96, 96)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    svg.render(painter)
    painter.end()
    return pixmap


def draw_icon(p, kind, color):
    """Draw bundled vector glyphs in a 24 by 24 coordinate system."""
    p.setPen(QPen(QColor(color), 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind in ('Router', 'Switch', 'Server'):
        if kind == 'Router':
            p.drawLine(5, 10, 5, 3)
            p.drawLine(19, 10, 19, 3)
        for y in ([4, 13] if kind == 'Server' else [10]):
            p.drawRoundedRect(QRectF(2, y, 20, 7), 2, 2)
            for x in (6, 10, 14):
                p.drawPoint(x, y + 3)
    elif kind == 'PC':
        p.drawRoundedRect(QRectF(2, 3, 20, 13), 2, 2)
        p.drawLine(12, 16, 12, 21)
        p.drawLine(7, 21, 17, 21)
    elif kind == 'Printer':
        p.drawRect(QRectF(6, 2, 12, 6))
        p.drawRoundedRect(QRectF(2, 8, 20, 10), 2, 2)
        p.drawRect(QRectF(6, 14, 12, 8))
    elif kind == 'Camera':
        p.drawRoundedRect(QRectF(2, 6, 20, 13), 3, 3)
        p.drawEllipse(QRectF(8, 8, 8, 8))
    elif kind == 'Access point':
        for inset in (0, 4, 8):
            p.drawArc(QRectF(1 + inset, 3 + inset, 22 - 2 * inset, 22 - 2 * inset), 45 * 16, 90 * 16)
        p.drawPoint(12, 16)
    else:
        p.drawEllipse(QRectF(3, 3, 18, 18))
        p.drawText(QRectF(3, 3, 18, 18), CENTER, '?')


class DeviceItem(QGraphicsObject):
    def __init__(self, view, ip, data):
        super().__init__()
        self.view, self.ip = view, ip
        self.dimensions = CARD_SIZES['Standard']
        self.setFlags(MOVABLE | SELECTABLE | self.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setPos(float(data.get('x', 0)), float(data.get('y', 0)))
        self.setZValue(3)
        self.icon_source = None
        self.icon = QPixmap()
        self.refresh(data)

    def refresh(self, data):
        dimensions = CARD_SIZES.get(data.get('card_size'), CARD_SIZES['Standard'])
        if dimensions != getattr(self, 'dimensions', None):
            self.prepareGeometryChange()
            self.dimensions = dimensions
        self.data = data
        source = data.get('icon_png', '')
        if source != self.icon_source:
            self.icon_source = source
            self.icon = QPixmap.fromImage(QImage.fromData(
                QByteArray.fromBase64(source.encode('ascii'))))
        self.setToolTip(f'{device_name(self.ip, data)} · {self.ip}')
        self.update()

    def boundingRect(self):
        width, height = self.dimensions
        return QRectF(-width / 2, -height / 2, width, height)

    def paint(self, p, option, widget=None):
        p.save()
        width, height = self.dimensions
        p.scale(width / 160, height / 90)
        r = QRectF(-79, -44, 158, 88)
        style = self.view.style
        fill = self.data.get('fill') or style['card']
        if self.isSelected() and not self.data.get('fill'):
            fill = style['selected']
        text_color = self.data.get('text_color') or (
            readable_ink(QColor(fill)) if self.data.get('fill') else style['text'])
        p.setBrush(QColor(fill))
        accent = self.data.get('accent') or style['border']
        p.setPen(QPen(QColor(style['selection'] if self.isSelected() else accent), 2))
        p.drawRoundedRect(r, 10, 10)
        if self.view.options['status']:
            p.setBrush(QColor(health(self.data, style)))
            p.setPen(NO_PEN)
            p.drawEllipse(QRectF(-68, -33, 10, 10))
        size = self.data.get('icon_size', 26)
        p.save()
        p.translate(-size / 2, -37)
        p.scale(size / 24, size / 24)
        if self.icon.isNull() or self.view.export_aliases is not None:
            draw_icon(p, self.data.get('type'), text_color)
        else:
            pixmap = self.icon.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
            width, height = pixmap.width() / 3, pixmap.height() / 3
            p.drawPixmap(QRectF((24 - width) / 2, (24 - height) / 2, width, height),
                         pixmap, QRectF(pixmap.rect()))
        p.restore()
        vendor = self.data.get('badge', 'Auto')
        if vendor == 'Auto':
            vendor = self.data.get('badge_hint', '')
        badge = BADGES.get(vendor)
        if self.view.options['badges'] and badge and self.view.export_aliases is None:
            title, color = badge
            logo = self.view.vendor_icon(vendor)
            p.setPen(NO_PEN)
            p.setBrush(QColor(color))
            if logo.isNull():
                bounds = QRectF(24, -35, 47, 16)
                p.drawRoundedRect(bounds, 4, 4)
                self.text(p, title, bounds, 9, '#102030', True)
            else:
                bounds = QRectF(37, -39, 35, 35)
                p.drawRoundedRect(bounds, 6, 6)
                area = bounds.adjusted(4, 4, -4, -4)
                scale = min(area.width() / logo.width(), area.height() / logo.height())
                width, height = logo.width() * scale, logo.height() * scale
                target = QRectF(area.center().x() - width / 2, area.center().y() - height / 2,
                                width, height)
                p.drawPixmap(target, logo, QRectF(logo.rect()))
        data = self.data
        name = device_name(self.ip, data)
        detail = ''
        if self.view.export_aliases is not None:
            name = self.view.export_aliases[self.ip]
        else:
            fields = self.view.options.get('card_fields', ['IP address'])
            values = {
                'IP address': self.ip if self.view.options['address'] else '',
                'Hostname': data.get('hostname', ''),
                'Model / service': data.get('model') or data.get('service_hint', ''),
                'Location': data.get('location', ''), 'Tags': data.get('tags', ''),
                'Ping latency': f"{data['latency']:g} ms" if data.get('online') and
                data.get('latency') is not None else '',
            }
            detail = ' · '.join(value for field in fields
                                if (value := values.get(field)) and value != name)
        self.text(p, name, QRectF(-73, 0 if detail else 5, 146, 24),
                  style['name'], text_color, True)
        if detail:
            self.text(p, detail, QRectF(-73, 23, 146, 15), style['detail'],
                      text_color if data.get('fill') or data.get('text_color') else style['secondary'])
        p.restore()

    @staticmethod
    def text(p, text, rect, size, color, bold=False):
        font = QFont('Segoe UI')
        font.setPixelSize(size)
        font.setBold(bold)
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(rect, CENTER, p.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, int(rect.width())))

    def itemChange(self, change, value):
        if change == self.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            self.view.update_links(self.ip)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self.view.device_selected.emit(self.ip)
        if self.view.connecting:
            self.view.endpoint_clicked.emit(self.ip)
            event.accept()
            return
        self.start_position = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if getattr(self, 'start_position', self.pos()) != self.pos():
            if self.view.snap:
                self.setPos(self.view.snapped(self.pos()))
            self.view.device_moved.emit(self.ip, self.x(), self.y())
        self.start_position = self.pos()


class SectionItem(QGraphicsObject):
    def __init__(self, view, data):
        super().__init__()
        self.view, self.data = view, data
        self.setFlags(SELECTABLE if data.get('locked') else MOVABLE | SELECTABLE)
        self.backdrop = QImage.fromData(QByteArray.fromBase64(data.get('backdrop', '').encode('ascii'))) if data.get('backdrop') else QImage()
        self.setPos(data['x'], data['y'])
        self.setZValue(-5 if data.get('note') == 'Floor plan' else -3)
        self.setToolTip(data['description'])

    def boundingRect(self):
        height = 40 if self.data['collapsed'] else self.data['h']
        return QRectF(0, 0, self.data['w'], height)

    def paint(self, p, option, widget=None):
        r = self.boundingRect().adjusted(1, 1, -1, -1)
        accent = QColor(self.data['color'])
        fill = QColor(accent)
        fill.setAlpha(45 if self.isSelected() else 26)
        p.setPen(QPen(accent, 1.5))
        p.setBrush(fill)
        p.drawRoundedRect(r, 10, 10)
        if self.view.export_aliases is not None:
            return
        if not self.data['collapsed'] and not self.backdrop.isNull():
            area = r.adjusted(8, 38, -8, -8)
            size = self.backdrop.size().scaled(area.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
            picture = QRectF(0, 0, size.width(), size.height())
            picture.moveCenter(area.center())
            p.drawImage(picture, self.backdrop)
        p.setFont(QFont('Segoe UI', 13 if self.data.get('note') == 'Title' else 10, QFont.Weight.Bold))
        marker = '▸' if self.data['collapsed'] else '▾'
        name = p.fontMetrics().elidedText(self.data['name'], Qt.TextElideMode.ElideRight,
                                          int(r.width() - 55))
        p.drawText(QRectF(13, 5, r.width() - 25, 30),
                   Qt.AlignmentFlag.AlignVCenter, f'{marker}  {name}')
        if self.data.get('note') and not self.data['collapsed'] and self.data['description']:
            p.setFont(QFont('Segoe UI', 10))
            p.drawText(r.adjusted(14, 40, -14, -13),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                       self.data['description'])
        if not self.data['collapsed'] and not self.data.get('locked'):
            p.drawLine(QPointF(r.right() - 14, r.bottom() - 5),
                       QPointF(r.right() - 5, r.bottom() - 14))

    def mousePressEvent(self, event):
        self.original = self.pos()
        self.resizing = (not self.data.get('locked') and not self.data['collapsed'] and
                         event.pos().x() >= self.data['w'] - 18 and
                         event.pos().y() >= self.data['h'] - 18)
        if self.resizing:
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.resizing:
            self.prepareGeometryChange()
            self.data['w'] = max(200, event.pos().x())
            self.data['h'] = max(120, event.pos().y())
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.view.snap and not self.data.get('locked'):
            self.setPos(self.view.snapped(self.pos()))
        self.view.section_moved.emit(self.data['id'], self.pos() - self.original)
        self.resizing = False

    def mouseDoubleClickEvent(self, event):
        event.accept()
        self.view.section_action.emit(self.data['id'], 'Collapse / expand')

    def contextMenuEvent(self, event):
        edit = 'Edit annotation' if self.data.get('note') else 'Edit section'
        actions = [edit, 'Collapse / expand', 'Lock / unlock']
        if self.data.get('note') == 'Floor plan':
            actions.append('Import backdrop…')
        if self.data.get('backdrop'):
            actions.append('Remove backdrop')
        actions.append('Delete section')
        self.view.menu(event, actions,
                       lambda action: self.view.section_action.emit(self.data['id'], action))


class NetworkView(QGraphicsView):
    device_selected = Signal(str)
    device_moved = Signal(str, float, float)
    section_moved = Signal(str, QPointF)
    section_action = Signal(str, str)
    cable_action = Signal(int, str)
    endpoint_clicked = Signal(str)
    canvas_section = Signal(QPointF)
    canvas_note = Signal(QPointF)
    zoom_changed = Signal(int)

    def __init__(self):
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing |
                            QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(self.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(self.ViewportAnchor.AnchorUnderMouse)
        self._scene.setSceneRect(-900, -700, 1800, 1400)
        self.items_by_ip = {}
        self.sections = {}
        self.links = []
        self.inferred_links = []
        self.show_inferred = False
        self.snap = False
        self.show_grid = True
        self.visible_link_types = set(LINK_TYPES)
        self.export_aliases = None
        self.options = dict(DEFAULT_MAP)
        self.style = palette(self.options['preset'])
        self._vendor_icons = {}
        self.connecting = False
        self._paths = []
        self._inferred = []
        self._by_endpoint = {}

    @staticmethod
    def snapped(point):
        return QPointF(round(point.x() / 25) * 25, round(point.y() / 25) * 25)

    def drawBackground(self, p, rect):
        p.fillRect(rect, QColor(self.style['bg']))
        if self.show_grid:
            step = 25 if self.transform().m11() >= .55 else 100
            p.setPen(QPen(QColor(self.style['grid']), 0))
            for x in range(int(rect.left()) // step * step, int(rect.right()) + 1, step):
                p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            for y in range(int(rect.top()) // step * step, int(rect.bottom()) + 1, step):
                p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

    def add_device(self, ip, data):
        if ip in self.items_by_ip:
            self.items_by_ip[ip].refresh(data)
        else:
            item = DeviceItem(self, ip, data)
            self._scene.addItem(item)
            self.items_by_ip[ip] = item
        self.update_links(ip)

    def set_sections(self, sections):
        for item in self.sections.values():
            self._scene.removeItem(item)
        self.sections.clear()
        for data in sections:
            item = SectionItem(self, data)
            self._scene.addItem(item)
            self.sections[data['id']] = item
        self.expand_bounds()

    def set_links(self, links):
        self.links = links
        for path, label in self._paths:
            self._scene.removeItem(path)
            self._scene.removeItem(label)
        self._paths = []
        self._by_endpoint.clear()
        for index, link in enumerate(links):
            path = self._scene.addPath(QPainterPath())
            path.setAcceptedMouseButtons(NO_BUTTON)
            label = self._scene.addSimpleText('')
            label.setBrush(QColor(self.style['text']))
            label.setZValue(2)
            label.setAcceptedMouseButtons(NO_BUTTON)
            self._paths.append((path, label))
            for ip in (link['a'], link['b']):
                self._by_endpoint.setdefault(ip, []).append(index)
            self.update_cable(index)
        self.refresh_inferred()

    def set_inferred_links(self, links, visible):
        self.inferred_links = links
        self.show_inferred = bool(visible)
        self.refresh_inferred()

    def refresh_inferred(self):
        for line, _, _ in self._inferred:
            self._scene.removeItem(line)
        self._inferred = []
        if not self.show_inferred:
            return
        manual = {frozenset((link['a'], link['b'])) for link in self.links}
        for a, b in self.inferred_links:
            if frozenset((a, b)) in manual or a not in self.items_by_ip or b not in self.items_by_ip:
                continue
            line = self._scene.addLine(0, 0, 0, 0, QPen(QColor(self.style['inferred']), 1, Qt.PenStyle.DotLine))
            line.setZValue(-1)
            line.setAcceptedMouseButtons(NO_BUTTON)
            self._inferred.append((line, a, b))
        self.update_inferred()

    def update_inferred(self, ip=None):
        for line, a, b in self._inferred:
            if ip is None or ip in (a, b):
                first, second = self.items_by_ip[a], self.items_by_ip[b]
                line.setVisible(first.isVisible() and second.isVisible())
                line.setLine(first.x(), first.y(), second.x(), second.y())

    def update_links(self, ip=None):
        for index in (range(len(self._paths)) if ip is None else self._by_endpoint.get(ip, ())):
            self.update_cable(index)
        self.update_inferred(ip)

    def update_cable(self, index):
        link = self.links[index]
        item, label = self._paths[index]
        a, b = (self.items_by_ip.get(link[key]) for key in ('a', 'b'))
        kind = link.get('kind', 'Generic')
        visible = bool(kind in self.visible_link_types and a and b and a.isVisible() and b.isVisible())
        item.setVisible(visible)
        label.setVisible(visible)
        if not visible:
            return
        p, q = a.pos(), b.pos()
        path = QPainterPath(p)
        mid = (p.x() + q.x()) / 2
        if link['route'] == 'Curved':
            path.cubicTo(QPointF(mid, p.y() - 42), QPointF(mid, q.y() - 42), q)
        elif link['route'] == 'Right angle':
            path.lineTo(mid, p.y())
            path.lineTo(mid, q.y())
            path.lineTo(q)
        else:
            path.lineTo(q)
        item.setPath(path)
        monitored = self.items_by_ip.get(link['monitor'])
        color = link['color']
        if monitored:
            color = health(monitored.data, self.style)
        elif color == '#53b8ce':
            color = {'Ethernet': '#57beee', 'Fiber': '#bd93f9', 'Wi-Fi': '#f1bf68'}.get(kind, color)
        style = (Qt.PenStyle.DashLine if link['dashed'] else
                 Qt.PenStyle.DotLine if kind == 'Wi-Fi' else Qt.PenStyle.SolidLine)
        item.setPen(QPen(QColor(color), link['width'], style))
        title = ' · '.join(filter(None, (link['label'], link.get('ports', ''))))
        if self.export_aliases is not None:
            title = ''
        if monitored and link['latency']:
            latency = monitored.data.get('latency')
            ping = f'{latency:g} ms' if monitored.data.get('online') and latency is not None else (
                'Unreachable' if monitored.data.get('online') is False else 'Not checked')
            title = f'{title}  ·  {ping}' if title else ping
        label.setText(title)
        label.setVisible(bool(title))
        label.setPos(path.pointAtPercent(.5) - QPointF(label.boundingRect().width() / 2, 22))

    @staticmethod
    def menu(event, labels, callback):
        menu = QMenu()
        actions = {menu.addAction(label): label for label in labels}
        position = event.screenPos() if hasattr(event, 'screenPos') else event.globalPos()
        choice = menu.exec(position)
        if choice in actions:
            callback(actions[choice])
        event.accept()

    def contextMenuEvent(self, event):
        point = self.mapToScene(event.pos())
        hits = self.items(event.pos())
        for index, (path, label) in enumerate(self._paths):
            if path in hits or label in hits:
                self.menu(event, ('Edit cable', 'Delete cable'),
                          lambda action: self.cable_action.emit(index, action))
                return
        if any(isinstance(item, SectionItem) for item in hits):
            super().contextMenuEvent(event)
            return
        self.menu(event, ('Add section here', 'Add annotation here'),
                  lambda action: (self.canvas_section if action == 'Add section here'
                                  else self.canvas_note).emit(point))

    def wheelEvent(self, event):
        self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)

    def zoom(self, factor):
        current = self.transform().m11()
        target = min(3, max(.12, current * factor))
        self.scale(target / current, target / current)
        self.zoom_changed.emit(round(target * 100))

    def restore_camera(self, zoom, x, y):
        self.resetTransform()
        self.zoom(zoom)
        self.centerOn(x, y)

    def set_options(self, options):
        self.options = dict(DEFAULT_MAP, **options)
        self.style = palette(self.options['preset'], self.options['colors'])
        self._vendor_icons.clear()
        for item in self.items_by_ip.values():
            item.update()
        for _, label in self._paths:
            label.setBrush(QColor(self.style['text']))
        self.refresh_inferred()
        self.update_links()
        self.viewport().update()

    def vendor_icon(self, vendor):
        if vendor not in self._vendor_icons:
            self._vendor_icons[vendor] = vendor_icon(vendor, self.options['vendor_icons'].get(vendor, ''))
        return self._vendor_icons[vendor]

    def focus_device(self, ip):
        item = self.items_by_ip.get(ip)
        if item and item.isVisible():
            if self.transform().m11() < 1:
                self.zoom(1 / self.transform().m11())
            self.centerOn(item)

    def set_device_position(self, ip, x, y):
        self.items_by_ip[ip].setPos(float(x), float(y))

    def expand_bounds(self):
        bounds = self._scene.itemsBoundingRect().adjusted(-350, -350, 350, 350)
        self._scene.setSceneRect(self._scene.sceneRect().united(bounds))

    def fit_nodes(self):
        items = [item for item in (*self.items_by_ip.values(), *self.sections.values()) if item.isVisible()]
        if not items:
            return
        bounds = items[0].sceneBoundingRect()
        for item in items[1:]:
            bounds = bounds.united(item.sceneBoundingRect())
        self.expand_bounds()
        self.fitInView(bounds.adjusted(-40, -40, 40, 40), Qt.AspectRatioMode.KeepAspectRatio)
        if self.transform().m11() > 1:
            self.resetTransform()
            self.centerOn(bounds.center())
        self.zoom_changed.emit(round(self.transform().m11() * 100))
