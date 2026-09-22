"""Run the vendor's complete update/decryption flow in a private scratch profile.

No original settings or accounts are changed. Only a newly updated, authenticated
profile is returned. A stale copied profile can never count as an online update.
"""
import json
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time


class NativeUpdateError(Exception):
    pass


def graphical_environment():
    """Steam's live session is authoritative; gamescope need not import DISPLAY
    into the systemd user manager. Never guess an X display number.
    """
    env = dict(os.environ)
    env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}', DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    keys = ('DISPLAY', 'XAUTHORITY', 'WAYLAND_DISPLAY', 'XDG_SESSION_TYPE')
    candidates = []
    try:
        result = subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', 'steam'],
                                capture_output=True, text=True, timeout=3)
        for pid in result.stdout.split():
            if not pid.isdecimal():
                continue
            try:
                process_env = dict(item.split('=', 1) for item in
                                   Path(f'/proc/{pid}/environ').read_bytes().decode(errors='replace').split('\0') if '=' in item)
                candidates.append({key: process_env[key] for key in keys if key in process_env})
            except OSError:
                continue
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        result = subprocess.run(['systemctl', '--user', 'show-environment'], env=env,
                                capture_output=True, text=True, timeout=5)
        candidates.append(dict(line.split('=', 1) for line in result.stdout.splitlines()
                               if '=' in line and line.split('=', 1)[0] in keys))
    except (OSError, subprocess.TimeoutExpired):
        pass
    candidates.append({key: env[key] for key in keys if key in env})
    for session in candidates:
        if not session.get('DISPLAY'):
            continue
        candidate = {key: value for key, value in env.items() if key not in keys}
        candidate.update(session)
        # Check access, not just the presence of a possibly stale DISPLAY.
        if shutil.which('xdotool'):
            try:
                check = subprocess.run(['xdotool', 'getdisplaygeometry'], env=candidate,
                                       capture_output=True, timeout=2)
                if check.returncode != 0:
                    continue
            except (OSError, subprocess.TimeoutExpired):
                continue
        return candidate
    raise NativeUpdateError('无法连接当前 Steam 显示会话，旧节点继续使用。请退出设置后重试。')


