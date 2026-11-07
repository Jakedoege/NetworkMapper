NetworkMapper v0.12 — Visual Map Designer
DSR Technologies

RUN ON WINDOWS
Extract the ZIP and double-click NetworkMapper.exe inside the NetworkMapper
folder. Keep the _internal folder beside the EXE. Click Scan to discover
responsive devices on the suggested local subnet. Deep discovery also
checks selected TCP services and the Windows neighbor cache for devices
that may not answer ping. A cached MAC can be stale. A responding TCP
service identifies an endpoint independently of ICMP status.
Vendor hints come from observed management pages or selected IEEE MA-L
MAC prefix assignments bundled with the app. A registered interface
vendor may differ from the brand of the device.

DESIGN THE MAP
- Duplicate the current map under Manage views. Each view remembers
  positions, zoom, canvas options, section/status filters, and connection
  visibility. Device inventory, names, card styles, and cables are shared.
- Bulk style applies sizes, role icons, vendor icons, and colors to
  checked devices. In Appearance, choose which fields appear on cards.
  Edit model, location, tags, and size in Device details, then save.
- Use Add annotation for notes, titles, legends, and floor plans.
  Right-click a floor plan to import a PNG or SVG backdrop, or lock it.
- Set Ethernet, Fiber, or Wi-Fi and optional port labels in a cable's
  properties. Connections toggles types independently in each view.
- Export map creates a PNG or PDF from the whole visible view. The
  privacy option substitutes device numbers and hides custom labels,
  annotation text, and imported artwork. Review the file before sharing.
- Start with Readable layout for a compact grid. Undo layout restores
  your previous positions. Canvas only gives the map the whole window.
- Open Appearance to edit the background, grid, card fill and borders,
  text, inferred links, and ping status colors. Pick a preset or use
  Reset to preset colors to start again. You can hide IP details, ping
  dots, or vendor icons. Use + or - to zoom, or double-click a table row
  to zoom to that card.
- Select Auto, None, or a named vendor icon per device. An automatic
  Proxmox virtual interface has a VM NIC tag, while a device with
  Proxmox management evidence gets the Proxmox logo.
- Open Vendor icons to preview the library or import a shared PNG or
  SVG for any listed vendor. It applies to every card using that vendor.
  See BRAND-ASSETS.txt for sources.
- In Device details, Card colors edits the fill, outline, and text.
  Click Save device changes to keep your edits.
- Choose Hierarchical, Grid, Radial, Sections / Zones, or Freeform. Use
  Arrange to apply the layout, Undo layout to restore the previous one,
  and Fit map to bring visible items into view.
- Drag the canvas to pan and scroll to zoom. Grid and Snap to grid are
  independent controls.
- Add a section from the toolbar or by right-clicking empty canvas. Drag
  its body to move it and drag its lower-right corner to resize it.
  Double-click it to collapse or expand it. Right-click it to edit it.
- Drop a device inside an expanded section or use Device groups to manage
  its memberships. Each device has one card. Sections / Zones places it
  in the first matching section, while keeping all its memberships.
  Section rules can match an explicitly supplied IPv4 range or a device
  type. These rules do not determine DHCP lease membership.
- Click Draw cable and then click the two devices. Choose the route,
  width, color, pattern, label, and which endpoint to monitor. Right-click
  the cable or its label to edit it later.
- Monitored cables use the device's existing ping results: green for a
  response, yellow at 150 ms or higher, red for unreachable, and gray
  before a check. Inferred gateway lines and drawn cables represent
  logical relationships, not verified physical wiring.
- Select a device to change its built-in icon or import a PNG or SVG.
  Imported artwork is embedded in the saved map as a small PNG, so the
  original asset does not need to travel with the map.

UPGRADE AND DATA
If no current map exists, NetworkMapper reads the v0.7 map from
%USERPROFILE%\Documents\NetworkMapper\networkmap.json if present.
It saves the working map to %LOCALAPPDATA%\NetworkMapper\networkmap.json.
The original v0.7 file is left in place. Neither ZIP includes your map.

DEVELOPER
The source ZIP contains complete source files. Extract it into a project
folder. Use Python 3.12 and install requirements.txt, then run main.py.
Install PyInstaller in the development environment and run build_windows.py
to rebuild the one-folder Windows executable.

Run "python -m unittest discover" from the source folder to check the
existing discovery and identity tests. Before publishing, validate the
ZIP on a clean Windows x64 machine without Python and review third-party
license obligations.

The original DSR Technologies PNG is bundled in assets/dsr-technologies.png.
See SIGNING.txt in the source package for the signed release workflow.
