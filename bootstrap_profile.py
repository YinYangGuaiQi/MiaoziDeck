"""Prepare a new disposable vendor profile without any user's saved account.

The bundled application creates its own database schema. We seed only known
profile fields; unknown mandatory columns fail closed rather than invent values.
This bootstrap needs a real SteamOS first-run acceptance test.
"""
import json
from contextlib import closing
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time


class BootstrapError(Exception):
    pass


def stop_helper(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)


def hide_helper(process, env, hidden):
    try:
        children = Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
        for pid in [str(process.pid), *children]:
            if Path(f'/proc/{pid}/comm').read_text().strip() != 'FlClash':
                continue
            windows = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', pid],
                                     env=env, capture_output=True, text=True, timeout=1).stdout.split()
            for window in windows:
                if window not in hidden:
                    subprocess.run(['xdotool', 'windowunmap', window], env=env,
                                   capture_output=True, timeout=1)
                    hidden.add(window)
    except (OSError, subprocess.TimeoutExpired):
        pass


def write_private(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(content)


def seed_preferences(data, profile_id=None):
    path = data / 'shared_preferences.json'
    prefs = json.loads(path.read_text()) if path.exists() else {}
    config = json.loads(prefs.get('flutter.config', '{}'))
    config.setdefault('appSettingProps', {}).update(
        autoRun=False, autoLaunch=False, autoCheckUpdate=False, silentLaunch=True)
    config.setdefault('vpnProps', {}).update(enable=False, systemProxy=False)
    config['currentProfileId'] = profile_id
    prefs['flutter.config'] = json.dumps(config, ensure_ascii=False)
    prefs['flutter.sspanel_binding'] = '{}'
    write_private(path, json.dumps(prefs, ensure_ascii=False).encode())


def seed_profile(database, url, profile_id):
    values = {'id': profile_id, 'label': '喵子订阅', 'url': url,
              'last_update_date': 0, 'auto_update': 1,
              'auto_update_duration_millis': 1000, 'selected_map': '{}',
              'unfold_set': '[]', 'overwrite_type': 'standard'}
    with closing(sqlite3.connect(database, timeout=3)) as db, db:
        columns = db.execute('PRAGMA table_info(profiles)').fetchall()
        names = {row[1] for row in columns}
        required = {'id', 'url', 'auto_update', 'auto_update_duration_millis', 'last_update_date'}
        if not required.issubset(names):
            raise BootstrapError('内置组件的订阅数据格式不匹配，请导出诊断。')
        for _, name, _, not_null, default, _ in columns:
            if not_null and default is None and name not in values:
                raise BootstrapError('内置组件出现未知的必填配置字段，请导出诊断。')
        selected = [name for name in values if name in names]
        db.execute('UPDATE profiles SET auto_update=0')
        db.execute('INSERT INTO profiles (' + ','.join('"' + name + '"' for name in selected)
                   + ') VALUES (' + ','.join('?' for _ in selected) + ')',
                   [values[name] for name in selected])


def prepare(data, application, env, plugin_dir, url, timeout=25):
    sys.path.insert(0, str(plugin_dir / 'py_modules'))
    try:
        from Cryptodome.Cipher import AES
    finally:
        sys.path.pop(0)

    def encrypted(key, plain):
        nonce = os.urandom(12)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        content, tag = cipher.encrypt_and_digest(plain)
        return b'\x01' + nonce + content + tag

    # No shared seed key and no customer subscription is put in the installer.
    key_path = data / '.fl_clash/metadata.dat'
    write_private(key_path, os.urandom(32))
    seed = b'mixed-port: 0\nallow-lan: false\ntun:\n  enable: false\nproxies: []\nproxy-groups: []\nrules: []\n'
    write_private(data / 'config.yeml', encrypted(key_path.read_bytes(), seed))
    seed_preferences(data)
    process = subprocess.Popen([str(application / 'FlClash')], cwd=application, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    deadline = time.monotonic() + timeout
    database = data / 'database.sqlite'
    hidden = set()
    ready = False
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise BootstrapError('内置组件初始化时退出，请导出诊断。')
            if database.is_file():
                try:
                    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
                        ready = bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='profiles'").fetchone())
                except sqlite3.Error:
                    pass
            hide_helper(process, env, hidden)
            if ready:
                break
            time.sleep(0.3)
    finally:
        stop_helper(process)
    if not ready:
        raise BootstrapError('内置组件初始化超时，请导出诊断。')
    profile_id = int(time.time() * 1000)
    seed_profile(database, url, profile_id)
    seed_preferences(data, profile_id)
    key = key_path.read_bytes()
    if len(key) != 32:
        raise BootstrapError('内置组件生成的本机密钥格式不匹配。')
    profile = data / 'profiles' / f'{profile_id}.yeml'
    write_private(profile, encrypted(key, seed))
    return profile_id
