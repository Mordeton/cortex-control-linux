#!/usr/bin/env python3
"""Install, repair, diagnose and run Cortex Control on Bazzite/KDE."""
import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

if sys.version_info < (3, 11):
    raise SystemExit('Cortex Control Linux requires Python 3.11 or newer.')

DATA = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
ROOT = DATA / 'cortex-control-linux'
EXPECTED = '9be548fb6cbd2e8c80715015c2a2f0f248c9b01a7165004e2b017ffe2b14e65a'
INSTALLER_HASH = 'c03942a0631afd195d3d70febf91384bf39cb7101014146f26f5ba65fd73228c'
TESTED_RUNTIME = '1791480010 experimental-11.0-20261008-x86_64'
DESKTOP = DATA / 'applications/cortex-control-linux.desktop'
LAUNCHER = Path.home() / '.local/bin/cortex-control'
RUNTIME_FILES = (
    'version', 'files/bin/wine', 'files/bin/wineserver',
    'files/lib/wine/dxvk/x86_64-windows/d3d11.dll',
    'files/lib/wine/dxvk/x86_64-windows/dxgi.dll',
    'files/lib/vkd3d/x86_64-windows/libvkd3d-1.dll',
    'files/lib/vkd3d/x86_64-windows/libvkd3d-shader-1.dll',
    'files/lib/vkd3d/x86_64-windows/libvkd3d-utils-1.dll',
)
TOOLS = ('bwrap', 'lsof', 'cp', 'desktop-file-validate')


class BusySession(RuntimeError):
    """A cooperative launch or installation lock is held."""


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def notify(message):
    print(message, file=sys.stderr)
    if not sys.stderr.isatty() and shutil.which('kdialog') and os.environ.get('DISPLAY'):
        subprocess.run(['kdialog', '--title', 'Cortex Control', '--error', message], check=False)


