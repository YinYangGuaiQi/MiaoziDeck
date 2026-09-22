"""Offline checks. This does not claim to execute Flutter or SteamOS."""
import ast
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bootstrap_profile', ROOT / 'bootstrap_profile.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class StandaloneChecks(unittest.TestCase):
    def test_fresh_profile_and_unknown_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'database.sqlite'
            with closing(sqlite3.connect(database)) as db, db:
                db.execute('''CREATE TABLE profiles (
                  id INTEGER PRIMARY KEY, label TEXT NOT NULL, url TEXT NOT NULL,
                  current_group_name TEXT, last_update_date INTEGER,
                  overwrite_type TEXT NOT NULL, auto_update_duration_millis INTEGER NOT NULL,
                  subscription_info TEXT, auto_update INTEGER NOT NULL,
                  selected_map TEXT NOT NULL, unfold_set TEXT NOT NULL)''')
            bootstrap.seed_profile(database, 'https://example.invalid/sub', 123)
            with closing(sqlite3.connect(database)) as db, db:
                row = db.execute('SELECT id,auto_update,last_update_date,overwrite_type FROM profiles').fetchone()
                self.assertEqual(row, (123, 1, 0, 'standard'))
                db.execute('DROP TABLE profiles')
                db.execute('''CREATE TABLE profiles (id INTEGER PRIMARY KEY,url TEXT NOT NULL,
                  auto_update INTEGER,auto_update_duration_millis INTEGER,last_update_date INTEGER,
                  unknown_required TEXT NOT NULL)''')
            with self.assertRaises(bootstrap.BootstrapError):
                bootstrap.seed_profile(database, 'https://example.invalid/sub', 123)

    def test_preferences_disable_network_autostart(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            bootstrap.seed_preferences(data, 123)
            prefs = json.loads((data / 'shared_preferences.json').read_text())
            config = json.loads(prefs['flutter.config'])
            self.assertEqual(config['currentProfileId'], 123)
            self.assertFalse(config['appSettingProps']['autoRun'])
            self.assertFalse(config['appSettingProps']['autoLaunch'])
            self.assertFalse(config['vpnProps']['enable'])
            self.assertFalse(config['vpnProps']['systemProxy'])
            self.assertEqual(prefs['flutter.sspanel_binding'], '{}')

    def test_installer_extracts_and_rejects_corruption(self):
        version = json.loads((ROOT / 'package.json').read_text())['version']
        installer = ROOT / 'release' / f'MiaoziDeck-{version}.sh'
        header = installer.read_bytes().split(b'\n__MIAOZI_PAYLOAD__\n', 1)[0].decode()
        code = header.split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
        def check_launch(args, **kwargs):
            install_path = Path(args[1])
            self.assertEqual(args[0], 'bash')
            self.assertTrue(install_path.is_file())
            payload = install_path.parent / 'MiaoziDeck'
            for relative in ('official/FlClash', 'official/vendor/libkeybinder-3.0.so.0',
                             'decky/PluginLoader', 'dashboard/index.html', 'bootstrap_profile.py'):
                self.assertTrue((payload / relative).is_file(), relative)
            self.assertFalse((payload / 'online-subscription.json').exists())
        with patch('sys.argv', ['check', str(installer)]), patch('subprocess.run', side_effect=check_launch) as run:
            exec(compile(code, '<self-extractor>', 'exec'), {})
            run.assert_called_once()
        with tempfile.TemporaryDirectory() as folder:
            corrupt = Path(folder) / 'corrupt.sh'
            corrupt.write_bytes(header.encode() + b'\n__MIAOZI_PAYLOAD__\nbroken')
            with patch('sys.argv', ['check', str(corrupt)]), patch('subprocess.run') as run:
                with self.assertRaises(SystemExit):
                    exec(compile(code, '<self-extractor>', 'exec'), {})
                run.assert_not_called()


if __name__ == '__main__':
    for path in list(ROOT.glob('*.py')) + list((ROOT / 'scripts').glob('*.py')):
        ast.parse(path.read_text(encoding='utf-8'), filename=path.name)
    unittest.main()
