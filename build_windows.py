"""Build a self-contained Windows folder. Run with .venv Python on Windows."""
import os
import subprocess
import sys
from pathlib import Path

if os.name != 'nt':
    raise SystemExit('Run this Windows EXE build on Windows.')
root = Path(__file__).resolve().parent
dist = root / 'dist'
system = Path(os.environ['SystemRoot'])
build_env = dict(os.environ, PATH=os.pathsep.join(map(str, (system / 'System32', system))))
# Qt imports the Windows ICU API. Third-party ICU DLLs found on the developer's
# PATH can have the same names but export a different API.
subprocess.run([
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
    '--windowed', '--onedir', '--noupx', '--name', 'NetworkMapper',
    '--collect-all', 'zeroconf',
    '--add-data', f"{root / 'assets' / 'dsr-technologies.png'}:assets",
    '--distpath', str(dist),
    '--workpath', str(root / 'build'),
    '--specpath', str(root / 'build'),
    str(root / 'main.py'),
], check=True, env=build_env)
bundled = dist / 'NetworkMapper'
for name in ('icuuc.dll', 'icuin.dll', 'icu.dll'):
    if any(bundled.rglob(name)):
        raise SystemExit(f'Unexpected bundled {name}. Qt requires the Windows copy.')
print('Built:', bundled / 'NetworkMapper.exe')