def atomic_write(path, text, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text.encode())
            stream.flush()
            os.fsync(stream.fileno())
            temporary.chmod(mode)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def copy_tree(source, destination):
    if destination.exists():
        raise ValueError('Refusing to merge into an existing copy: ' + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cp', '-a', '--reflink=auto', '--', str(source), str(destination)], check=True)


def desktop_quote(value):
    value = str(value)
    if '\n' in value or '\r' in value:
        raise ValueError('Desktop launcher paths must not contain line breaks.')
    # Exec has two escaping layers: Desktop Entry strings, then argument quoting.
    escaped = ''.join('\\' + c if c in '\\"`$' else c for c in value)
    return '"' + escaped.replace('\\', '\\\\').replace('%', '%%') + '"'


def archive_tool():
    tool = shutil.which('7z') or shutil.which('7zz')
    if not tool:
        raise ValueError('Installer extraction needs 7z or 7zz. Run ./cortex-control doctor.')
    return tool


def require_tools(archive=False):
    missing = [tool for tool in TOOLS if not shutil.which(tool)]
    if missing:
        raise ValueError('Missing tools: ' + ', '.join(missing) + '. Run ./cortex-control doctor.')
    if archive:
        archive_tool()
    if platform.machine() != 'x86_64':
        raise ValueError('This launcher supports x86_64 Bazzite desktops only.')


def display_ready():
    if not os.environ.get('DISPLAY') or not Path('/tmp/.X11-unix').is_dir():
        raise ValueError('Open a terminal in your desktop session (X11 or Wayland with XWayland). DISPLAY is required.')
    auth = os.environ.get('XAUTHORITY')
    if auth and not os.access(auth, os.R_OK):
        raise ValueError('The desktop XAUTHORITY file is not readable. Use your normal desktop account.')


def runtime_info(runtime):
    missing = [name for name in RUNTIME_FILES if not (runtime / name).is_file()]
    if missing:
        raise ValueError('Incomplete or unsupported Proton runtime: ' + str(runtime) + '; missing ' + ', '.join(missing))
    if any(not os.access(runtime / name, os.X_OK) for name in ('files/bin/wine', 'files/bin/wineserver')):
        raise ValueError('Proton Wine and wineserver must be executable.')
    return (runtime / 'version').read_text().strip()


def runtime_candidates():
    bases = [Path.home() / '.local/share/Steam', Path.home() / '.steam/steam',
             Path.home() / '.var/app/com.valvesoftware.Steam/.local/share/Steam']
    for base in list(bases):
        vdf = base / 'steamapps/libraryfolders.vdf'
        if vdf.is_file():
            bases += [Path(value.replace('\\\\', '\\')) for value in re.findall(r'"path"\s+"([^"\n]+)"', vdf.read_text())]
    found = set()
    for base in bases:
        for path in (base / 'steamapps/common').glob('Proton*'):
            try:
                runtime_info(path)
                found.add(path.resolve())
            except (OSError, ValueError):
                continue
    return sorted(found, key=lambda path: ((path / 'version').read_text().strip() != TESTED_RUNTIME,
                                          'Experimental' not in path.name, str(path)))


def choose_runtime(explicit, previous=None):
    if explicit:
        return Path(explicit).expanduser().resolve()
    if previous:
        existing = ROOT / previous['runtime']
        try:
            runtime_info(existing)
            return existing
        except (OSError, ValueError):
            pass
    candidates = runtime_candidates()
    if not candidates:
        raise ValueError('No usable Proton found. In Steam, enable the Tools library filter, install Proton Experimental, then retry. Or supply --runtime /path/to/Proton.')
    return candidates[0]


def choose_installer():
    if shutil.which('kdialog') and os.environ.get('DISPLAY'):
        result = subprocess.run(['kdialog', '--title', 'Select the Cortex Control 4.1.0 Windows installer',
                                 '--getopenfilename', str(Path.home() / 'Downloads'), '*.exe'],
                                capture_output=True, text=True)
        if result.returncode or not result.stdout.strip():
            raise ValueError('Installation cancelled; no files were installed.')
        return result.stdout.strip()
    raise ValueError('Download the Cortex Control 4.1.0 Windows installer from https://neuraldsp.com/downloads and supply --installer /path/to/installer.exe.')


def load_config(required=True):
    path = ROOT / 'install.json'
    if not path.exists():
        if required:
            raise ValueError('Cortex Control is not installed. Run ./cortex-control install.')
        return None
    config = json.loads(path.read_text())
    if not isinstance(config, dict):
        raise ValueError('Invalid installation configuration: expected a JSON object.')
    for key in ('app', 'runtime', 'files'):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError('Invalid installation configuration: missing ' + key)
    if not Path(config['files']).is_absolute():
        raise ValueError('The import/export folder must be an absolute path.')
    if 'manifest' in config and (not isinstance(config['manifest'], str) or not config['manifest']):
        raise ValueError('Invalid installation configuration: manifest must be a path string.')
    for key in ('app', 'runtime', 'state'):
        value = config.get(key, 'state')
        if not isinstance(value, str) or not value or Path(value).is_absolute() or '..' in Path(value).parts:
            raise ValueError('Invalid installation path: ' + key)
    return config


def state_path(config):
    return ROOT / config.get('state', 'state')


@contextmanager
def file_lock(path, message):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BusySession(message) from None
        yield


@contextmanager
def installation_lock(config=None):
    # Also honor the session lock used by the original desktop launcher.
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ExitStack() as stack:
        stack.enter_context(file_lock(ROOT / 'operation.lock', 'Cortex Control or its installer is running. Close that session first.'))
        if config and state_path(config).exists():
            stack.enter_context(file_lock(state_path(config) / 'session.lock', 'Close Cortex Control before changing its installation.'))
        yield


def device():
    matches = []
    for path in Path('/sys/class/hidraw').glob('*'):
        try:
            if 'HID_ID=0003:0000152A:0000880A' in (path / 'device/uevent').read_text():
                matches.append('/dev/' + path.name)
        except FileNotFoundError:
            continue  # A USB device disappeared during enumeration.
    if len(matches) > 1:
        raise RuntimeError('More than one Quad Cortex is connected. Connect one device for this version.')
    return matches[0] if matches else None


def owners(node):
    result = subprocess.run(['lsof', '-t', node], capture_output=True, text=True, timeout=10)
    if result.returncode not in (0, 1) or result.stderr.strip():
        raise RuntimeError('Could not reliably check QC ownership with lsof. Close other editor sessions and run doctor.')
    return result.stdout.split()


def activate():
    if shutil.which('wmctrl'):
        result = subprocess.run(['wmctrl', '-a', 'Cortex Control'], capture_output=True, timeout=10)
        if result.returncode == 0:
            return 0
    raise RuntimeError('Cortex Control has a running session but its window could not be activated. It may still be starting. Check its window or run doctor; no process was stopped.')


def run_wine(wine_args=None, disconnected=False, config=None):
    config = config or load_config()
    display_ready()
    runtime = ROOT / config['runtime']
    runtime_info(runtime)
    app = ROOT / config['app']
    executable = app / 'Cortex Control.exe'
    if not executable.is_file() or sha(executable) != EXPECTED:
        raise ValueError('Application files are missing or fail the verified Cortex Control 4.1.0 hash check. Run ./cortex-control reinstall with your installer.')
    state = state_path(config)
    files = Path(config['files'])
    files.mkdir(parents=True, exist_ok=True)
    node = None if disconnected else device()
    with ExitStack() as stack:
        if node:
            if owners(node):
                raise RuntimeError('Another program is using the Quad Cortex editor connection. Close that session first.')
            try:
                fd = os.open(node, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
            except PermissionError:
                raise RuntimeError('No permission to access the QC HID interface. Run doctor for details; do not run this launcher as root.') from None
            stack.callback(os.close, fd)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Another CorTux session owns the Quad Cortex.') from None
        return execute_wine(runtime, app, state, files, node, wine_args)


def execute_wine(runtime, app, state, files, node, wine_args):
    cmd = ['bwrap', '--unshare-user', '--unshare-pid', '--unshare-uts', '--unshare-cgroup-try', '--die-with-parent', '--new-session', '--clearenv',
           '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
           '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
           '--ro-bind', '/etc', '/etc', '--ro-bind', '/sys', '/sys',
           '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
           '--ro-bind', '/tmp/.X11-unix', '/tmp/.X11-unix',
           '--ro-bind', str(runtime), '/runtime', '--ro-bind', str(app), '/app',
           '--bind', str(state), '/state', '--bind', str(files), '/files', '--chdir', '/app']
    env = {'HOME': '/state/home', 'USER': 'steamuser',
           'PATH': '/runtime/files/bin:/usr/bin:/bin',
           'LD_LIBRARY_PATH': '/runtime/files/lib64:/runtime/files/lib',
           'WINEDLLPATH': '/runtime/files/lib/vkd3d:/runtime/files/lib/wine',
           'WINEPREFIX': '/state/prefix', 'WINEARCH': 'win64',
           'WINEESYNC': '0', 'WINEFSYNC': '0', 'WINEDEBUG': '-all,err+all',
           # Editor control uses HID, not Wine audio/MIDI. Host ALSA defaults can
           # enter PipeWire and hang in this sandbox without its audio sockets.
           # Disable only this process's Wine backends; host/game audio is intact.
           'WINEDLLOVERRIDES': 'winemenubuilder.exe=;mscoree=;mshtml=;winealsa.drv=;winepulse.drv=;dxgi,d3d11=n,b',
           'DXVK_LOG_PATH': '/state', 'DISPLAY': os.environ['DISPLAY'],
           'LANG': 'C.UTF-8', 'XDG_DATA_HOME': '/state/home/.local/share'}
    for key, value in env.items():
        cmd += ['--setenv', key, value]
    auth = os.environ.get('XAUTHORITY')
    if auth:
        cmd += ['--ro-bind', auth, '/tmp/xauth', '--setenv', 'XAUTHORITY', '/tmp/xauth']
    for gpu in [Path('/dev/dri'), *Path('/dev').glob('nvidia*')]:
        if gpu.is_dir() or os.access(gpu, os.R_OK | os.W_OK):
            cmd += ['--dev-bind', str(gpu), str(gpu)]
    if node:
        cmd += ['--dev-bind', node, node]
        if Path('/run/udev').exists():
            cmd += ['--ro-bind', '/run/udev', '/run/udev']
    cmd += ['/bin/bash', '-c', 'trap "wineserver -k; wineserver -w" EXIT; wine "$@"',
            'cortex-control', *(wine_args or ['/app/Cortex Control.exe'])]
    with (state / 'last-run.log').open('w') as log:
        result = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=180 if wine_args else None)
    if result:
        raise RuntimeError('Cortex Control could not start. Details: ' + str(state / 'last-run.log'))
    return result


def extract_installer(installer, destination):
    """The checked 4.1.0 bootstrapper embeds an XOR-obfuscated CAB."""
    if sha(installer) != INSTALLER_HASH:
        raise ValueError('This installer version is not qualified. Use the original Cortex Control 4.1.0 installer.')
    data = installer.read_bytes()[9548800:9548800 + 20726076]
    # The extraction manifest identifies a 512-byte obfuscated CAB header.
    # Derive its repeated XOR key from the CAB magic and reserved zero bytes.
    expected_header = b'MSCF' + b'\0' * 4
    key = bytes(a ^ b for a, b in zip(data[:8], expected_header))
    candidates = []
    for period in (1, 2, 4, 8):
        decoded = bytes(value ^ key[i % period] for i, value in enumerate(data[:512])) + data[512:]
        if hashlib.sha256(decoded).hexdigest() == '40feff69394a538aee6e5b713c6355623eb97daa4a78c6236477664a11b8c5c8':
            candidates.append(decoded)
    if not candidates:
        raise ValueError('Installer extraction did not match the verified CAB. No installer was executed.')
    cab = destination / 'payload.cab'
    cab.write_bytes(candidates[0])
    subprocess.run([archive_tool(), 'x', '-y', '-o' + str(destination / 'expanded'), str(cab)], check=True, stdout=subprocess.DEVNULL)
    matches = [p for p in (destination / 'expanded').rglob('*') if p.is_file() and sha(p) == EXPECTED]
    if len(matches) != 1:
        raise ValueError('Expected exactly one verified Cortex Control executable in the installer.')
    return matches[0]


def integration_files():
    script = ROOT / 'scripts/desktop.py'
    icon = ROOT / 'cortex-control-linux.svg'
    launcher = ('#!/bin/sh\nexport XDG_DATA_HOME=' + shlex.quote(str(DATA)) +
                '\nexec /usr/bin/python3 ' + shlex.quote(str(script)) + ' "$@"\n')
    desktop = ('[Desktop Entry]\nType=Application\nName=Cortex Control\n'
               'Comment=Unofficial Linux launcher for the Windows Quad Cortex editor\n'
               'Exec=' + desktop_quote(LAUNCHER) + '\nIcon=' + str(icon) + '\n'
               'Terminal=false\nCategories=AudioVideo;Audio;\nStartupWMClass=cortex control.exe\n'
               'Actions=Files;Doctor;Uninstall;\n\n[Desktop Action Files]\n'
               'Name=Open backups and imports\nExec=' + desktop_quote(LAUNCHER) + ' files\n\n'
               '[Desktop Action Doctor]\nName=Check installation\nExec=' + desktop_quote(LAUNCHER) + ' doctor --gui\n\n'
               '[Desktop Action Uninstall]\nName=Remove desktop integration\nExec=' + desktop_quote(LAUNCHER) + ' uninstall\n')
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><rect x="5" y="5" width="118" height="118" rx="25" fill="#17202b"/><path d="M28 64h15l8-23 18 47 9-24h22" fill="none" stroke="#63d4bd" stroke-width="8" stroke-linejoin="round" stroke-linecap="round"/></svg>\n'
    return {script: (Path(__file__).read_text(), 0o600),
            ROOT / 'scripts/hid.reg': (Path(__file__).with_name('hid.reg').read_text(), 0o600),
            icon: (svg, 0o644), LAUNCHER: (launcher, 0o755), DESKTOP: (desktop, 0o644)}


def publish_install(config):
    """Commit a local installation; this never uploads or publishes online."""
    changes = integration_files()
    config_file = ROOT / 'install.json'
    changes[config_file] = (json.dumps(config, indent=2) + '\n', 0o600)
    previous = {}
    for path in changes:
        if path.is_symlink():
            raise ValueError('Refusing to replace a symlink: ' + str(path))
        previous[path] = (path.read_text(), path.stat().st_mode & 0o777) if path.exists() else None
    backup = ROOT / 'backups' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    backup.mkdir(parents=True)
    atomic_write(backup / 'integration.json', json.dumps({str(p): v for p, v in previous.items()}, indent=2) + '\n')
    if previous[config_file]:
        atomic_write(backup / 'install.json', previous[config_file][0])
    try:
        for path, (content, mode) in changes.items():
            # install.json is last: it never points at a partially prepared bundle.
            if path == config_file:
                subprocess.run(['desktop-file-validate', str(DESKTOP)], check=True)
            atomic_write(path, content, mode)
    except BaseException:
        for path, value in previous.items():
            if value is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, *value)
        raise
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(DESKTOP.parent)], check=False)