def update(url, plugin_dir, timeout=65):
    original = Path('/home/deck/.local/share/com.follow.clash')
    application = plugin_dir / 'official'
    if not (application / 'FlClash').is_file():
        application = Path('/home/deck/Miaozi-SteamDeck')
    if not (application / 'FlClash').is_file():
        raise NativeUpdateError('内置订阅组件缺失，请重新运行完整安装文件。')
    env = graphical_environment()
    with tempfile.TemporaryDirectory(prefix='miaozi-sync-') as folder:
        root = Path(folder)
        data = root / 'data/com.follow.clash'
        data.mkdir(parents=True)
        env.update(XDG_DATA_HOME=str(root / 'data'), XDG_CONFIG_HOME=str(root / 'config'),
                   XDG_STATE_HOME=str(root / 'state'), GDK_BACKEND='x11',
                   LD_LIBRARY_PATH=str(application / 'vendor') + ':' + str(application / 'lib'))
        # Existing installations retain the already verified legacy path. New
        # installations create an isolated profile from bundled components.
        try:
            prefs = json.loads((original / 'shared_preferences.json').read_text())
            binding = json.loads(prefs.get('flutter.sspanel_binding', '{}'))
            profile_id = int(binding['managedProfileId'])
            legacy = all((original / relative).is_file() for relative in (
                'config.yeml', '.fl_clash/metadata.dat', 'database.sqlite', f'profiles/{profile_id}.yeml'))
        except (OSError, ValueError, TypeError, KeyError):
            legacy = False
        if not legacy:
            spec = importlib.util.spec_from_file_location('miaozi_bootstrap', plugin_dir / 'bootstrap_profile.py')
            bootstrap = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bootstrap)
            try:
                profile_id = bootstrap.prepare(data, application, env, plugin_dir, url)
            except bootstrap.BootstrapError as exc:
                raise NativeUpdateError(str(exc)) from None
            original = data
            prefs = json.loads((data / 'shared_preferences.json').read_text())
        profile_name = str(profile_id) + '.yeml'
        for relative in ('config.yeml', '.fl_clash/metadata.dat', 'profiles/' + profile_name):
            destination = data / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if original != data:
                shutil.copy2(original / relative, destination)
        # Keep the active profile and vendor serialization, without bringing
        # another account's cookie jar into this one-shot subscription update.
        prefs['flutter.sspanel_binding'] = '{}'
        config = json.loads(prefs.get('flutter.config', '{}'))
        settings = config.setdefault('appSettingProps', {})
        settings.update(autoRun=False, autoLaunch=False)
        prefs['flutter.config'] = json.dumps(config, ensure_ascii=False)
        (data / 'shared_preferences.json').write_text(json.dumps(prefs, ensure_ascii=False), encoding='utf-8')
        if original != data:
            with sqlite3.connect((original / 'database.sqlite').as_uri() + '?mode=ro', uri=True) as source:
                with sqlite3.connect(data / 'database.sqlite') as destination:
                    source.backup(destination)
        with sqlite3.connect(data / 'database.sqlite') as destination:
            destination.execute('UPDATE profiles SET auto_update=0')
            destination.execute('UPDATE profiles SET url=?,last_update_date=0,auto_update=1,auto_update_duration_millis=1000 WHERE id=?', (url, profile_id))
        profile = data / 'profiles' / profile_name
        before = profile.stat().st_mtime_ns
        env.update(XDG_DATA_HOME=str(root / 'data'), XDG_CONFIG_HOME=str(root / 'config'),
                   XDG_STATE_HOME=str(root / 'state'), GDK_BACKEND='x11',
                   LD_LIBRARY_PATH=str(application / 'vendor') + ':' + str(application / 'lib'))
        process = subprocess.Popen([str(application / 'FlClash')],
                    cwd=application, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        started = time.monotonic()
        hidden = set()
        try:
            while time.monotonic() - started < timeout:
                if profile.stat().st_mtime_ns != before:
                    with sqlite3.connect((data / 'database.sqlite').as_uri() + '?mode=ro', uri=True, timeout=2) as db:
                        row = db.execute('SELECT last_update_date,url FROM profiles WHERE id=?', (profile_id,)).fetchone()
                    if row and row[0] and row[1] == url:
                        sys.path.insert(0, str(plugin_dir / 'py_modules'))
                        try:
                            from Cryptodome.Cipher import AES
                        finally:
                            sys.path.pop(0)
                        blob = profile.read_bytes()
                        key = (data / '.fl_clash/metadata.dat').read_bytes()
                        if len(key) != 32 or len(blob) < 30 or blob[0] != 1:
                            raise NativeUpdateError('官方组件返回的缓存格式发生变化，旧订阅已保留。')
                        try:
                            return AES.new(key, AES.MODE_GCM, nonce=blob[1:13]).decrypt_and_verify(blob[13:-16], blob[-16:])
                        except ValueError:
                            raise NativeUpdateError('更新后的订阅未通过完整性校验，旧订阅已保留。') from None
                if process.poll() is not None:
                    raise NativeUpdateError('官方更新组件提前退出，旧订阅已保留。')
                # Hide only windows belonging to this disposable helper.
                try:
                    children = Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
                    for child in [str(process.pid), *children]:
                        if Path(f'/proc/{child}/comm').read_text().strip() != 'FlClash':
                            continue
                        windows = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', child], env=env,
                                    capture_output=True, text=True, timeout=1).stdout.split()
                        for window in windows:
                            if window not in hidden:
                                subprocess.run(['xdotool', 'windowunmap', window], env=env, capture_output=True, timeout=1)
                                hidden.add(window)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                time.sleep(0.3)
            raise NativeUpdateError('在线同步超时，旧节点继续使用。请确认账号订阅有效后重试。')
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
