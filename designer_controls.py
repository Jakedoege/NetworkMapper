"""Designer operations integrated with the existing scan and device panel."""
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QImage, QImageReader, QPainter, QShortcut, QKeySequence
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from designer import LINK_TYPES, LAYOUTS, cable, grid, positions, section_members
from designer_dialogs import edit_cable, edit_note, edit_section
from map_view import CARD_FIELDS, TYPE_SYMBOL, device_name
from map_presets import COLOR_FIELDS, PRESETS, palette
from color_controls import ColorButton
from map_view import vendor_icon
from vendors import BADGES


class DesignerControls:
    def designer_toolbar(self):
        toolbar = QHBoxLayout()
        self.layout_mode = QComboBox()
        self.layout_mode.addItems(LAYOUTS)
        toolbar.addWidget(self.layout_mode)
        self.button(toolbar, 'Arrange', self.auto_arrange)
        self.undo_btn = self.button(toolbar, 'Undo layout', self.undo_layout)
        self.undo_btn.setEnabled(False)
        self.button(toolbar, 'Fit map', self.view.fit_nodes)
        self.button(toolbar, 'Readable layout', self.readable_layout)
        self.button(toolbar, 'Add section', self.add_section)
        self.button(toolbar, 'Device groups', self.edit_memberships)
        self.cable_btn = self.button(toolbar, 'Draw cable', self.add_link)
        self.cable_btn.setCheckable(True)
        self.view.endpoint_clicked.connect(self.cable_endpoint)
        self.view.section_action.connect(self.section_action)
        self.view.section_moved.connect(self.section_moved)
        self.view.cable_action.connect(self.cable_action)
        self.view.canvas_section.connect(self.add_section)
        self.view.canvas_note.connect(self.add_note)
        QShortcut(QKeySequence('Escape'), self, activated=self.cancel_cable)
        QShortcut(QKeySequence('Ctrl+Z'), self, activated=self.undo_layout)
        toolbar.addStretch()
        return toolbar

    @staticmethod
    def button(layout, label, callback):
        button = QPushButton(label)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def canvas_options(self, options):
        self.grid_check = QCheckBox('Grid')
        self.grid_check.setChecked(True)
        self.grid_check.toggled.connect(self.set_grid)
        self.snap_check = QCheckBox('Snap to grid')
        self.snap_check.toggled.connect(self.set_snap)
        options.addWidget(self.grid_check)
        options.addWidget(self.snap_check)
        options.addWidget(QLabel('Dotted gray = inferred gateway reachability'))
        options.addStretch()
        self.button(options, '−', lambda: self.view.zoom(1 / 1.2))
        self.zoom_value = QLabel('100%')
        self.view.zoom_changed.connect(lambda percent: self.zoom_value.setText(f'{percent}%'))
        options.addWidget(self.zoom_value)
        self.button(options, '+', lambda: self.view.zoom(1.2))
        self.button(options, 'Appearance', self.edit_appearance)
        self.button(options, 'Vendor icons', self.edit_vendor_icons)
        self.presentation = self.button(options, 'Canvas only', self.toggle_presentation)
        self.presentation.setCheckable(True)

    def readable_layout(self):
        self.layout_mode.setCurrentText('Grid')
        self.auto_arrange()

    def toggle_presentation(self, enabled):
        self.sidebar.setVisible(not enabled)
        QTimer.singleShot(0, self.view.fit_nodes)

    def edit_appearance(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Map appearance')
        layout = QVBoxLayout(dialog)
        preset = QComboBox()
        preset.addItems(PRESETS)
        preset.setCurrentText(self.view.options['preset'])
        layout.addWidget(QLabel('Map preset'))
        layout.addWidget(preset)
        controls = {}
        for key, label in [('status', 'Show ping status dots'), ('badges', 'Show vendor icons')]:
            check = QCheckBox(label)
            check.setChecked(self.view.options[key])
            controls[key] = check
            layout.addWidget(check)
        columns = QHBoxLayout()
        forms = [QFormLayout(), QFormLayout()]
        for form in forms:
            columns.addLayout(form)
        layout.addLayout(columns)
        layout.addWidget(QLabel('Show these fields on device cards'))
        fields_row = QHBoxLayout()
        fields = {}
        enabled = self.view.options.get('card_fields', ['IP address'])
        for field in CARD_FIELDS:
            check = QCheckBox(field)
            check.setChecked(field in enabled and (field != 'IP address' or self.view.options['address']))
            fields[field] = check
            fields_row.addWidget(check)
        layout.addLayout(fields_row)
        colors = {}
        base = palette(preset.currentText())
        overrides = self.view.options['colors']
        for index, (key, label) in enumerate(COLOR_FIELDS.items()):
            button = ColorButton(dialog, base[key], overrides.get(key, ''))
            colors[key] = button
            forms[index // 7].addRow(label, button)

        def reset_colors():
            defaults = palette(preset.currentText())
            for key, button in colors.items():
                button.set_color(defaults[key])

        preset.currentTextChanged.connect(reset_colors)
        self.button(layout, 'Reset to preset colors', reset_colors)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec():
            self.view.set_options(dict(
                self.view.options, preset=preset.currentText(),
                colors={key: button.value for key, button in colors.items() if button.value},
                address=fields['IP address'].isChecked(),
                card_fields=[field for field, check in fields.items() if check.isChecked()],
                **{key: widget.isChecked() for key, widget in controls.items()}))
            self.save_layout()

    def edit_vendor_icons(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Vendor icon library')
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Set a shared PNG or SVG for all devices using a vendor icon.'))
        vendor = QComboBox()
        vendor.addItems(sorted(BADGES))
        current = self.badge_edit.currentText()
        if current == 'Auto':
            current = self.devices.get(self.active_ip, {}).get('badge_hint', '')
        if current in BADGES:
            vendor.setCurrentText(current)
        layout.addWidget(vendor)
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setMinimumHeight(74)
        preview.setStyleSheet('background: #dde8f6; color: #182739; border-radius: 5px;')
        layout.addWidget(preview)
        icons = dict(self.view.options['vendor_icons'])

        def refresh():
            name = vendor.currentText()
            pixmap = vendor_icon(name, icons.get(name, ''))
            preview.clear()
            if pixmap.isNull():
                preview.setText(f'{name} · text label')
            else:
                preview.setPixmap(pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))

        def import_vendor():
            filename, _ = QFileDialog.getOpenFileName(dialog, 'Import vendor icon', '',
                                                      'Vendor icons (*.png *.svg)')
            if filename:
                try:
                    icons[vendor.currentText()] = read_icon(Path(filename))
                except (OSError, ValueError) as exc:
                    QMessageBox.warning(dialog, 'Import vendor icon', str(exc))
                    return
                refresh()

        def reset_vendor():
            icons.pop(vendor.currentText(), None)
            refresh()

        vendor.currentTextChanged.connect(refresh)
        refresh()
        row = QHBoxLayout()
        self.button(row, 'Import icon…', import_vendor)
        self.button(row, 'Restore default', reset_vendor)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec():
            self.view.set_options(dict(self.view.options, vendor_icons=icons))
            self.save_layout()

    def set_grid(self, checked):
        self.view.show_grid = checked
        self.view.viewport().update()
        self.save_layout()

    def set_snap(self, checked):
        self.view.snap = checked
        self.save_layout()

    def device_icon_controls(self, form):
        row = QHBoxLayout()
        self.button(row, 'Import…', self.import_icon)
        self.button(row, 'Reset', self.reset_icon)
        self.icon_size = QSpinBox()
        self.icon_size.setRange(16, 36)
        self.icon_size.setValue(26)
        row.addWidget(self.icon_size)
        form.addRow('Custom icon / size', row)

    def import_icon(self):
        if not self.active_ip:
            return
        filename, _ = QFileDialog.getOpenFileName(self, 'Import device icon', '',
                                                  'Device icons (*.png *.svg)')
        if filename:
            try:
                payload = read_icon(Path(filename))
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Import icon', str(exc))
                return
            self.devices[self.active_ip]['icon_png'] = payload
            self.update_device()

    def reset_icon(self):
        if self.active_ip:
            self.devices[self.active_ip].pop('icon_png', None)
            self.update_device()

    def edit_memberships(self):
        if not self.active_ip or not self.sections:
            self.status.setText('Select a device and add a section to manage memberships.')
            return
        ip = self.active_ip
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Sections for {device_name(ip, self.devices[ip])}')
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Set manual memberships. Section rules can also include this device.'))
        scroll = QScrollArea()
        content = QWidget()
        rows = QVBoxLayout(content)
        controls = []
        for section in self.sections:
            check = QCheckBox(section['name'])
            check.setChecked(ip in section['members'])
            rows.addWidget(check)
            controls.append((section, check))
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec():
            for section, check in controls:
                members = section['members']
                if check.isChecked() and ip not in members:
                    members.append(ip)
                elif not check.isChecked() and ip in members:
                    members.remove(ip)
            self.refresh_sections()
            self.save_layout()

    def section_by_id(self, section_id):
        return next(section for section in self.sections if section['id'] == section_id)

    def add_section(self, point=None):
        if not isinstance(point, QPointF):
            point = self.view.mapToScene(self.view.viewport().rect().center())
        if self.view.snap:
            point = self.view.snapped(point)
        section = edit_section(self, dict(id=uuid4().hex, name='New section',
                               description='', color='#5886bf', x=point.x(), y=point.y(),
                               w=430, h=305, collapsed=False, members=[], subnet='', kind=''),
                               TYPE_SYMBOL)
        if section:
            self.sections.append(section)
            self.refresh_sections(rebuild=True)
            self.save_layout()

    def add_note(self, point=None):
        if not isinstance(point, QPointF):
            point = self.view.mapToScene(self.view.viewport().rect().center())
        note = edit_note(self, dict(id=uuid4().hex, name='New annotation', note='Note',
                         description='', color='#658bc1', x=point.x(), y=point.y(),
                         w=360, h=180, collapsed=False, members=[], subnet='', kind='', locked=False))
        if note:
            self.sections.append(note)
            self.refresh_sections(rebuild=True)
            self.save_layout()

    def refresh_sections(self, rebuild=False):
        if rebuild:
            self.view.set_sections(self.sections)
            self.refresh_group_filter()
        visible = self.visible_devices()
        memberships = [(section, set(section_members(section, self.devices)))
                       for section in self.sections if not section.get('note')]
        for ip, item in self.view.items_by_ip.items():
            owner = next((s for s, members in reversed(memberships)
                          if ip in members and section_area(s).contains(item.pos())), None)
            item.setVisible(ip in visible and (not owner or not owner['collapsed']))
        self.view.update_links()

    def edit_link_visibility(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Show connections in this view')
        form = QFormLayout(dialog)
        choices = {}
        for kind in LINK_TYPES:
            check = QCheckBox()
            check.setChecked(kind in self.visible_link_types)
            choices[kind] = check
            form.addRow(kind, check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            self.visible_link_types = {kind for kind, check in choices.items() if check.isChecked()}
            self.view.visible_link_types = self.visible_link_types
            self.view.update_links()
            self.save_layout()

    def section_action(self, section_id, action):
        section = self.section_by_id(section_id)
        if action == 'Delete section':
            self.sections.remove(section)
        elif action == 'Lock / unlock':
            section['locked'] = not section.get('locked', False)
        elif action == 'Import backdrop…':
            filename, _ = QFileDialog.getOpenFileName(self, 'Import floor plan', '',
                                                      'Images (*.png *.svg)')
            if not filename:
                return
            try:
                section['backdrop'] = read_icon(Path(filename), 1200)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Import floor plan', str(exc))
                return
        elif action == 'Remove backdrop':
            section.pop('backdrop', None)
        elif action == 'Collapse / expand':
            section['collapsed'] = not section['collapsed']
        else:
            result = (edit_note(self, section) if section.get('note') else
                      edit_section(self, section, TYPE_SYMBOL))
            if result is None:
                return
            section.update(result)
        self.refresh_sections(rebuild=True)
        self.save_layout()

    def section_moved(self, section_id, delta):
        section = self.section_by_id(section_id)
        area = section_area(section)
        section['x'] += delta.x()
        section['y'] += delta.y()
        if not delta.isNull() and not section.get('note'):
            for ip in section_members(section, self.devices):
                data = self.devices[ip]
                if area.contains(QPointF(data['x'], data['y'])):
                    data['x'] += delta.x()
                    data['y'] += delta.y()
                    self.view.set_device_position(ip, data['x'], data['y'])
        self.refresh_sections()
        self.view.expand_bounds()
        self.save_layout()

    def assign_dropped_device(self, ip, x, y):
        for section in reversed(self.sections):
            if not section.get('note') and not section['collapsed'] and section_area(section).contains(QPointF(x, y)):
                if ip not in section['members']:
                    section['members'].append(ip)
                self.status.setText(f'Added to {section["name"]}. Existing group memberships are retained.')
                break
        self.refresh_sections()
        self.view.expand_bounds()

    def apply_positions(self, mode='Hierarchical', remember=False):
        if mode == 'Freeform':
            self.save_layout()
            return
        if remember:
            self.layout_undo = {
                'devices': {ip: [d['x'], d['y'], d.get('layout_custom', False)]
                            for ip, d in self.devices.items()},
                'sections': {s['id']: [s[k] for k in ('x', 'y', 'w', 'h')] for s in self.sections},
            }
            self.undo_btn.setEnabled(True)
        target = self.zone_positions() if mode == 'Sections / Zones' else positions(
            mode, self.devices, self.gateway)
        for ip, (x, y) in target.items():
            self.devices[ip].update(x=x, y=y, layout_custom=False)
            self.view.set_device_position(ip, x, y)
        self.refresh_sections(rebuild=True)
        self.view.fit_nodes()
        self.save_layout()

    def zone_positions(self):
        result = {}
        y = 0
        for section in self.sections:
            if section.get('note') or section.get('locked'):
                continue
            ids = [ip for ip in section_members(section, self.devices) if ip not in result]
            columns = max(1, int((section['w'] - 20) / 195))
            section.update(x=0, y=y, h=max(section['h'], 65 + 125 * (
                (len(ids) + columns - 1) // columns)))
            result.update(grid(ids, 105, y + 96, columns))
            y += (40 if section['collapsed'] and not ids else section['h']) + 35
        rest = sorted(set(self.devices) - result.keys(), key=lambda ip: tuple(map(int, ip.split('.'))))
        result.update(grid(rest, 105, y + 65))
        return result

    def auto_arrange(self):
        if self.devices:
            mode = self.layout_mode.currentText()
            self.apply_positions(mode, remember=True)
            self.status.setText(f'{mode} layout selected.')

    def undo_layout(self):
        if not self.layout_undo:
            return
        for section in self.sections:
            before = self.layout_undo['sections'].get(section['id'])
            if before:
                section.update(zip(('x', 'y', 'w', 'h'), before))
        for ip, (x, y, custom) in self.layout_undo['devices'].items():
            if ip in self.devices:
                self.devices[ip].update(x=x, y=y, layout_custom=custom)
                self.view.set_device_position(ip, x, y)
        self.layout_undo = None
        self.undo_btn.setEnabled(False)
        self.refresh_sections(rebuild=True)
        self.view.fit_nodes()
        self.save_layout()

    def add_link(self, checked):
        if not checked or len(self.devices) < 2:
            self.cancel_cable()
            if checked:
                self.status.setText('Discover two devices before drawing a cable.')
            return
        self.view.connecting = True
        self.view.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.status.setText('Click the first device on the canvas. Esc cancels.')

    def cancel_cable(self):
        self.cable_start = None
        self.view.connecting = False
        self.cable_btn.setChecked(False)
        self.view.viewport().unsetCursor()

    def cable_endpoint(self, ip):
        if not self.cable_start:
            self.cable_start = ip
            self.status.setText('Click the second device. Esc cancels.')
            return
        if ip == self.cable_start:
            return
        link = cable(self.cable_start, ip)
        self.cancel_cable()
        self.status.setText('Edit the logical cable to choose a monitored endpoint.')
        existing = next((i for i, entry in enumerate(self.links)
                         if {entry['a'], entry['b']} == {link['a'], link['b']}), None)
        if existing is not None:
            self.cable_action(existing, 'Edit cable')
            return
        result = edit_cable(self, link, lambda ip: device_name(ip, self.devices[ip]))
        if result:
            self.links.append(result)
            self.view.set_links(self.links)
            self.save_layout()

    def cable_action(self, index, action):
        if action == 'Delete cable':
            self.links.pop(index)
        else:
            result = edit_cable(self, self.links[index],
                                lambda ip: device_name(ip, self.devices.get(ip, {})))
            if result is None:
                return
            self.links[index] = result
        self.view.set_links(self.links)
        self.save_layout()


def section_area(section):
    return QRectF(section['x'], section['y'] + 40, section['w'], section['h'] - 40)


def read_icon(path, resolution=144):
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Choose an icon under 4 MB.')
    if path.suffix.lower() == '.svg':
        svg = QSvgRenderer(QByteArray(path.read_bytes()))
        if not svg.isValid():
            raise ValueError('The SVG could not be opened.')
        image = QImage(resolution, resolution, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        svg.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        painter = QPainter(image)
        svg.render(painter)
        painter.end()
    else:
        reader = QImageReader(str(path), b'png')
        size = reader.size()
        if not size.isValid() or max(size.width(), size.height()) > 4096:
            raise ValueError('Choose a PNG up to 4096 pixels wide or tall.')
        size.scale(resolution, resolution, Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(size)
        image = reader.read()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if image.isNull() or not image.save(buffer, 'PNG'):
        raise ValueError('The icon could not be read.')
    return bytes(data.toBase64()).decode('ascii')