def link_documents(state):
    user = state / 'prefix/drive_c/users/steamuser'
    user.mkdir(parents=True, exist_ok=True)
    for name in ('Documents', 'My Documents'):
        target = user / name
        if target.is_symlink():
            target.unlink()
        elif target.exists():
            previous = user / (name + '.before-linux')
            if previous.exists():
                raise ValueError('Existing Documents backup needs review: ' + str(previous))
            target.rename(previous)
        target.symlink_to('/files', target_is_directory=True)


def prepare_bundle(exe, runtime, previous, migrate_prefix=None):
    """Build a fresh bundle. Never merge into old or interrupted copies."""
    bundles = ROOT / 'installs'
    bundles.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.staging-', dir=bundles) as temporary:
        stage = Path(temporary)
        app = stage / 'app'
        app.mkdir()
        shutil.copy2(exe, app / 'Cortex Control.exe')
        shutil.copy2(Path(__file__).with_name('hid.reg'), app / 'hid.reg')
        copy_tree(runtime, stage / 'runtime')
        version = runtime_info(stage / 'runtime')
        for name in RUNTIME_FILES:
            if sha(runtime / name) != sha(stage / 'runtime' / name):
                raise ValueError('Runtime copy verification failed: ' + name)
        for name in RUNTIME_FILES[3:]:
            shutil.copy2(stage / 'runtime' / name, app / Path(name).name)
        if sha(app / 'Cortex Control.exe') != EXPECTED:
            raise ValueError('Application copy verification failed.')
        state = stage / 'state'
        if previous:
            source = state_path(previous)
            if not (source / 'prefix').is_dir():
                raise ValueError('The existing prefix is missing. Preserve the installation and inspect doctor before continuing.')
            copy_tree(source, state)
        else:
            state.mkdir()
            if migrate_prefix:
                copy_tree(Path(migrate_prefix).expanduser().resolve(), state / 'prefix')
        (state / 'home').mkdir(exist_ok=True)
        files = previous['files'] if previous else str(Path.home() / 'Documents/Cortex Control')
        config = {'version': '4.1.0', 'sha256': EXPECTED, 'runtime_version': version,
                  'runtime': str((stage / 'runtime').relative_to(ROOT)),
                  'app': str(app.relative_to(ROOT)), 'state': str(state.relative_to(ROOT)),
                  'files': files, 'network': 'offline'}
        run_wine(['wineboot', '-u'], disconnected=True, config=config)
        run_wine(['reg', 'import', r'Z:\app\hid.reg'], disconnected=True, config=config)
        link_documents(state)
        manifest = {str(path.relative_to(stage)): sha(path)
                    for path in [*(stage / 'runtime' / name for name in RUNTIME_FILES), *app.iterdir()]}
        atomic_write(stage / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
        final = bundles / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
        stage.rename(final)
        for key in ('runtime', 'app', 'state'):
            config[key] = str((final / key).relative_to(ROOT))
        config['manifest'] = str((final / 'manifest.json').relative_to(ROOT))
        return config


def install(args):
    require_tools()
    display_ready()
    with installation_lock():
        previous = load_config(required=False)
        if args.action == 'install' and previous:
            raise ValueError('Already installed. Use repair to restore the menu/launcher, or reinstall to replace app/runtime files while preserving settings.')
        if args.action == 'reinstall' and not previous:
            raise ValueError('No installation to reinstall. Use install first.')
        if previous and args.migrate_prefix:
            raise ValueError('--migrate-prefix is only available on first installation.')
        with ExitStack() as stack:
            if previous:
                stack.enter_context(file_lock(state_path(previous) / 'session.lock', 'Close Cortex Control before reinstalling.'))
            runtime = choose_runtime(args.runtime, previous)
            version = runtime_info(runtime)
            print('Using Proton:', version, flush=True)
            if version != TESTED_RUNTIME:
                print('Note: this runtime build has not been hardware-qualified here. See COMPATIBILITY.md.', flush=True)
            installer = args.installer
            exe = Path(args.exe).expanduser().resolve() if args.exe else None
            if not exe and not installer and previous:
                candidate = ROOT / previous['app'] / 'Cortex Control.exe'
                if candidate.is_file() and sha(candidate) == EXPECTED:
                    exe = candidate
            if not exe:
                installer = installer or choose_installer()
                archive_tool()
            with tempfile.TemporaryDirectory(prefix='extract-', dir=ROOT) as temporary:
                if not exe:
                    exe = extract_installer(Path(installer).expanduser().resolve(), Path(temporary))
                if sha(exe) != EXPECTED:
                    raise ValueError('Executable does not match the tested Cortex Control 4.1.0. No version checks were bypassed.')
                print('Preparing a private runtime and prefix; this may take a few minutes.', flush=True)
                config = prepare_bundle(exe, runtime, previous, args.migrate_prefix)
                publish_install(config)
    print('Installed. Open Cortex Control from your application menu. Files:', config['files'])
    if previous:
        print('Previous app, runtime and prefix retained. No automatic cleanup was performed.')


def repair():
    require_tools()
    with installation_lock():
        config = load_config()
        with file_lock(state_path(config) / 'session.lock', 'Close Cortex Control before repairing.'):
            runtime_info(ROOT / config['runtime'])
            if sha(ROOT / config['app'] / 'Cortex Control.exe') != EXPECTED:
                raise ValueError('App is damaged or unsupported. Use reinstall --installer /path/to/installer.exe.')
            if not (state_path(config) / 'prefix').is_dir():
                raise ValueError('The prefix is missing; repair will not recreate or erase personal settings.')
            publish_install(config)
    print('Repaired launcher and menu integration. Settings and backups preserved; Wine was not started.')


def uninstall(yes=False):
    with installation_lock():
        config = load_config(required=False)
        with ExitStack() as stack:
            if config:
                stack.enter_context(file_lock(state_path(config) / 'session.lock', 'Close Cortex Control first.'))
            if not yes:
                if shutil.which('kdialog') and os.environ.get('DISPLAY'):
                    if subprocess.call(['kdialog', '--yesno', 'Remove Cortex Control from the application menu? Application files, settings and backups will be kept. Restore with repair.']):
                        return
                elif not sys.stdin.isatty() or input('Remove desktop integration and keep your files? [y/N] ').lower() != 'y':
                    return
            DESKTOP.unlink(missing_ok=True)
            LAUNCHER.unlink(missing_ok=True)
    print('Desktop integration removed; application files and settings retained. Run ./cortex-control repair to restore it.')


def locked(path):
    if not path.exists():
        return False
    with path.open('r') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def doctor(gui=False):
    """Read-only checks: no Wine, HID open, device commands, or saved report."""
    rows = []
    def add(level, label, detail):
        rows.append((level, label, detail))
    add('OK' if platform.machine() == 'x86_64' else 'FAIL', 'Architecture', platform.machine())
    for tool in TOOLS:
        add('OK' if shutil.which(tool) else 'FAIL', tool, shutil.which(tool) or 'Missing host tool; see README prerequisites.')
    add('OK' if shutil.which('7z') or shutil.which('7zz') else 'WARN', 'Installer extraction',
        shutil.which('7z') or shutil.which('7zz') or 'Install needs 7z or 7zz.')
    add('OK' if shutil.which('wmctrl') else 'WARN', 'Window activation',
        'Available' if shutil.which('wmctrl') else 'wmctrl missing; a second launch cannot focus the window.')
    try:
        display_ready()
        add('OK', 'Display', 'Desktop X11/XWayland environment is available; rendering is not tested.')
    except ValueError as exc:
        add('FAIL', 'Display', str(exc))
    gpu = Path('/dev/dri/renderD128').exists() or any(Path('/dev').glob('nvidia*'))
    add('OK' if gpu else 'WARN', 'Graphics', 'Graphics device found; Vulkan is not tested.' if gpu else 'No usual graphics device found.')
    try:
        config = load_config(required=False)
        if config:
            version = runtime_info(ROOT / config['runtime'])
            add('OK' if version == TESTED_RUNTIME else 'WARN', 'Runtime', version)
            app = ROOT / config['app'] / 'Cortex Control.exe'
            add('OK' if app.is_file() and sha(app) == EXPECTED else 'FAIL', 'Application',
                'Cortex Control 4.1.0 hash check; use reinstall if this fails.')
            add('OK' if (state_path(config) / 'prefix').is_dir() else 'FAIL', 'Prefix', str(state_path(config) / 'prefix'))
            if config.get('manifest'):
                manifest_path = ROOT / config['manifest']
                if not manifest_path.resolve().is_relative_to(ROOT.resolve()):
                    raise ValueError('Manifest path is outside the installation.')
                manifest = json.loads(manifest_path.read_text())
                if not isinstance(manifest, dict):
                    raise ValueError('Invalid copy manifest: expected a JSON object.')
                bad = []
                for name, digest in manifest.items():
                    if not isinstance(name, str) or not isinstance(digest, str):
                        raise ValueError('Invalid copy manifest: file paths and hashes must be strings.')
                    path = manifest_path.parent / name
                    if not path.resolve().is_relative_to(manifest_path.parent.resolve()) or not path.is_file() or sha(path) != digest:
                        bad.append(name)
                add('FAIL' if bad else 'OK', 'Copied files', ', '.join(bad) if bad else 'Recorded app/runtime file hashes match.')
            else:
                add('WARN', 'Copied files', 'Legacy installation has no copy manifest. Reinstall creates one.')
            add('WARN' if locked(state_path(config) / 'session.lock') else 'OK', 'App session',
                'Running' if locked(state_path(config) / 'session.lock') else 'Idle')
            add('OK' if LAUNCHER.is_file() and DESKTOP.is_file() else 'WARN', 'Desktop integration',
                'Present' if LAUNCHER.is_file() and DESKTOP.is_file() else 'Run repair to restore it.')
        else:
            candidates = runtime_candidates()
            add('WARN', 'Installation', 'Not installed. Run ./cortex-control install.')
            add('OK' if candidates else 'WARN', 'Available Proton', str(candidates[0]) if candidates else 'Install Proton Experimental in Steam, or supply --runtime.')
        add('WARN' if locked(ROOT / 'operation.lock') else 'OK', 'Launcher/installer',
            'Busy' if locked(ROOT / 'operation.lock') else 'Idle')
    except (OSError, ValueError, RuntimeError) as exc:
        add('FAIL', 'Installation', str(exc))
    try:
        node = device()
        if node:
            accessible = os.access(node, os.R_OK | os.W_OK)
            add('OK' if accessible else 'FAIL', 'QC permission', node + (' is readable/writable.' if accessible else ' is not accessible. Use a local desktop session; no permissions were changed.'))
            if shutil.which('lsof'):
                busy = owners(node)
                add('WARN' if busy else 'OK', 'QC ownership', 'In use by process(es): ' + ', '.join(busy) if busy else 'No visible open owner. Launch will also acquire the cooperative HID lock.')
        else:
            add('WARN', 'Quad Cortex', 'Not connected. Disconnected launch is available.')
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        add('FAIL', 'Quad Cortex', str(exc))
    report = '\n'.join(f'[{level}] {label}: {detail}' for level, label, detail in rows)
    report += '\nOffline mode: Cloud, downloads and updates are unavailable.\nDoctor did not launch Wine or open the QC HID interface.\n'
    print(report)
    if gui and shutil.which('kdialog'):
        subprocess.run(['kdialog', '--title', 'Cortex Control diagnostics', '--msgbox', report], check=False)
    return int(any(row[0] == 'FAIL' for row in rows))


def run(disconnected=False):
    # Reload configuration under the stable lock, then lock the active prefix.
    # Also honor the original launcher's prefix-only lock during migration.
    config = load_config()
    try:
        with installation_lock():
            config = load_config()
            with file_lock(state_path(config) / 'session.lock', 'Cortex Control is already running.'):
                return run_wine(disconnected=disconnected, config=config)
    except BusySession:
        if locked(state_path(config) / 'session.lock'):
            return activate()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='action', required=True)
    for action in ('install', 'reinstall'):
        setup = subs.add_parser(action, help='Install a new copy, preserving any previous installation.')
        source = setup.add_mutually_exclusive_group()
        source.add_argument('--installer', help='Official Cortex Control 4.1.0 Windows installer.')
        source.add_argument('--exe', help='An already extracted, hash-verified 4.1.0 executable.')
        setup.add_argument('--runtime', help='Proton directory; detected from Steam if omitted.')
        setup.add_argument('--migrate-prefix', help='Copy an existing prefix on first install only.')
    launch = subs.add_parser('run', help='Launch Cortex Control (default command).')
    launch.add_argument('--disconnected', action='store_true')
    subs.add_parser('repair', help='Restore/update desktop integration without starting Wine.')
    diagnose = subs.add_parser('doctor', help='Read-only diagnostics; no device commands.')
    diagnose.add_argument('--gui', action='store_true')
    subs.add_parser('files', help='Open your import/export folder.')
    remove = subs.add_parser('uninstall', help='Remove desktop integration, retaining all personal files.')
    remove.add_argument('--yes', action='store_true', help='Skip the desktop-integration removal prompt.')
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] == '--disconnected':
        arguments.insert(0, 'run')
    args = parser.parse_args(arguments)
    try:
        if os.geteuid() == 0 and args.action != 'doctor':
            raise ValueError('Run as your normal desktop user, without sudo.')
        if args.action in ('install', 'reinstall'):
            install(args)
        elif args.action == 'run':
            return run(args.disconnected)
        elif args.action == 'repair':
            repair()
        elif args.action == 'doctor':
            return doctor(args.gui)
        elif args.action == 'files':
            subprocess.run(['xdg-open', load_config()['files']], check=True)
        else:
            uninstall(args.yes)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        notify(str(exc))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
