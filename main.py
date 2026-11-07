"""NetworkMapper v0.12 — Visual Map Designer."""
import ipaddress
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QTimer, QStandardPaths
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QHBoxLayout,
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSplitter,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from color_controls import ColorButton

from scanner import MonitorWorker, ScanWorker, HostnameWorker, IdentityWorker
from map_view import NetworkView, TYPE_SYMBOL, device_name
from identity import determine_identity, default_gateway
from local_network import detect_local_network

from designer import LINK_TYPES, load_map, save_map
from designer_controls import DesignerControls
from personalization import Personalization
from map_export import MapExport
from map_view import CARD_SIZES
from vendors import BADGES

LEGACY_FILE = Path.home() / 'Documents' / 'NetworkMapper' / 'networkmap.json'


def map_path():
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    return Path(base) / 'networkmap.json'


class MainWindow(QMainWindow, DesignerControls, Personalization, MapExport):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('NetworkMapper v0.12 | DSR Technologies')
        self.resize(1420, 850)
        self.devices = {}
        self.links = []
        self.sections = []
        self.saved_views = {}
        self.active_view = 'Main map'
        self.visible_link_types = set(LINK_TYPES)
        self.layout_undo = None
        self.cable_start = None
        self.card_colors = {}
        self.save_path = map_path()
        self.can_save = False
        self.loading = True
        self.closing = False
        self.pending_update = QTimer(self)
        self.pending_update.setSingleShot(True)
        self.pending_update.setInterval(120)
        self.pending_update.timeout.connect(self.update_table)
        self.active_ip = None
        self.scan_worker = None
        self.monitor_worker = None
        self.hostname_worker = None
        self.identity_worker = None
        self.local_config = detect_local_network()
        self.gateway = (self.local_config or {}).get('gateway') or default_gateway()
        self.fresh_layout = True
        self.monitor_interval = QTimer(self)
        self.monitor_interval.setInterval(10000)
        self.monitor_interval.timeout.connect(self.refresh_pings)
        self.monitor_interval.start()

        root = QWidget()
        layout = QVBoxLayout(root)
        header = QLabel('NETWORK MAPPER   /   v0.12')
        header.setObjectName('header')
        title_row = QHBoxLayout()
        title_row.addWidget(header, 1)
        logo = QLabel()
        logo.setAccessibleName('DSR Technologies')
        logo.setToolTip('DSR Technologies')
        original = QPixmap(str(Path(__file__).resolve().parent / 'assets' / 'dsr-technologies.png'))
        if not original.isNull():
            # Frame the artwork in the header; the bundled PNG stays byte-for-byte intact.
            width, height = original.width(), original.height()
            framed = original.copy(0, int(height * .275), width, int(height * .465))
            logo.setPixmap(framed.scaled(130, 56, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
            title_row.addWidget(logo)
        layout.addLayout(title_row)
        toolbar = QHBoxLayout()
        self.subnet = QLineEdit((self.local_config or {}).get('subnet') or '192.168.1.0/24')
        self.local_btn = QPushButton('My network')
        self.local_btn.clicked.connect(self.use_local_network)
        self.scan_btn = QPushButton('Scan')
        self.scan_btn.setObjectName('scan')
        self.scan_btn.clicked.connect(self.start_scan)
        self.resolve_btn = QPushButton('Refresh names')
        self.resolve_btn.clicked.connect(lambda: self.resolve_hostnames())
        toolbar.addWidget(QLabel('Subnet'))
        toolbar.addWidget(self.subnet, 1)
        toolbar.addWidget(self.local_btn)
        toolbar.addWidget(self.scan_btn)
        toolbar.addWidget(self.resolve_btn)
        self.deep_btn = self.button(toolbar, 'Deep discovery', self.deep_discover)
        self.deep_btn.setToolTip('Look for devices that block ping using selected TCP services and the local neighbor cache.')
        layout.addLayout(toolbar)
        options = QHBoxLayout()
        self.logical_links = QCheckBox('Show inferred gateway links')
        self.logical_links.toggled.connect(self.refresh_logical_links)
        options.addWidget(self.logical_links)
        layout.addLayout(options)

        content = QSplitter(Qt.Orientation.Horizontal)
        self.view = NetworkView()
        self.view.device_selected.connect(self.select_device)
        self.view.device_moved.connect(self.moved)
        self.canvas_options(options)
        layout.insertLayout(2, self.designer_toolbar())
        view_row = QHBoxLayout()
        self.view_controls(view_row)
        self.button(view_row, 'Connections', self.edit_link_visibility)
        self.button(view_row, 'Add annotation', self.add_note)
        self.button(view_row, 'Export map…', self.export_map)
        view_row.addStretch()
        layout.addLayout(view_row)
        content.addWidget(self.view)
        sidebar = self.sidebar = QWidget()
        sl = QVBoxLayout(sidebar)
        sl.addWidget(QLabel('DISCOVERED DEVICES'))
        self.device_filter = QLineEdit()
        self.device_filter.setPlaceholderText('Filter by name, IP, vendor, or MAC')
        self.device_filter.textChanged.connect(self.update_table)
        sl.addWidget(self.device_filter)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['IP', 'Name', 'Hostname', 'MAC', 'Identification', 'Confidence', 'Ping'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 150)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self.from_table)
        self.table.cellDoubleClicked.connect(self.focus_table_device)
        sl.addWidget(self.table, 2)
        sl.addWidget(QLabel('DEVICE DETAILS'))
        self.details_ip = QLabel('Select a device')
        self.hostname_label = QLabel('Not resolved')
        self.hostname_label.setTextFormat(Qt.TextFormat.PlainText)
        self.hostname_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.name_edit = QLineEdit()
        self.type_edit = QComboBox()
        self.type_edit.addItems(TYPE_SYMBOL.keys())
        self.badge_edit = QComboBox()
        self.badge_edit.addItems(['Auto', 'None', *sorted(BADGES)])
        self.card_color_btn = QPushButton('Edit colors…')
        self.card_color_btn.clicked.connect(self.edit_card_colors)
        self.ping_label = QLabel('—')
        form = QFormLayout()
        form.addRow('Address', self.details_ip)
        form.addRow('Name', self.name_edit)
        form.addRow('Hostname', self.hostname_label)
        self.mac_label = QLabel('Not known')
        self.mac_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.service_label = QLabel('—')
        self.service_label.setTextFormat(Qt.TextFormat.PlainText)
        self.service_label.setWordWrap(True)
        form.addRow('MAC', self.mac_label)
        form.addRow('Web service', self.service_label)
        self.source_label = QLabel('—')
        self.identity_label = QLabel('Unknown')
        self.identity_label.setWordWrap(True)
        self.evidence_label = QLabel('—')
        self.evidence_label.setTextFormat(Qt.TextFormat.PlainText)
        self.evidence_label.setWordWrap(True)
        form.addRow('Found via', self.source_label)
        form.addRow('Suggested type', self.identity_label)
        form.addRow('Evidence', self.evidence_label)
        form.addRow('Icon type', self.type_edit)
        form.addRow('Vendor icon', self.badge_edit)
        form.addRow('Card colors', self.card_color_btn)
        self.card_size = QComboBox()
        self.card_size.addItems(CARD_SIZES)
        form.addRow('Card size', self.card_size)
        self.card_metadata = {}
        for key, label in [('model', 'Model'), ('location', 'Location'), ('tags', 'Tags')]:
            field = QLineEdit()
            field.setMaxLength(100)
            self.card_metadata[key] = field
            form.addRow(label, field)
        self.device_icon_controls(form)
        form.addRow('Ping', self.ping_label)
        details = QWidget()
        details.setLayout(form)
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setWidget(details)
        sl.addWidget(detail_scroll, 2)
        save_btn = QPushButton('Save device changes')
        save_btn.clicked.connect(self.update_device)
        ping_btn = QPushButton('Ping selected now')
        ping_btn.clicked.connect(self.ping_selected)
        sl.addWidget(save_btn)
        sl.addWidget(ping_btn)
        content.addWidget(sidebar)
        content.setSizes([960, 390])
        layout.addWidget(content)
        self.status = QLabel('Ready. Local network detection is a suggestion. Scan only authorized networks.')
        layout.addWidget(self.status)
        self.setCentralWidget(root)
        self.setStyleSheet('''
          QMainWindow, QWidget { background: #101827; color: #e3eaf5; font: 13px "Segoe UI"; }
          #header { font-size: 24px; font-weight: bold; padding: 8px 0; }
          QLineEdit, QComboBox, QTableWidget { background: #1e2b3e; color: #e3eaf5; border: 1px solid #42536b; padding: 6px; }
          QPushButton { background: #2659ae; color: white; border: 0; border-radius: 5px; padding: 9px; }
          #scan { background: #167f82; font-weight: bold; }
          QPushButton:checked { background: #117d84; }
          QPushButton:hover { background: #3774d4; }
          QPushButton:disabled { background: #404b60; }
          QHeaderView::section { background: #26384e; color: #e3eaf5; padding: 6px; }
        ''')
        self.load_layout()
        self.loading = False
        QTimer.singleShot(0, self.restore_initial_camera)

    def restore_initial_camera(self):
        camera = self.saved_views.get(self.active_view, {}).get('camera')
        if camera:
            self.view.restore_camera(*camera)
        else:
            self.view.fit_nodes()

    def edit_card_colors(self):
        if not self.active_ip:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Device card colors')
        form = QFormLayout(dialog)
        fields = {'fill': ('Fill', 'card'), 'accent': ('Border', 'border'),
                  'text_color': ('Name, address, and icon', 'text')}
        controls = {}
        for key, (label, base) in fields.items():
            controls[key] = ColorButton(dialog, self.view.style[base], self.card_colors.get(key, ''))
            form.addRow(label, controls[key])

        def reset():
            for key, button in controls.items():
                button.set_color(self.view.style[fields[key][1]])

        clear = QPushButton('Reset to map colors')
        clear.clicked.connect(reset)
        form.addRow(clear)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            self.card_colors = {key: button.value for key, button in controls.items()}
            self.card_color_btn.setText('Edit colors… (custom)' if any(self.card_colors.values())
                                        else 'Edit colors…')

    def focus_table_device(self, row, column):
        item = self.table.item(row, 0)
        if item:
            self.view.focus_device(item.text())

    def use_local_network(self):
        config = detect_local_network()
        if not config:
            QMessageBox.information(self, "Local network", "Could not identify a private IPv4 /24 or smaller network. Enter a subnet manually.")
            return
        self.local_config = config
        self.gateway = config["gateway"]
        self.subnet.setText(config["subnet"])
        self.status.setText(f"Detected {config['interface']}: {config['subnet']} (gateway {self.gateway})")
        self.refresh_logical_links()

    def refresh_logical_links(self):
        # L3 gateway is not proof of a physical cable or switch-port attachment.
        gateway = self.gateway if self.gateway in self.devices else None
        if gateway:
            inferred = [[gateway, ip] for ip in self.devices if ip != gateway]
        else:
            inferred = []
        self.view.set_inferred_links(inferred, self.logical_links.isChecked())

    def get_network(self):
        try:
            n = ipaddress.ip_network(self.subnet.text().strip(), strict=False)
            if n.version != 4 or n.num_addresses > 256 or not n.is_private:
                raise ValueError('Select an authorized, private IPv4 subnet of /24 or smaller.')
            return n
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid subnet', str(exc))
            return None

    def start_scan(self):
        n = self.get_network()
        if n is None or (self.scan_worker and self.scan_worker.isRunning()):
            return
        self.scan_btn.setEnabled(False)
        self.deep_btn.setEnabled(False)
        self.fresh_layout = not bool(self.devices)
        self.status.setText(f'Scanning {n} ...')
        self.scan_worker = ScanWorker(str(n))
        self.scan_worker.found.connect(self.found)
        self.scan_worker.progress.connect(lambda done, total: self.status.setText(f'Scanning {n}: {done}/{total} checked'))
        self.scan_worker.scan_done.connect(self.scan_complete)
        self.scan_worker.start()

    def found(self, ip, latency):
        if ip in self.devices:
            data = self.devices[ip]
            data['online'] = True
            data['latency'] = latency
        else:
            self.add_discovered(ip, True, latency)
        self.refresh_identity(ip)
        self.pending_update.start()

    def add_discovered(self, ip, online=None, latency=None):
        occupied = [item.sceneBoundingRect() for item in self.view.items_by_ip.values()]
        i = 0
        while any(rect.adjusted(-80, -45, 80, 45).contains(
                  QPointF((i % 6) * 195 - 490, (i // 6) * 125 - 300)) for rect in occupied):
            i += 1
        self.devices[ip] = {'name': '', 'type': 'Unknown', 'online': online, 'latency': latency,
                            'x': float((i % 6) * 195 - 490), 'y': float((i // 6) * 125 - 300)}

    def scan_complete(self):
        self.scan_btn.setEnabled(True)
        self.deep_btn.setEnabled(not (self.identity_worker and self.identity_worker.isRunning()))
        self.status.setText(f'Scan complete. {sum(d.get("online") is True for d in self.devices.values())} known responsive devices.')
        if self.closing:
            return
        if self.fresh_layout and self.devices:
            self.apply_positions(self.layout_mode.currentText())
        else:
            self.refresh_sections()
            self.view.expand_bounds()
        self.update_table()
        self.save_layout()
        self.refresh_logical_links()
        self.resolve_hostnames()

    def deep_discover(self):
        network = self.get_network()
        if network is None:
            return
        self.discover_identity([str(ip) for ip in network.hosts()])

    def discover_identity(self, subnet_ips=None):
        if self.closing or (self.identity_worker and self.identity_worker.isRunning()):
            return
        ips = subnet_ips if subnet_ips is not None else list(self.devices)
        if not ips:
            return
        deep = subnet_ips is not None
        self.deep_btn.setEnabled(False)
        self.identity_worker = IdentityWorker(ips, deep=deep)
        if deep:
            self.identity_worker.initial_map = not self.devices
            self.scan_btn.setEnabled(False)
            self.status.setText(f'Deep discovery: checking selected services on {len(ips)} addresses…')
        self.identity_worker.identified.connect(self.identity_found)
        self.identity_worker.done.connect(self.identity_complete)
        self.identity_worker.start()

    def identity_found(self, ip, mac, web_title, ports):
        if ip not in self.devices:
            if not (mac or web_title or ports):
                return
            self.add_discovered(ip)
        data = self.devices[ip]
        if mac:
            data['mac'] = mac
        if ports is not None:
            data['web_title'] = web_title
            data['ports'] = ports
        self.refresh_identity(ip)
        if ip == self.active_ip:
            self.update_evidence(ip)
        self.pending_update.start()

    def identity_complete(self, count):
        if self.closing:
            return
        self.deep_btn.setEnabled(not (self.scan_worker and self.scan_worker.isRunning()))
        if self.identity_worker.deep:
            self.scan_btn.setEnabled(True)
            if self.identity_worker.initial_map and self.devices:
                self.apply_positions(self.layout_mode.currentText())
            self.resolve_hostnames(refresh_identity=False)
        self.refresh_sections()
        self.refresh_logical_links()
        self.view.expand_bounds()
        self.save_layout()
        self.status.setText(f'Device discovery complete · {len(self.devices)} mapped · {count} MAC addresses')

    def resolve_hostnames(self, refresh_identity=True):
        if self.closing:
            return
        if not self.devices or (self.hostname_worker and self.hostname_worker.isRunning()):
            return
        # Resolve known map entries without touching user-defined display names.
        self.resolve_btn.setEnabled(False)
        self.hostname_worker = HostnameWorker(list(self.devices))
        self.hostname_worker.resolved.connect(self.hostname_resolved)
        self.hostname_worker.done.connect(self.hostnames_complete)
        self.hostname_worker.start()
        if refresh_identity:
            self.discover_identity()

    def hostname_resolved(self, ip, hostname, source):
        if ip not in self.devices:
            return
        data = self.devices[ip]
        if not hostname:
            return
        data['hostname'] = hostname
        data['hostname_source'] = source
        self.refresh_identity(ip)
        if ip == self.active_ip:
            self.hostname_label.setText(hostname)
            self.source_label.setText(source)
        self.update_table()
        self.save_layout()

    def hostnames_complete(self, note):
        self.resolve_btn.setEnabled(True)
        named = sum(bool(d.get('hostname')) for d in self.devices.values())
        self.status.setText(f'Hostname lookup complete: {named} of {len(self.devices)} resolved (DNS / NetBIOS / mDNS). ' + (note or 'Unnamed devices may not advertise their names.'))

    def refresh_identity(self, ip):
        if ip not in self.devices:
            return
        d = self.devices[ip]
        hint = determine_identity(ip, d, self.gateway)
        d.update(hint)
        if not d.get('type_custom'):
            # Older maps may have manual types without a flag; preserve them.
            if d.get('type', 'Unknown') == 'Unknown' or d.get('type') == d.get('auto_type'):
                d['type'] = hint['suggested_type']
                d['auto_type'] = hint['suggested_type']
        # Do not overwrite names typed by the user, ever.
        self.view.add_device(ip, d)

    def update_table(self):
        selected = self.active_ip
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        query = self.device_filter.text().strip().casefold()
        for ip in sorted(self.devices, key=ipaddress.ip_address):
            d = self.devices[ip]
            match = (ip, device_name(ip, d), d.get('mac', ''), d.get('vendor_hint', ''),
                     d.get('badge_hint', ''), d.get('hostname', ''), d.get('badge', ''), d.get('location', ''), d.get('tags', ''), d.get('model', ''))
            if query and not any(query in str(value).casefold() for value in match):
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate([ip, device_name(ip, d), d.get('hostname') or '—',
                                    d.get('mac') or '—', d.get('vendor_hint') or d.get('service_hint') or '—',
                                    (d.get('suggested_type', 'Unknown') + ' · ' + d.get('confidence', 'Unknown')), 
                                    self.ping_text(d)]):
                self.table.setItem(r, c, QTableWidgetItem(str(v)))
            if ip == selected:
                self.table.selectRow(r)
        self.table.blockSignals(False)

    def from_table(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            item = self.table.item(rows[0].row(), 0)
            if item:
                self.select_device(item.text())

    def select_device(self, ip):
        self.active_ip = ip
        d = self.devices[ip]
        self.details_ip.setText(ip)
        self.name_edit.setText(d.get('name') or '')
        self.update_evidence(ip)
        self.type_edit.setCurrentText(d.get('type', 'Unknown'))
        self.icon_size.setValue(d.get('icon_size', 26))
        self.badge_edit.setCurrentText(d.get('badge', 'Auto'))
        self.card_size.setCurrentText(d.get('card_size', 'Standard'))
        for key, field in self.card_metadata.items():
            field.setText(d.get(key, ''))
        self.card_colors = {key: d.get(key, '') for key in ('fill', 'accent', 'text_color')}
        self.card_color_btn.setText('Edit colors… (custom)' if any(self.card_colors.values())
                                    else 'Edit colors…')
        for item in self.view.items_by_ip.values():
            item.setSelected(item.ip == ip)
        self.ping_label.setText(self.ping_text(d))

    def update_evidence(self, ip):
        data = self.devices[ip]
        self.hostname_label.setText(data.get('hostname') or 'Not resolved')
        self.mac_label.setText(data.get('mac') or 'Not known')
        self.service_label.setText(data.get('service_hint') or '—')
        self.source_label.setText(data.get('hostname_source') or '—')
        self.identity_label.setText(f"{data.get('suggested_type', 'Unknown')} ({data.get('confidence', 'Unknown')})")
        evidence = [data.get('reason')]
        if data.get('vendor_hint'):
            evidence.append(f"{data['vendor_hint']} · {data.get('vendor_source', '')}")
        ports = data.get('ports') or []
        if ports:
            evidence.append('TCP ' + ', '.join(map(str, sorted(ports))))
        self.evidence_label.setText('  |  '.join(filter(None, evidence)) or '—')
        self.evidence_label.setToolTip('• ' + '\n• '.join(filter(None, evidence)))

    @staticmethod
    def ping_text(d):
        if d.get('online') is True:
            latency = d.get('latency')
            if latency is None:
                return 'Online'
            state = 'High latency' if latency >= 150 else 'Online'
            return f'{state} · {latency:g} ms'
        return 'No ping reply' if d.get('online') is False else 'Not checked'

    def moved(self, ip, x, y):
        self.devices[ip]['x'] = x
        self.devices[ip]['y'] = y
        self.devices[ip]['layout_custom'] = True
        self.assign_dropped_device(ip, x, y)
        self.save_layout()

    def update_device(self):
        if not self.active_ip:
            return
        d = self.devices[self.active_ip]
        d['name'] = self.name_edit.text().strip()[:50]
        d['type'] = self.type_edit.currentText()
        d['type_custom'] = True
        d['icon_size'] = self.icon_size.value()
        d['badge'] = self.badge_edit.currentText()
        d.update(self.card_colors)
        d['card_size'] = self.card_size.currentText()
        d.update({key: field.text().strip() for key, field in self.card_metadata.items()})
        self.refresh_sections()
        self.view.add_device(self.active_ip, d)
        self.update_table()
        self.save_layout()

    def refresh_pings(self):
        if not self.devices or (self.monitor_worker and self.monitor_worker.isRunning()) or (self.scan_worker and self.scan_worker.isRunning()):
            return
        self.monitor_worker = MonitorWorker(self.devices.keys())
        self.monitor_worker.checked.connect(self.checked)
        self.monitor_worker.start()

    def ping_selected(self):
        if self.active_ip and not (self.monitor_worker and self.monitor_worker.isRunning()):
            self.monitor_worker = MonitorWorker([self.active_ip])
            self.monitor_worker.checked.connect(self.checked)
            self.monitor_worker.start()

    def checked(self, ip, latency):
        if ip not in self.devices:
            return
        d = self.devices[ip]
        d['online'] = latency is not None
        d['latency'] = latency
        self.view.add_device(ip, d)
        if ip == self.active_ip:
            self.ping_label.setText(self.ping_text(d))
        self.pending_update.start()
        if self.status_filter.currentIndex():
            self.refresh_sections()

    def save_layout(self):
        if self.loading or not self.can_save:
            return
        self.capture_view()
        devices = {ip: {key: value for key, value in data.items()
                        if key not in ('online', 'latency')} for ip, data in self.devices.items()}
        try:
            save_map(self.save_path, {
                'subnet': self.subnet.text(), 'devices': devices, 'links': self.links,
                'sections': self.sections, 'layout': self.layout_mode.currentText(),
                'undo': self.layout_undo, 'grid': self.grid_check.isChecked(),
                'snap': self.snap_check.isChecked(), 'appearance': self.view.options,
                'views': self.saved_views, 'active_view': self.active_view,
            })
        except (OSError, ValueError) as exc:
            self.status.setText(f'Could not save map: {exc}')

    def load_layout(self):
        source = self.save_path if self.save_path.exists() else LEGACY_FILE
        if not source.exists():
            self.can_save = True
            return
        try:
            d = load_map(source)
            self.subnet.setText(d.get('subnet', self.subnet.text()))
            self.devices = d.get('devices', {})
            self.fresh_layout = False
            self.links = d.get('links', [])
            self.sections = d.get('sections', [])
            self.layout_undo = d.get('undo')
            self.undo_btn.setEnabled(bool(self.layout_undo))
            self.layout_mode.setCurrentText(d.get('layout', 'Hierarchical'))
            self.grid_check.setChecked(d.get('grid', True))
            self.snap_check.setChecked(d.get('snap', False))
            self.view.set_options(d.get('appearance', {}))
            for ip, info in self.devices.items():
                info.setdefault('x', 0)
                info.setdefault('y', 0)
                info.update(online=None, latency=None)
                self.refresh_identity(ip)
            self.view.set_links(self.links)
            self.refresh_sections(rebuild=True)
            self.refresh_logical_links()
            self.update_table()
            self.saved_views = d.get('views', {})
            active = d.get('active_view')
            if active in self.saved_views:
                self.active_view = active
                self.apply_view(self.saved_views[active])
            self.refresh_view_picker()
            self.can_save = True
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            self.status.setText(f'Could not load saved map. Saving is disabled: {exc}')

    def closeEvent(self, event):
        if not self.closing:
            self.closing = True
            self.monitor_interval.stop()
            self.save_layout()
        workers = (self.scan_worker, self.monitor_worker, self.hostname_worker, self.identity_worker)
        if any(worker and worker.isRunning() for worker in workers):
            event.ignore()
            self.setEnabled(False)
            self.status.setText('Finishing background checks…')
            QTimer.singleShot(150, self.close)
            return
        self.save_layout()
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName('NetworkMapper')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
