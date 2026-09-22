"""Read the official client's existing local cache without modifying it."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile


class CacheError(Exception):
    pass


async def read_cache(plugin, user_home, runtime=None):
    online = (Path(runtime) if runtime else Path(user_home) / 'homebrew/data/MiaoziDeck') / 'online-subscription.json'
    if online.is_file():
        saved = json.loads(online.read_text(encoding='utf-8'))
        proxies = saved.get('proxies')
        if not isinstance(proxies, list) or not proxies or any(not isinstance(p, dict) or not isinstance(p.get('name'), str) for p in proxies):
            raise CacheError('在线订阅缓存格式异常，原客户端缓存未修改。')
        return proxies, {'label': saved.get('label', '喵子在线订阅'), 'cache_updated': saved.get('updated_at'),
                         'source': 'online', 'official_auto_update': None, 'official_update_hours': None}
    root = Path(user_home) / '.local/share/com.follow.clash'
    path = root / 'config.yeml'
    key_path = root / '.fl_clash/metadata.dat'
    if not path.is_file() or not key_path.is_file():
        raise CacheError('尚无订阅，请在插件设置中登录账号并同步订阅。')
    sys.path.insert(0, str(plugin / 'py_modules'))
    try:
        from Cryptodome.Cipher import AES
    finally:
        sys.path.pop(0)
    blob = path.read_bytes()
    key = key_path.read_bytes()
    if len(key) != 32 or len(blob) < 30 or blob[0] != 1:
        raise CacheError('原客户端缓存格式不支持。')
    try:
        plain = AES.new(key, AES.MODE_GCM, nonce=blob[1:13]).decrypt_and_verify(blob[13:-16], blob[-16:])
    except ValueError:
        raise CacheError('原客户端缓存完整性校验失败。') from None
    binary = plugin / 'bin/FlClashCore'
    expected = json.loads((plugin / 'vendor.json').read_text(encoding='utf-8'))['sha256']
    if binary.is_symlink() or hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
        raise CacheError('原版内核校验失败，请重新安装。')
    spec = importlib.util.spec_from_file_location('miaozi_cache_transport', plugin / 'core_session.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='mz-cache-') as folder:
        home = Path(folder)
        config = home / 'source.yaml'
        config.write_bytes(plain)
        config.chmod(0o600)
        del plain
        core = module.CoreSession(binary, home)
        try:
            await core.open()
            raw = await core.request('getConfig', str(config))
        except module.CoreError:
            raise CacheError('原版内核无法解析缓存。') from None
        finally:
            await core.close()
    normalized = {key.lower().replace('-', '').replace('_', ''): value for key, value in raw.items()}
    proxies = normalized.get('proxies', normalized.get('proxy', []))
    proxies = [p for p in proxies if isinstance(p, dict) and isinstance(p.get('name'), str)
               and not p['name'].startswith(('A官网:', 'A若您看不到'))]
    meta = {'label': '喵子订阅', 'cache_updated': path.stat().st_mtime,
            'official_auto_update': None, 'official_update_hours': None}
    try:
        prefs = json.loads((root / 'shared_preferences.json').read_text())
        binding = json.loads(prefs.get('flutter.sspanel_binding', '{}'))
        with sqlite3.connect((root / 'database.sqlite').as_uri() + '?mode=ro', uri=True) as db:
            row = db.execute('SELECT label,auto_update,auto_update_duration_millis FROM profiles WHERE id=?',
                             (binding.get('managedProfileId'),)).fetchone()
        if row:
            meta.update(label=row[0] or '喵子订阅', official_auto_update=bool(row[1]),
                        official_update_hours=round(row[2] / 3600000, 2))
    except (ValueError, OSError, sqlite3.Error, TypeError):
        pass
    return proxies, meta


async def parse_online(plain, plugin):
    """Parse authenticated bytes with the vendor core, exposing no node secrets."""
    spec = importlib.util.spec_from_file_location('miaozi_online_transport', plugin / 'core_session.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='mz-online-') as folder:
        home = Path(folder)
        config = home / 'download.yaml'
        config.write_bytes(plain)
        config.chmod(0o600)
        core = module.CoreSession(plugin / 'bin/FlClashCore', home)
        try:
            await core.open()
            raw = await core.request('getConfig', str(config))
        finally:
            await core.close()
    normalized = {key.lower().replace('-', '').replace('_', ''): value for key, value in raw.items()}
    proxies = [p for p in normalized.get('proxies', []) if isinstance(p, dict) and isinstance(p.get('name'), str)
               and not p['name'].startswith(('A官网:', 'A若您看不到'))]
    if not proxies:
        raise CacheError('在线订阅未包含可用节点，已保留旧配置。')
    return proxies
