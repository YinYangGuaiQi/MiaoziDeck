"""Build a local-use installation ZIP from source and separately supplied assets."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    'plugin.json', 'package.json', 'main.py', 'native_subscription.py',
    'acceleration_service.py', 'cache_nodes.py', 'core_session.py',
    'node_probe.py', 'miaozi-deck.service', 'vendor.json', 'README.md', 'bootstrap_profile.py',
)
ASSET_FILES = (
    'bin/FlClashCore', 'certs/cacert.pem', 'certs/LICENSE-certifi',
    'certs/SOURCE.json', 'py_modules/LICENSE-pycryptodomex.rst',
    'py_modules/CRYPTO-SOURCE.json',
)


def checked_file(base, relative):
    path = base / relative
    if not path.is_file() or path.is_symlink():
        raise ValueError(f'Missing or unsafe file: {relative}')
    if any(parent.is_symlink() for parent in path.parents if parent != base.parent):
        raise ValueError(f'Symlink ancestor: {relative}')
    path.resolve().relative_to(base.resolve())
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets-dir', required=True, type=Path)
    parser.add_argument('--frontend-dir', type=Path, default=ROOT / 'dist',
                        help='Built frontend directory (default: dist/)')
    parser.add_argument('--official-dir', type=Path, required=True)
    parser.add_argument('--decky-dir', type=Path, required=True)
    args = parser.parse_args()
    assets = args.assets_dir.absolute()
    entries = [(checked_file(ROOT, name), 'MiaoziDeck/' + name) for name in SOURCE_FILES]
    entries.append((checked_file(args.frontend_dir.absolute(), 'index.js'), 'MiaoziDeck/dist/index.js'))
    entries += [(checked_file(assets, name), 'MiaoziDeck/' + name) for name in ASSET_FILES]
    expected = json.loads((ROOT / 'vendor.json').read_text(encoding='utf-8'))['sha256']
    if hashlib.sha256((assets / 'bin/FlClashCore').read_bytes()).hexdigest() != expected:
        raise ValueError('Vendor core SHA-256 mismatch; refusing to package.')
    official = args.official_dir.absolute()
    decky = args.decky_dir.absolute()
    for name in ('FlClash', 'FlClashCore', 'lib/libapp.so', 'data/icudtl.dat', 'vendor/SOURCES.json'):
        checked_file(official, name)
    if hashlib.sha256((official / 'FlClashCore').read_bytes()).hexdigest() != expected:
        raise ValueError('Bundled official core hash mismatch.')
    for name in ('PluginLoader', 'SOURCE.json', 'LICENSE', 'plugin_loader.service.in'):
        checked_file(decky, name)
    for base, prefix in ((official, 'official'), (decky, 'decky')):
        for path in sorted(base.rglob('*')):
            if path.is_symlink():
                raise ValueError('Runtime symlink is not supported.')
            if not path.is_file():
                continue
            relative = path.relative_to(base).as_posix()
            if path.name in {'metadata.dat','shared_preferences.json','database.sqlite','config.yeml','online-subscription.json','subscription-link.json'}:
                raise ValueError('Private data detected in runtime assets.')
            entries.append((checked_file(base, relative), 'MiaoziDeck/' + prefix + '/' + relative))
    checked_file(assets, 'dashboard/index.html')
    checked_file(assets, 'py_modules/Cryptodome/__init__.py')
    if not any(p.is_file() and 'license' in p.name.lower() for p in (assets / 'dashboard').iterdir()):
        raise ValueError('Keep the Yacd license in dashboard/.')
    if not list((assets / 'py_modules/Cryptodome').rglob('*.so')):
        raise ValueError('Linux Cryptodome native extensions are missing.')
    for folder in ('dashboard', 'py_modules/Cryptodome'):
        for path in sorted((assets / folder).rglob('*')):
            if path.is_symlink():
                raise ValueError(f'Symlink in assets: {path.name}')
            if not path.is_file() or {'__pycache__', 'SelfTest'} & set(path.parts):
                continue
            if path.suffix.lower() in {'.db', '.sqlite', '.key', '.yeml', '.log'} or path.name in {
                'online-subscription.json', 'subscription-link.json', 'shared_preferences.json',
            }:
                raise ValueError(f'Unexpected private-data file in assets: {path.name}')
            relative = path.relative_to(assets).as_posix()
            entries.append((checked_file(assets, relative), 'MiaoziDeck/' + relative))
    entries.append((checked_file(ROOT, 'scripts/install.sh'), 'install.sh'))
    entries.append((checked_file(ROOT, 'scripts/install_decky.sh'), 'MiaoziDeck/install_decky.sh'))
    for relative in ('docs/THIRD_PARTY.md', 'docs/PRIVACY.md', 'docs/PUBLISHING.md', 'docs/DEVELOPMENT.md'):
        entries.append((checked_file(ROOT, relative), 'MiaoziDeck/' + relative))
    version = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']
    output = ROOT / 'release' / f'MiaoziDeck-{version}.zip'
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path, name in entries:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            executable = name in {'install.sh', 'MiaoziDeck/install_decky.sh', 'MiaoziDeck/bin/FlClashCore',
                                 'MiaoziDeck/official/FlClash', 'MiaoziDeck/official/FlClashCore', 'MiaoziDeck/decky/PluginLoader'}
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_name(output.name + '.sha256').write_text(
        f'{digest}  {output.name}\n', encoding='utf-8')
    header = checked_file(ROOT, 'scripts/self_extract.sh').read_text(encoding='utf-8')
    header = header.replace('PAYLOAD_SHA256', digest).replace('\r\n', '\n')
    executable = output.with_suffix('.run')
    with executable.open('xb') as stream:
        stream.write(header.encode('utf-8'))
        stream.write(b'\n__MIAOZI_PAYLOAD__\n')
        stream.write(output.read_bytes())
    executable.chmod(0o755)
    executable.with_name(executable.name + '.sha256').write_text(
        hashlib.sha256(executable.read_bytes()).hexdigest() + '  ' + executable.name + '\n', encoding='utf-8')
    print(f'Created {output.name}; for local use with separately supplied third-party assets.')
    print(f'Created single-file installer: {executable.name}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from None
