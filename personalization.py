"""Saved map views, bulk appearance and device card fields."""
from copy import deepcopy

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QToolButton,
                               QVBoxLayout)

from color_controls import ColorButton
from designer import section_members
from map_view import CARD_SIZES, TYPE_SYMBOL, device_name
from vendors import BADGES

FILTERS = ('All devices', 'No ping reply', 'Online', 'Not checked')


class Personalization:
    def view_controls(self, row):
        row.addWidget(QLabel('View'))
        self.view_picker = QComboBox()
        self.view_picker.setMinimumContentsLength(13)
        self.view_picker.addItem(self.active_view)
        self.view_picker.currentTextChanged.connect(self.switch_view)
        row.addWidget(self.view_picker)
        button = QToolButton()
        button.setText('Manage views')
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        menu.addAction('Duplicate current view…', self.duplicate_view)
        menu.addAction('Rename current view…', self.rename_view)
        menu.addAction('Delete current view…', self.delete_view)
        button.setMenu(menu)
        row.addWidget(button)
        self.status_filter = QComboBox()
        self.status_filter.addItems(FILTERS)
        self.status_filter.currentTextChanged.connect(self.change_view_filter)
        row.addWidget(self.status_filter)
        self.group_filter = QComboBox()
        self.group_filter.addItem('All sections', '')
        self.group_filter.currentIndexChanged.connect(self.change_view_filter)
        row.addWidget(self.group_filter)
        self.button(row, 'Bulk style', self.bulk_style)

    def capture_view(self):
        center = self.view.mapToScene(self.view.viewport().rect().center())
        self.saved_views[self.active_view] = {
            'positions': {ip: [d['x'], d['y'], d.get('layout_custom', False)]
                          for ip, d in self.devices.items()},
            'section_positions': {s['id']: [s[k] for k in ('x', 'y', 'w', 'h', 'collapsed')]
                                  for s in self.sections},
            'appearance': deepcopy({k: v for k, v in self.view.options.items()
                                    if k != 'vendor_icons'}),
            'layout': self.layout_mode.currentText(),
            'grid': self.grid_check.isChecked(), 'snap': self.snap_check.isChecked(),
            'inferred': self.logical_links.isChecked(), 'undo': deepcopy(self.layout_undo),
            'canvas_only': self.presentation.isChecked(),
            'status': self.status_filter.currentText(), 'group': self.group_filter.currentData(),
            'camera': [self.view.transform().m11(), center.x(), center.y()],
            'link_types': list(self.visible_link_types),
        }

    def refresh_view_picker(self):
        self.view_picker.blockSignals(True)
        self.view_picker.clear()
        self.view_picker.addItems(self.saved_views or [self.active_view])
        self.view_picker.setCurrentText(self.active_view)
        self.view_picker.blockSignals(False)

    def switch_view(self, name):
        if not name or name == self.active_view:
            return
        self.capture_view()
        self.active_view = name
        self.apply_view(self.saved_views[name])
        self.save_layout()

    def apply_view(self, snapshot):
        loading = self.loading
        self.loading = True
        try:
            self.cancel_cable()
            self.layout_mode.setCurrentText(snapshot.get('layout', 'Hierarchical'))
            self.grid_check.setChecked(snapshot.get('grid', True))
            self.snap_check.setChecked(snapshot.get('snap', False))
            self.logical_links.setChecked(snapshot.get('inferred', False))
            self.layout_undo = deepcopy(snapshot.get('undo'))
            self.undo_btn.setEnabled(bool(self.layout_undo))
            self.view.set_options(dict(deepcopy(snapshot.get('appearance', {})),
                                       vendor_icons=self.view.options['vendor_icons']))
            self.status_filter.setCurrentText(snapshot.get('status', FILTERS[0]))
            self.visible_link_types = set(snapshot.get('link_types', self.visible_link_types))
            self.view.visible_link_types = self.visible_link_types
            self.refresh_group_filter(snapshot.get('group', ''))
            self.presentation.setChecked(snapshot.get('canvas_only', False))
            self.sidebar.setVisible(not self.presentation.isChecked())
            for ip, (x, y, custom) in snapshot.get('positions', {}).items():
                if ip in self.devices:
                    self.devices[ip].update(x=x, y=y, layout_custom=custom)
                    self.view.set_device_position(ip, x, y)
            for section in self.sections:
                values = snapshot.get('section_positions', {}).get(section['id'])
                if values:
                    section.update(zip(('x', 'y', 'w', 'h', 'collapsed'), values))
            self.refresh_sections(rebuild=True)
            self.update_table()
            self.view.expand_bounds()
            camera = snapshot.get('camera')
            if camera:
                self.view.restore_camera(*camera)
        finally:
            self.loading = loading

    def ask_view_name(self, title, suggestion):
        name, ok = QInputDialog.getText(self, title, 'View name', text=suggestion)
        name = name.strip()
        if ok and name and name not in self.saved_views:
            return name
        if ok and name in self.saved_views:
            self.status.setText('A view with that name already exists.')
        return ''

    def duplicate_view(self):
        self.capture_view()
        name = self.ask_view_name('Duplicate view', self.active_view + ' copy')
        if name:
            self.saved_views[name] = deepcopy(self.saved_views[self.active_view])
            self.active_view = name
            self.refresh_view_picker()
            self.save_layout()

    def rename_view(self):
        self.capture_view()
        name = self.ask_view_name('Rename view', self.active_view)
        if name:
            self.saved_views[name] = self.saved_views.pop(self.active_view)
            self.active_view = name
            self.refresh_view_picker()
            self.save_layout()

    def delete_view(self):
        if len(self.saved_views) < 2:
            self.status.setText('Keep at least one view.')
            return
        name = self.active_view
        if QMessageBox.question(self, 'Delete view', f'Delete the saved view “{name}”?') != QMessageBox.StandardButton.Yes:
            return
        self.saved_views.pop(name)
        self.active_view = next(iter(self.saved_views))
        self.refresh_view_picker()
        self.apply_view(self.saved_views[self.active_view])
        self.save_layout()

    def refresh_group_filter(self, selection=None):
        selected = self.group_filter.currentData() if selection is None else selection
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem('All sections', '')
        for section in self.sections:
            if not section.get('note'):
                self.group_filter.addItem(section['name'], section['id'])
        self.group_filter.setCurrentIndex(max(0, self.group_filter.findData(selected)))
        self.group_filter.blockSignals(False)

    def change_view_filter(self):
        if not self.loading:
            self.refresh_sections()
            self.save_layout()

    def visible_devices(self):
        selected = self.group_filter.currentData()
        candidates = set(self.devices)
        if selected:
            section = next((s for s in self.sections if s['id'] == selected), None)
            if section:
                candidates.intersection_update(section_members(section, self.devices))
        status = self.status_filter.currentText()
        if status != FILTERS[0]:
            online = dict(zip(FILTERS[1:], (False, True, None)))[status]
            candidates = {ip for ip in candidates if self.devices[ip].get('online') is online}
        return candidates

    def bulk_style(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Bulk device styling')
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Select devices from the current view or choose a section.'))
        group = QComboBox()
        group.addItem('Current view', None)
        group.addItem('All devices', '')
        for section in self.sections:
            if not section.get('note'):
                group.addItem(section['name'], section['id'])
        layout.addWidget(group)
        devices = QListWidget()
        layout.addWidget(devices)

        def populate():
            selected = group.currentData()
            if selected is None:
                ips = self.visible_devices()
            elif selected:
                ips = section_members(self.section_by_id(selected), self.devices)
            else:
                ips = self.devices
            devices.clear()
            for ip in sorted(ips):
                item = QListWidgetItem(f'{device_name(ip, self.devices[ip])} · {ip}', devices)
                item.setData(Qt.ItemDataRole.UserRole, ip)
                item.setCheckState(Qt.CheckState.Unchecked)

        def check_all(state):
            for index in range(devices.count()):
                devices.item(index).setCheckState(state)

        group.currentIndexChanged.connect(populate)
        populate()
        self.button(layout, 'Check all', lambda: check_all(Qt.CheckState.Checked))
        self.button(layout, 'Uncheck all', lambda: check_all(Qt.CheckState.Unchecked))
        form = QFormLayout()
        choices = {}
        for key, label, options in (
            ('card_size', 'Card size', CARD_SIZES),
            ('type', 'Role icon', TYPE_SYMBOL),
            ('badge', 'Vendor icon', ('Auto', 'None', *sorted(BADGES))),
        ):
            box = QComboBox()
            box.addItems(['Keep existing', *options])
            choices[key] = box
            form.addRow(label, box)
        colors = {}
        for key, label, base in (('fill', 'Fill', 'card'), ('accent', 'Border', 'border'),
                                  ('text_color', 'Text', 'text')):
            button = ColorButton(dialog, self.view.style[base])
            colors[key] = button
            form.addRow(label, button)
        reset = QCheckBox('Reset selected cards to map colors')
        form.addRow(reset)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec():
            updates = {key: box.currentText() for key, box in choices.items() if box.currentIndex()}
            updates.update({key: button.value for key, button in colors.items()
                            if button.value or reset.isChecked()})
            if 'type' in updates:
                updates['type_custom'] = True
            selected = [devices.item(i).data(Qt.ItemDataRole.UserRole) for i in range(devices.count())
                        if devices.item(i).checkState() == Qt.CheckState.Checked]
            self.apply_bulk_style(selected, updates)

    def apply_bulk_style(self, selected, updates):
        if not selected or not updates:
            return
        for ip in selected:
            self.devices[ip].update(updates)
            self.view.add_device(ip, self.devices[ip])
        self.refresh_sections()
        self.update_table()
        if self.active_ip in selected:
            self.select_device(self.active_ip)
        self.save_layout()
        self.status.setText(f'Updated {len(selected)} device cards.')
