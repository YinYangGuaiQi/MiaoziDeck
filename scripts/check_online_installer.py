"""Check online launch of the released desktop payload without installing it."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CODE = (ROOT / 'install.sh').read_text(encoding='utf-8').split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]


class OnlineInstallerChecks(unittest.TestCase):
    def test_released_desktop_launch_and_exit_code(self):
        version = json.loads((ROOT / 'package.json').read_text())['version']
        name = f'MiaoziDeck-{version}.desktop'
        extracted = []

        def simulated_bash(args, **kwargs):
            self.assertEqual(args[0], 'bash')
            self.assertEqual(len(args), 2)
            self.assertEqual(kwargs, {'check': False})
            shell = Path(args[1])
            self.assertIn(b'\n__MIAOZI_PAYLOAD__\n', shell.read_bytes())
            extracted.append(shell)
            return subprocess.CompletedProcess(args, 23)

        with patch('sys.argv', ['online', str(ROOT / 'release'), name]), patch('subprocess.run', side_effect=simulated_bash) as run:
            with self.assertRaises(SystemExit) as ended:
                exec(compile(CODE, '<online-install>', 'exec'), {})
            self.assertEqual(ended.exception.code, 23)
            run.assert_called_once()
        self.assertFalse(extracted[0].exists())

    def test_bad_checksum_never_executes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            name = 'corrupt.desktop'
            (root / name).write_text('[Desktop Entry]\nExec=invalid\n', encoding='utf-8')
            (root / (name + '.sha256')).write_text('0' * 64 + '  ' + name + '\n', encoding='utf-8')
            with patch('sys.argv', ['online', folder, name]), patch('subprocess.run') as run:
                with self.assertRaises(SystemExit) as ended:
                    exec(compile(CODE, '<online-install>', 'exec'), {})
                self.assertEqual(ended.exception.code, '安装文件校验失败。')
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
