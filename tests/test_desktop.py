"""Offline regression tests. No Wine process or device access is permitted."""
import argparse
from contextlib import redirect_stdout
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('desktop', PROJECT / 'scripts/desktop.py')
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)
REAL_RUN_WINE = desktop.run_wine


class InstallationTests(unittest.TestCase):
    def setUp(self):
        scratch = PROJECT / 'local-data/test-runs'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.data = self.home / 'data with spaces'
        self.root = self.data / 'cortex-control-linux'
        self.launcher = self.home / 'bin/cortex-control'
        self.desktop_file = self.data / 'applications/cortex-control-linux.desktop'
        for name, value in [('DATA', self.data), ('ROOT', self.root), ('LAUNCHER', self.launcher), ('DESKTOP', self.desktop_file)]:
            self.enterContext(patch.object(desktop, name, value))
        self.enterContext(patch.object(Path, 'home', return_value=self.home))
        self.runtime = self.home / 'Proton - Experimental'
        for name in desktop.RUNTIME_FILES:
            path = self.runtime / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(desktop.TESTED_RUNTIME if name == 'version' else name)
            path.chmod(0o755)
        self.exe = self.home / 'source.exe'
        self.exe.write_text('synthetic application, not a proprietary binary')
        self.enterContext(patch.object(desktop, 'EXPECTED', desktop.sha(self.exe)))
        self.enterContext(patch.object(desktop, 'require_tools'))
        self.enterContext(patch.object(desktop, 'display_ready'))
        self.enterContext(patch.object(desktop.shutil, 'which', side_effect=lambda name: '/usr/bin/' + name))
        # cp is the only real subprocess in these synthetic tests.
        real_run = subprocess.run
        def fake_run(cmd, **kwargs):
            if cmd[0] == 'cp':
                return real_run(cmd, **kwargs)
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
        self.process = self.enterContext(patch.object(desktop.subprocess, 'run', side_effect=fake_run))
        def fake_wine(args, disconnected, config):
            self.assertTrue(disconnected)
            prefix = desktop.state_path(config) / 'prefix'
            prefix.mkdir(exist_ok=True)
            (prefix / 'initialized').write_text('yes')
        self.wine = self.enterContext(patch.object(desktop, 'run_wine', side_effect=fake_wine))
        self.enterContext(redirect_stdout(io.StringIO()))

    def args(self, action='install', **extra):
        values = dict(action=action, installer=None, exe=str(self.exe), runtime=str(self.runtime), migrate_prefix=None)
        values.update(extra)
        return argparse.Namespace(**values)

    def install(self):
        desktop.install(self.args())
        return desktop.load_config()

    def test_install_uses_verified_complete_bundle_and_one_launcher(self):
        config = self.install()
        self.assertEqual(desktop.sha(self.root / config['app'] / 'Cortex Control.exe'), desktop.EXPECTED)
        self.assertTrue((self.root / config['manifest']).is_file())
        self.assertTrue(self.launcher.stat().st_mode & 0o111)
        self.assertIn('"$@"', self.launcher.read_text())
        self.assertNotIn(' run "$@"', self.launcher.read_text())
        self.assertEqual((desktop.state_path(config) / 'prefix/drive_c/users/steamuser/Documents').readlink(), Path('/files'))
        self.assertFalse(list((self.root / 'installs').glob('.staging-*')))

    def test_reinstall_keeps_old_prefix_and_copies_settings(self):
        first = self.install()
        settings = desktop.state_path(first) / 'prefix/user-settings'
        settings.write_text('preserve me')
        desktop.install(self.args('reinstall', exe=None, runtime=None))
        second = desktop.load_config()
        self.assertNotEqual(first['state'], second['state'])
        self.assertEqual(settings.read_text(), 'preserve me')
        self.assertEqual((desktop.state_path(second) / 'prefix/user-settings').read_text(), 'preserve me')
        self.assertTrue((self.root / first['runtime']).is_dir())
        self.assertTrue(list((self.root / 'backups').glob('*/install.json')))

    def test_install_refuses_existing_without_changes(self):
        config = self.install()
        with self.assertRaisesRegex(ValueError, 'Already installed'):
            desktop.install(self.args())
        self.assertEqual(config, desktop.load_config())

    def test_uninstall_then_repair_restores_without_wine(self):
        config = self.install()
        self.wine.reset_mock()
        desktop.uninstall(yes=True)
        self.assertFalse(self.launcher.exists())
        self.assertEqual(config, desktop.load_config())
        desktop.repair()
        self.assertTrue(self.launcher.exists())
        self.assertTrue(self.desktop_file.exists())
        self.assertEqual(config, desktop.load_config())
        self.wine.assert_not_called()

    def test_failed_wine_preparation_retains_previous_config_and_settings(self):
        config = self.install()
        marker = desktop.state_path(config) / 'prefix/important'
        marker.write_text('untouched')
        self.wine.side_effect = RuntimeError('simulated Wine failure')
        with self.assertRaisesRegex(RuntimeError, 'simulated Wine failure'):
            desktop.install(self.args('reinstall'))
        self.assertEqual(config, desktop.load_config())
        self.assertEqual(marker.read_text(), 'untouched')
        self.assertFalse(list((self.root / 'installs').glob('.staging-*')))

    def test_failed_desktop_validation_rolls_back_config_and_integration(self):
        config = self.install()
        old_launcher = self.launcher.read_bytes()
        real_side_effect = self.process.side_effect
        def fail_validation(cmd, **kwargs):
            if cmd[0] == 'desktop-file-validate':
                raise subprocess.CalledProcessError(1, cmd)
            return real_side_effect(cmd, **kwargs)
        self.process.side_effect = fail_validation
        with self.assertRaises(subprocess.CalledProcessError):
            desktop.install(self.args('reinstall'))
        self.assertEqual(config, desktop.load_config())
        self.assertEqual(old_launcher, self.launcher.read_bytes())

    def test_incomplete_runtime_refused_before_configuration(self):
        (self.runtime / desktop.RUNTIME_FILES[-1]).unlink()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            desktop.install(self.args())
        self.assertFalse((self.root / 'install.json').exists())
        self.wine.assert_not_called()

    def test_wrong_app_hash_refused_before_wine(self):
        self.exe.write_text('not the qualified executable')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            desktop.install(self.args())
        self.wine.assert_not_called()

    def test_interrupted_staging_is_not_reused(self):
        stale = self.root / 'installs/.staging-interrupted/runtime'
        stale.mkdir(parents=True)
        (stale / 'version').write_text(desktop.TESTED_RUNTIME)
        config = self.install()
        self.assertNotIn('.staging-interrupted', config['runtime'])
        self.assertTrue(stale.exists())

    def test_running_legacy_session_blocks_reinstall_and_repair(self):
        config = self.install()
        with (desktop.state_path(config) / 'session.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for action in (lambda: desktop.install(self.args('reinstall')), desktop.repair):
                with self.assertRaisesRegex(RuntimeError, 'Close Cortex Control'):
                    action()
        self.assertEqual(config, desktop.load_config())

    def test_legacy_layout_is_preserved_on_reinstall(self):
        config = self.install()
        state = desktop.state_path(config)
        state.rename(self.root / 'state')
        config.pop('state')
        (self.root / 'install.json').write_text(json.dumps(config))
        desktop.install(self.args('reinstall'))
        self.assertTrue((self.root / 'state/prefix').is_dir())
        self.assertNotEqual(desktop.state_path(desktop.load_config()), self.root / 'state')

    def test_doctor_does_not_write_launch_wine_or_open_hid(self):
        self.install()
        self.wine.reset_mock()
        before = {str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in self.root.rglob('*') if p.is_file()}
        with patch.object(desktop, 'device', return_value='/dev/hidraw-test'), patch.object(desktop, 'owners', return_value=[]), patch.object(desktop.os, 'open', side_effect=AssertionError('No HID open')):
            desktop.doctor()
        after = {str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.wine.assert_not_called()

    def test_doctor_reports_corrupt_config(self):
        self.root.mkdir(parents=True)
        (self.root / 'install.json').write_text('[]')
        with patch.object(desktop, 'device', return_value=None):
            self.assertEqual(desktop.doctor(), 1)

    def test_doctor_detects_damaged_copied_dll(self):
        config = self.install()
        (self.root / config['app'] / 'dxgi.dll').write_text('damaged')
        with patch.object(desktop, 'device', return_value=None):
            self.assertEqual(desktop.doctor(), 1)

    def test_archive_tool_accepts_7zz_and_rejects_missing(self):
        with patch.object(desktop.shutil, 'which', side_effect=lambda name: '/usr/bin/7zz' if name == '7zz' else None):
            self.assertEqual(desktop.archive_tool(), '/usr/bin/7zz')
        with patch.object(desktop.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, '7z or 7zz'):
                desktop.archive_tool()

    def test_steam_secondary_library_with_spaces_is_detected(self):
        base = self.home / '.local/share/Steam/steamapps'
        base.mkdir(parents=True)
        library = self.home / 'Other Steam Library'
        target = library / 'steamapps/common/Proton - Experimental'
        target.parent.mkdir(parents=True)
        self.runtime.rename(target)
        (base / 'libraryfolders.vdf').write_text('"libraryfolders" { "1" { "path" "' + str(library) + '" } }')
        self.assertEqual(desktop.runtime_candidates(), [target.resolve()])

    def test_lsof_error_fails_closed(self):
        self.process.side_effect = None
        self.process.return_value = subprocess.CompletedProcess(['lsof'], 1, '', 'permission error')
        with self.assertRaisesRegex(RuntimeError, 'reliably check'):
            desktop.owners('/dev/hidraw-test')

    def test_failed_window_activation_is_reported(self):
        self.process.side_effect = None
        self.process.return_value = subprocess.CompletedProcess(['wmctrl'], 1, '', '')
        with self.assertRaisesRegex(RuntimeError, 'could not be activated'):
            desktop.activate()

    def test_disconnected_launch_never_enumerates_or_opens_hid(self):
        config = self.install()
        with patch.object(desktop, 'device', side_effect=AssertionError('No enumeration')), patch.object(desktop.os, 'open', side_effect=AssertionError('No HID open')), patch.object(desktop, 'execute_wine', return_value=0) as execute:
            self.assertEqual(REAL_RUN_WINE(disconnected=True, config=config), 0)
        self.assertIsNone(execute.call_args.args[4])

    def test_competing_owner_prevents_hid_open_and_launch(self):
        config = self.install()
        with patch.object(desktop, 'device', return_value='/dev/hidraw-test'), patch.object(desktop, 'owners', return_value=['123']), patch.object(desktop.os, 'open', side_effect=AssertionError('Must not open')), patch.object(desktop, 'execute_wine') as execute:
            with self.assertRaisesRegex(RuntimeError, 'Another program'):
                REAL_RUN_WINE(config=config)
        execute.assert_not_called()

    def test_hid_lock_contention_prevents_launch(self):
        config = self.install()
        node = self.home / 'synthetic-hid-node'
        node.touch()
        with node.open('r+') as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(desktop, 'device', return_value=str(node)), patch.object(desktop, 'owners', return_value=[]), patch.object(desktop, 'execute_wine') as execute:
                with self.assertRaisesRegex(RuntimeError, 'Another CorTux session'):
                    REAL_RUN_WINE(config=config)
        execute.assert_not_called()

    def test_launch_error_is_not_treated_as_window_activation(self):
        self.install()
        self.wine.side_effect = RuntimeError('launch failed')
        with patch.object(desktop, 'activate') as activate:
            with self.assertRaisesRegex(RuntimeError, 'launch failed'):
                desktop.run()
        activate.assert_not_called()


    def test_installer_hash_rejected_before_extraction(self):
        with self.assertRaisesRegex(ValueError, 'not qualified'):
            desktop.extract_installer(self.exe, self.home / 'extract')
        self.process.assert_not_called()

    def test_unsafe_config_path_rejected(self):
        self.root.mkdir(parents=True)
        (self.root / 'install.json').write_text(json.dumps({'app': '../elsewhere', 'runtime': 'runtime', 'files': '/tmp'}))
        with self.assertRaisesRegex(ValueError, 'Invalid installation path'):
            desktop.load_config()


if __name__ == '__main__':
    unittest.main()
