"""Offline checks for the desktop installer; never launch Bash or install software."""
import argparse
import base64
from pathlib import Path
import re
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from urllib.parse import quote

from desktop_package import write_desktop


def load_embedded_launcher(desktop):
    command = None
    with desktop.open('r', encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('Exec='):
                command = line[5:].rstrip('\r\n')
                break
    match = re.fullmatch(
        r'''python3 -c "import base64;exec\(base64\.b64decode\('([A-Za-z0-9+/=]+)'\)\)" %k''',
        command or '',
    )
    if not match:
        raise AssertionError('Exec must pass %k as its own argument to the embedded loader')
    module = types.ModuleType('_miaozi_desktop_offline_test')
    exec(base64.b64decode(match.group(1), validate=True), module.__dict__)
    return module


class DesktopInstallerChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='miaozi-desktop-check-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.payload = b'#!/usr/bin/env bash\nprintf "offline fixture only\\n"\n'
        shell = self.root / 'fixture.sh'
        shell.write_bytes(self.payload)
        self.desktop = write_desktop(shell, Path(__file__).with_name('desktop_launch.py'))
        self.launcher = load_embedded_launcher(self.desktop)

    def test_local_and_uri_paths_remain_data(self):
        # Windows cannot create these Linux filenames. Map only the final file
        # read to the real fixture, after checking the real source_path result.
        linux_path = '/tmp/中文 空格 单引号\' 双引号" $;安装.desktop'
        locations = (
            linux_path,
            'file://' + quote(linux_path, safe='/'),
            'file://localhost' + quote(linux_path, safe='/'),
        )
        real_extract = self.launcher.extract_shell
        for location in locations:
            with self.subTest(location=location):
                extracted = []

                def mapped_extract(source, target):
                    self.assertEqual(source, Path(linux_path))
                    real_extract(self.desktop, target)

                def simulated_bash(arguments, **kwargs):
                    self.assertEqual(arguments[0], 'bash')
                    self.assertEqual(len(arguments), 2)
                    self.assertEqual(kwargs, {'check': False})
                    target = Path(arguments[1])
                    self.assertEqual(target.read_bytes(), self.payload)
                    extracted.append(target)
                    return subprocess.CompletedProcess(arguments, 17)

                with patch.object(self.launcher, 'extract_shell', mapped_extract), patch.object(
                    self.launcher.subprocess, 'run', side_effect=simulated_bash
                ) as run:
                    self.assertEqual(self.launcher.install(location), 17)
                    run.assert_called_once()
                self.assertEqual(len(extracted), 1)
                self.assertFalse(extracted[0].exists())
                self.assertFalse(extracted[0].parent.exists())

    def test_corrupt_or_truncated_payload_never_runs(self):
        original = self.desktop.read_text(encoding='utf-8')
        marker = '# __MIAOZI_SHELL_BASE64__\n'
        before, payload = original.split(marker, 1)
        data_start = payload.index('# ') + 2
        replacement = 'A' if payload[data_start] != 'A' else 'B'
        corrupt = before + marker + payload[:data_start] + replacement + payload[data_start + 1:]
        truncated = original.replace('# __MIAOZI_SHELL_END__\n', '')
        for name, contents in (('corrupt', corrupt), ('truncated', truncated)):
            with self.subTest(case=name):
                source = self.root / (name + '.desktop')
                source.write_text(contents, encoding='utf-8')
                extracted = []
                real_extract = self.launcher.extract_shell

                def record_extract(location, target):
                    extracted.append(target)
                    return real_extract(location, target)

                with patch.object(self.launcher, 'extract_shell', record_extract), patch.object(
                    self.launcher.subprocess, 'run'
                ) as run:
                    with self.assertRaises(ValueError):
                        self.launcher.install(str(source))
                    run.assert_not_called()
                self.assertEqual(len(extracted), 1)
                self.assertFalse(extracted[0].exists())
                self.assertFalse(extracted[0].parent.exists())


def check_artifact(desktop):
    """Decode and checksum an optional full release, mocking its Bash execution."""
    launcher = load_embedded_launcher(desktop)
    extracted = []

    def simulated_bash(arguments, **kwargs):
        if len(arguments) != 2 or arguments[0] != 'bash' or kwargs != {'check': False}:
            raise AssertionError('Unexpected installer invocation')
        target = Path(arguments[1])
        with target.open('rb') as stream:
            if stream.readline().rstrip() != b'#!/usr/bin/env bash':
                raise AssertionError('The embedded installer is not a Bash script')
        extracted.append(target)
        return subprocess.CompletedProcess(arguments, 0)

    with patch.object(launcher.subprocess, 'run', side_effect=simulated_bash) as run:
        if launcher.install(str(desktop.resolve())) != 0:
            raise AssertionError('Installer return code was not forwarded')
        run.assert_called_once()
    if not extracted or extracted[0].exists() or extracted[0].parent.exists():
        raise AssertionError('Temporary installer was not cleaned up')
    print('Full desktop artifact: checksum, extraction, invocation and cleanup passed (installation mocked).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, help='Optional full .desktop release to decode offline')
    arguments = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(DesktopInstallerChecks)
    )
    if not result.wasSuccessful():
        raise SystemExit(1)
    if arguments.artifact:
        check_artifact(arguments.artifact)
