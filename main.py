"""Decky UI and account adapter; acceleration is owned by a separate service."""
import asyncio
import base64
import hashlib
import http.cookiejar
import json
import ipaddress
import os
import socket
import ssl
import re
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

import decky

VERSION = "0.1.0-alpha.9"
BOOTSTRAP = "https://mzjsq.oss-cn-shenzhen.aliyuncs.com/config.json"
ALLOWED_API_HOST = "kxzapi.whythk.cn"
MAX_RESPONSE = 1024 * 1024
SYSTEM_CA_FILES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/ssl/cert.pem",
    "/etc/ca-certificates/extracted/tls-ca-bundle.pem",
)


class UserError(Exception):
    def __init__(self, message, kind="validation", details=None):
        super().__init__(message)
        self.kind = kind
        self.details = details or {}


def create_tls_context():
    """Decky's embedded Python may not find the OS OpenSSL trust paths."""
    context = ssl.create_default_context()
    info = {"default_ca_count": context.cert_store_stats()["x509_ca"],
            "system_bundle_loaded": False, "bundled_ca_loaded": False}
    for location in SYSTEM_CA_FILES:
        if Path(location).is_file():
            try:
                context.load_verify_locations(cafile=location)
                info["system_bundle_loaded"] = True
                break
            except (OSError, ssl.SSLError):
                continue
    bundle = Path(__file__).resolve().parent / "certs" / "cacert.pem"
    if bundle.is_file():
        try:
            context.load_verify_locations(cafile=str(bundle))
            info["bundled_ca_loaded"] = True
        except (OSError, ssl.SSLError):
            raise UserError("随包 HTTPS 根证书无法加载，请完整解压新版安装包后重新安装。", "ca_bundle_invalid") from None
    info["loaded_ca_count"] = context.cert_store_stats()["x509_ca"]
    if not info["loaded_ca_count"]:
        raise UserError("未找到 HTTPS 根证书，请完整安装带有 certs 文件夹的新版本。", "ca_store_empty", info)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.keylog_filename = None
    return context, info


def tls_error(reason):
    details = {}
    verify_code = getattr(reason, "verify_code", None)
    if isinstance(verify_code, int) and 0 <= verify_code <= 1000:
        details["tls_verify_code"] = verify_code
    if isinstance(reason, ssl.SSLCertVerificationError):
        if verify_code in (9, 10):
            return UserError("服务证书有效期验证失败，请确认 Deck 的日期和时间正确。", "tls_certificate_time", details)
        return UserError("HTTPS 证书验证失败，请导出诊断中的证书错误码。", "tls_certificate", details)
    # SSL errors also cover protocol failures and early connection closure.
    # Keep a small fixed enum instead of exporting arbitrary exception text.
    error_reason = getattr(reason, "reason", None)
    allowed_reasons = {"WRONG_VERSION_NUMBER", "UNEXPECTED_EOF_WHILE_READING",
                       "TLSV1_ALERT_PROTOCOL_VERSION", "SSLV3_ALERT_HANDSHAKE_FAILURE",
                       "TLSV1_ALERT_INTERNAL_ERROR", "UNSUPPORTED_PROTOCOL"}
    details["tls_reason"] = error_reason if error_reason in allowed_reasons else "other"
    return UserError("HTTPS 握手失败，请导出诊断。", "tls_handshake", details)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward credentials to a redirect target.
        return None


# Only known schema names can leave the backend. Unknown dictionary keys may
# themselves contain account IDs, addresses or secrets, so only count them.
SCHEMA_KEYS = set("""
code message msg data success status user account username email id token
access_token accessToken auth_data authData authorization bearer session
session_token sessionToken subscription subscriptionUrl subscription_url
subscribe_url subscribeUrl sub_url subUrl url path subscriptionPath
subscriptionToken subscription_path subscription_token protocol version
encrypted payload ciphertext nonce iv tag kid keyId key_id keys expire
expired_at expiredAt expiry expires expires_at traffic upload download
transfer_enable transferEnable plan name type nodes proxies groups config
config_url configUrl refresh_token refreshToken auth checkin
v alg algorithm keyId key_id key nonce tag ciphertext cipher encrypted content
body encryption key_ids keyIds signature sign format
""".split())


def schema(value, depth=0):
    if depth >= 5:
        return type(value).__name__
    if isinstance(value, dict):
        result = {key: schema(item, depth + 1) for key, item in value.items()
                  if key in SCHEMA_KEYS}
        unknown = sum(key not in SCHEMA_KEYS for key in value)
        if unknown:
            result["<unknown_fields>"] = unknown
        return result
    if isinstance(value, list):
        return {"list": schema(value[0], depth + 1) if value else "empty"}
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (float, int)):
        return "number"
    return "string"


def result_code(value):
    code = value.get("code") if isinstance(value, dict) else None
    # Do not copy arbitrary server values into diagnostics.
    if isinstance(code, int) and 0 <= code <= 599:
        return code
    if isinstance(code, str) and code.isdigit() and len(code) <= 3:
        return int(code)
    return None


def token_from(value):
    if not isinstance(value, dict):
        return ""
    for key in ("token", "access_token", "accessToken", "auth_data", "authData",
                "authorization", "session_token", "sessionToken"):
        token = value.get(key)
        if isinstance(token, str) and 0 < len(token) <= 16384 and "\n" not in token and "\r" not in token:
            return token if token.lower().startswith("bearer ") else "Bearer " + token
    for key in ("data", "session", "auth"):
        token = token_from(value.get(key))
        if token:
            return token
    return ""


class AccountClient:
    def __init__(self):
        self.base = ""
        self.last_stage = "idle"
        self.token = ""
        self.tls_info = {}
        self.jar = http.cookiejar.CookieJar()
        self.opener = None

    def clear(self):
        self.token = ""
        self.jar.clear()

    def request(self, url, body=None, auth=False):
        if self.opener is None:
            context, self.tls_info = create_tls_context()
            self.opener = urllib.request.build_opener(
                NoRedirect(), urllib.request.HTTPCookieProcessor(self.jar),
                urllib.request.HTTPSHandler(context=context))
        headers = {"User-Agent": "FlClash/2.0.0", "Accept": "application/json"}
        if auth and self.token:
            headers["Authorization"] = self.token
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            response = self.opener.open(request, timeout=18)
        except urllib.error.HTTPError as exc:
            response = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            if isinstance(reason, socket.gaierror):
                raise UserError("无法解析喵子服务地址，请检查 Deck 的网络或 DNS。", "dns") from None
            if isinstance(reason, ssl.SSLError):
                raise tls_error(reason) from None
            if isinstance(reason, TimeoutError):
                raise UserError("连接喵子服务超时，请检查 Deck 的网络。", "timeout") from None
            raise UserError("无法连接喵子官方服务，请检查网络后再试。", "network") from None
        with response:
            if response.status in (301, 302, 303, 307, 308):
                raise UserError("官方接口发生重定向，已暂停提交账号；需要更新接口适配。", "redirect")
            if response.status >= 500:
                raise UserError("喵子官方服务暂时不可用，请稍后再试。", "server_5xx")
            try:
                content = response.read(MAX_RESPONSE + 1)
            except TimeoutError:
                raise UserError("读取喵子服务返回数据超时。", "read_timeout") from None
            except OSError:
                raise UserError("读取喵子服务返回数据时连接中断。", "read_network") from None
            if len(content) > MAX_RESPONSE:
                raise UserError("接口返回数据过大，已停止读取。", "response_size")
            try:
                value = json.loads(content)
            except (ValueError, UnicodeError):
                raise UserError("官方接口未返回可识别的数据，请导出诊断。", "response_json") from None
            if not isinstance(value, dict):
                raise UserError("官方接口格式发生变化，请导出诊断。", "response_shape")
            return value

    def discover(self):
        self.last_stage = "bootstrap"
        info = self.request(BOOTSTRAP)
        base = info.get("baseUrl", "")
        parsed = urllib.parse.urlsplit(base) if isinstance(base, str) else None
        if not parsed or parsed.scheme != "https" or parsed.hostname != ALLOWED_API_HOST or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise UserError("官方登录域名有变化；核实并更新插件前不会提交账号密码。", "api_host_changed")
        self.base = base.rstrip("/")

    def login(self, account, password):
        self.clear()
        self.discover()
        self.last_stage = "login"
        # These field names are present in the supplied client. Their mapping
        # is provisional until an authenticated response is tested on the Deck.
        return self.request(self.base + "/client-api/login", {
            "account": account, "username": account, "email": account,
            "password": password,
        })

    def session(self):
        self.last_stage = "session"
        return self.request(self.base + "/client-api/session", auth=True)

    def read_subscription(self, url):
        """Read only the URL received through the authenticated official API.

        An isolated opener deliberately sends no account cookies or bearer
        token. A subscription link has its own authorization in the URL.
        """
        if not isinstance(url, str) or len(url) > 16384 or any(char.isspace() for char in url):
            raise UserError("官方返回的订阅地址格式不符。", "subscription_url")
        url = urllib.parse.urljoin(self.base + "/", url)
        try:
            parsed = urllib.parse.urlsplit(url)
            host = parsed.hostname
            if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment:
                raise ValueError()
            if host.lower() == "localhost" or host.lower().endswith((".localhost", ".local")):
                raise ValueError()
            try:
                literal_address = ipaddress.ip_address(host)
            except ValueError:
                literal_address = None
            if literal_address and not literal_address.is_global:
                raise ValueError()
            # Do not pre-resolve domain names here: another active TUN may
            # intentionally return a fake IP. TLS still validates the host.
        except ValueError:
            raise UserError("订阅地址无法解析为有效的 HTTPS 服务。", "subscription_url") from None
        import importlib.util
        spec = importlib.util.spec_from_file_location('miaozi_native_subscription', Path(__file__).with_name('native_subscription.py'))
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        try:
            body = native.update(url, Path(decky.DECKY_PLUGIN_DIR))
        except native.NativeUpdateError as exc:
            raise UserError(str(exc), 'subscription_native') from None
        except (OSError, ValueError, KeyError):
            raise UserError('内置订阅组件初始化失败，请导出诊断以便修复。', 'subscription_native_config') from None
        return body, {'http_status': 200, 'protocol': 'official_component', 'authenticated': True}


def inspect_subscription(body):
    """Classify without exporting response values or assuming a cipher format."""
    info = {}
    try:
        text = body.decode("utf-8-sig").strip()
    except UnicodeError:
        return None, {"format": "binary"}
    try:
        value = json.loads(text)
    except ValueError:
        value = None
    if isinstance(value, dict):
        info = {"format": "json", "schema": schema(value)}
        code = result_code(value)
        if code is not None:
            info["response_code"] = code
        if isinstance(value.get("proxies"), list) or isinstance(value.get("proxy-providers"), dict):
            return text, info
        messages = " ".join(str(value.get(key, "")) for key in ("message", "msg", "error")).lower()
        if "sign" in messages or "签名" in messages:
            info["error_hint"] = "signature_required_or_invalid"
        elif "encrypt" in messages or "加密" in messages:
            info["error_hint"] = "encrypted_protocol"
        elif "auth" in messages or "登录" in messages or "认证" in messages:
            info["error_hint"] = "authorization_required"
        if any(key in value for key in ("ciphertext", "nonce", "encrypted", "iv", "kid", "keyId")):
            info["encrypted_envelope"] = True
        return None, info
    if re.search(r"(?m)^(proxies|proxy-providers)\s*:", text):
        return text, {"format": "yaml"}
    # Legacy subscription exports sometimes encode a YAML document once.
    if re.fullmatch(r"[A-Za-z0-9+/=_\-\s]+", text) and text:
        try:
            decoded = base64.b64decode(re.sub(r"\s", "", text), altchars=b"-_", validate=True).decode("utf-8-sig")
            if re.search(r"(?m)^(proxies|proxy-providers)\s*:", decoded):
                return decoded, {"format": "base64_yaml"}
        except (ValueError, UnicodeError):
            pass
    return None, {"format": "html" if text.lower().startswith(("<!doctype html", "<html")) else "unrecognized_text"}


async def parse_subscription_nodes(text, plugin_dir):
    # Loading through importlib avoids depending on Decky's plugin sys.path.
    import importlib.util
    spec = importlib.util.spec_from_file_location("miaozi_core_session", plugin_dir / "core_session.py")
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    core_path = plugin_dir / "bin" / "FlClashCore"
    metadata = json.loads((plugin_dir / "vendor.json").read_text(encoding="utf-8"))
    if core_path.is_symlink() or hashlib.sha256(core_path.read_bytes()).hexdigest() != metadata["sha256"]:
        raise UserError("原版内核校验失败，请重新安装。", "core_integrity")
    with tempfile.TemporaryDirectory(prefix="mz-sub-") as folder:
        home = Path(folder)
        source = home / "subscription.yaml"
        source.write_text(text, encoding="utf-8")
        source.chmod(0o600)
        core = transport.CoreSession(core_path, home)
        try:
            await core.open()
            raw = await core.request("getConfig", str(source))
            if not isinstance(raw, dict):
                raise UserError("原版内核无法识别订阅配置。", "subscription_parse")
            normalized = {key.lower().replace("-", "").replace("_", ""): val for key, val in raw.items()}
            proxies = normalized.get("proxies", normalized.get("proxy", []))
            providers = normalized.get("proxyproviders", {})
            nodes = []
            if isinstance(proxies, list):
                for proxy in proxies:
                    if isinstance(proxy, dict) and isinstance(proxy.get("name"), str):
                        nodes.append({"name": proxy["name"][:256], "type": str(proxy.get("type", "unknown"))[:48]})
            return nodes, len(providers) if isinstance(providers, dict) else 0
        except transport.CoreError:
            raise UserError("原版内核解析订阅失败，请导出诊断。", "subscription_parse") from None
        finally:
            await core.close()


async def core_check(plugin_dir):
    """Exercise the vendor's real socket protocol without starting listeners."""
    core = plugin_dir / "bin" / "FlClashCore"
    metadata = json.loads((plugin_dir / "vendor.json").read_text(encoding="utf-8"))
    if core.is_symlink() or hashlib.sha256(core.read_bytes()).hexdigest() != metadata["sha256"]:
        raise UserError("原版内核文件不完整，请重新安装测试包。")
    if not os.access(core, os.X_OK):
        raise UserError("内核缺少执行权限，请使用随包安装脚本重新安装。")
    loop = asyncio.get_running_loop()
    connected = loop.create_future()

    async def accept(reader, writer):
        if connected.done():
            writer.close()
        else:
            connected.set_result((reader, writer))

    # Short private path avoids the AF_UNIX path length limit.
    with tempfile.TemporaryDirectory(prefix="miaozi-deck-") as folder:
        socket_path = str(Path(folder) / "core.sock")
        server = await asyncio.start_unix_server(accept, socket_path)
        proc = None
        writer = None
        seq = 0
        try:
            proc = await asyncio.create_subprocess_exec(
                str(core), socket_path, cwd=folder,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            reader, writer = await asyncio.wait_for(connected, 8)

            async def rpc(method, data=None):
                nonlocal seq
                seq += 1
                ident = str(seq)
                writer.write((json.dumps({"id": ident, "method": method, "data": data}) + "\n").encode())
                await writer.drain()

                async def receive():
                    while True:
                        line = await reader.readline()
                        if not line:
                            raise UserError("内核提前退出。")
                        item = json.loads(line)
                        if item.get("id") == ident:
                            if item.get("code") != 0:
                                raise UserError("内核通讯测试未通过。")
                            return item.get("data")
                return await asyncio.wait_for(receive(), 8)

            if not await rpc("initClash", json.dumps({"home-dir": folder, "version": 2026071801})):
                raise UserError("内核初始化失败。")
            (Path(folder) / "config.yaml").write_text(json.dumps({
                "mixed-port": 0, "port": 0, "socks-port": 0,
                "external-controller": "", "mode": "global",
                "tun": {"enable": False}, "dns": {"enable": False},
                "rules": ["MATCH,DIRECT"],
            }), encoding="utf-8")
            error = await rpc("setupConfig", json.dumps({"selected-map": {}, "test-url": "https://www.gstatic.com/generate_204"}))
            if error:
                raise UserError("内核配置测试未通过。")
            groups = await rpc("getProxies")
            if not isinstance(groups, dict) or "proxies" not in groups:
                raise UserError("内核节点接口格式不符。")
            await rpc("shutdown")
            return "passed"
        finally:
            server.close()
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
            # Python 3.12 waits for accepted connections here, so close the
            # client transport before waiting for the listening server.
            await server.wait_closed()
            if proc and proc.returncode is None:
                try:
                    await asyncio.wait_for(proc.wait(), 2)
                except asyncio.TimeoutError:
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), 3)
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()


class Plugin:
    def _ensure(self):
        if not hasattr(self, "client"):
            self.client = AccountClient()
            self.lock = asyncio.Lock()
            self.logged_in = False
            self.message = "在此管理喵子账号与在线订阅。"
            self.auth_message = "已有订阅可继续使用，无需重复登录。"
            self.subscription_url = ""
            self.nodes = []
            self.subscription_state = "not_tested"
            self.subscription_message = "点击同步账号与订阅，获取并应用最新节点。"
            self.cache_proxies = []
            self.cache_meta = {}
            self.cache_error = ""
            self.cache_loaded = False
            self.node_results = {}
            self.selected_node = ""
            self.service_state = {}
            runtime = Path(decky.DECKY_PLUGIN_RUNTIME_DIR)
            try:
                saved = json.loads((runtime / 'node-results.json').read_text())
                self.node_results = {row['name']: row for row in saved.get('tested', []) if isinstance(row.get('name'), str)}
            except (OSError, ValueError, TypeError, KeyError):
                pass
            try:
                self.selected_node = json.loads((runtime / 'selection.json').read_text()).get('node', '')
            except (OSError, ValueError, TypeError):
                pass
            self.report = {"version": VERSION, "acceleration": "not_checked", "core": "not_tested", "auth_state": "not_tested"}

    async def _main(self):
        self._ensure()

    async def _service(self, operation='status', **params):
        writer = None
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_unix_connection('/run/miaozi-deck/control.sock'), 3)
            writer.write((json.dumps({'op': operation, **params}) + '\n').encode())
            await writer.drain()
            self.service_state = json.loads(await asyncio.wait_for(reader.readline(), 55))
        except (OSError, ValueError, asyncio.TimeoutError):
            self.service_state = {'available': False, 'running': False,
                                  'error': '加速服务未就绪，请在 Deck 上运行新版安装脚本。'}
        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
        self.report['acceleration'] = 'running' if self.service_state.get('running') else 'stopped'
        self.report['service_available'] = self.service_state.get('available', False)
        return self.service_state

    async def set_acceleration(self, enabled: bool):
        self._ensure()
        async with self.lock:
            await self._load_cache()
            await self._service('start' if enabled else 'stop')
            return self._dashboard()

    def _module(self, filename):
        import importlib.util
        spec = importlib.util.spec_from_file_location('miaozi_' + filename, Path(decky.DECKY_PLUGIN_DIR) / (filename + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    async def _load_cache(self, force=False):
        if self.cache_loaded and not force:
            return
        try:
            module = self._module('cache_nodes')
            self.cache_proxies, self.cache_meta = await module.read_cache(Path(decky.DECKY_PLUGIN_DIR), decky.DECKY_USER_HOME, decky.DECKY_PLUGIN_RUNTIME_DIR)
            self.cache_error = ''
            self.cache_loaded = True
        except Exception:
            self.cache_proxies = []
            self.cache_error = '无法读取订阅，请在设置中连接账号或重新同步。'

    def _dashboard(self):
        nodes = [{'name': p['name'], 'status': self.node_results.get(p['name'], {}).get('status', 'not_tested'),
                  'delay_ms': self.node_results.get(p['name'], {}).get('delay_ms')}
                 for p in self.cache_proxies]
        return {'subscription': self.cache_meta.get('label', '喵子订阅'), 'source': self.cache_meta.get('source', 'official_local_cache'),
                'cache_updated': self.cache_meta.get('cache_updated'), 'error': self.service_state.get('error') or self.cache_error,
                'official_auto_update': self.cache_meta.get('official_auto_update'),
                'official_update_hours': self.cache_meta.get('official_update_hours'),
                'nodes': nodes, 'selected_node': self.service_state.get('selected_node', self.selected_node),
                'running': self.service_state.get('running', False),
                'service_available': self.service_state.get('available', False),
                'dashboard_url': self.service_state.get('dashboard_url', '')}

    async def get_dashboard(self, refresh: bool = False):
        self._ensure()
        async with self.lock:
            await self._load_cache(force=refresh)
            await self._service('refresh' if refresh else 'status')
            return self._dashboard()

    async def select_node(self, name: str):
        self._ensure()
        async with self.lock:
            await self._load_cache()
            if not isinstance(name, str) or not any(p['name'] == name for p in self.cache_proxies):
                raise UserError('节点不存在。')
            self.selected_node = name
            await self._service('select', name=name)
            runtime = Path(decky.DECKY_PLUGIN_RUNTIME_DIR)
            runtime.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(prefix='selection-', dir=runtime)
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump({'node': name}, output, ensure_ascii=False)
            os.replace(temp, runtime / 'selection.json')
            return self._dashboard()

    async def test_node(self, name: str):
        self._ensure()
        async with self.lock:
            await self._load_cache()
            if not isinstance(name, str) or not any(p['name'] == name for p in self.cache_proxies):
                raise UserError('节点不存在。')
            probe = self._module('node_probe').NodeProbe(Path(decky.DECKY_PLUGIN_DIR) / 'bin/FlClashCore')
            try:
                result = (await probe.test(self.cache_proxies, [name]))[0]
            except Exception:
                result = {'name': name, 'status': 'error', 'delay_ms': None}
            self.node_results[name] = result
            runtime = Path(decky.DECKY_PLUGIN_RUNTIME_DIR)
            runtime.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(prefix='node-results-', dir=runtime)
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump({'tested': list(self.node_results.values())}, output, ensure_ascii=False)
            os.replace(temp, runtime / 'node-results.json')
            return self._dashboard()

    async def get_status(self):
        self._ensure()
        return {"version": VERSION, "logged_in": self.logged_in,
                "message": self.message, "core": self.report["core"],
                "auth_state": self.report["auth_state"], "auth_message": self.auth_message,
                "subscription_state": self.subscription_state,
                "subscription_message": self.subscription_message, "nodes": self.nodes,
                "diagnostic": json.dumps(self.report, ensure_ascii=False, indent=2)}

    async def login(self, account: str, password: str):
        self._ensure()
        async with self.lock:
            self.logged_in = False
            self.subscription_url = ""
            self.nodes = []
            self.subscription_state = "not_tested"
            self.subscription_message = "登录后点击“同步账号与订阅”应用最新节点。"
            self.report.pop("subscription", None)
            self.client.clear()
            self.client.last_stage = "input"
            for key in ("login", "session", "login_code", "session_code", "error", "failure_stage", "failure_kind", "tls_verify_code", "tls_reason", "tls"):
                self.report.pop(key, None)
            self.report["auth_state"] = "checking"
            try:
                if not isinstance(account, str) or not isinstance(password, str) or not account.strip() or not password or len(account) > 512 or len(password) > 4096:
                    raise UserError("请填写账号和密码。")
                result = await asyncio.to_thread(self.client.login, account.strip(), password)
                self.report["login"] = schema(result)
                self.report["login_code"] = result_code(result)
                if result_code(result) != 200:
                    raise UserError("登录未通过，返回码 " + str(result_code(result)) + "。请确认账号密码；若原客户端能登录，请导出诊断，不要反复尝试。", "login_rejected")
                self.client.token = token_from(result)
                session = await asyncio.to_thread(self.client.session)
                self.report["session"] = schema(session)
                self.report["session_code"] = result_code(session)
                if result_code(session) != 200:
                    raise UserError("登录接口已接受，但会话验证未通过。请导出诊断以适配官方认证格式。", "session_rejected")
                self.logged_in = True
                session_data = session.get("data", {})
                if isinstance(session_data, dict) and isinstance(session_data.get("subscriptionUrl"), str):
                    self.subscription_url = session_data["subscriptionUrl"]
                self.report["auth_state"] = "passed"
                self.auth_message = "官方会话验证通过。"
                self.message = "登录成功，可以读取线路。"
            except UserError as exc:
                stage_names = {"input": "填写账号", "bootstrap": "获取官方接口地址", "login": "提交登录", "session": "验证会话"}
                stage = self.client.last_stage
                self.auth_message = stage_names.get(stage, "登录") + "：" + str(exc)
                self.message = "登录未通过，请查看账号状态并导出诊断。"
                self.report["auth_state"] = "failed"
                self.report["error"] = "login_not_ready"
                self.report["failure_stage"] = stage
                self.report["failure_kind"] = exc.kind
                self.report.update(exc.details)
                self.client.clear()
            except Exception:
                self.message = "登录适配出现错误，请导出诊断。"
                self.auth_message = self.message
                self.report["auth_state"] = "failed"
                self.report["error"] = "unexpected_login_error"
                self.report["failure_stage"] = self.client.last_stage
                self.report["failure_kind"] = "unexpected"
                self.client.clear()
            finally:
                self.report["tls"] = dict(getattr(self.client, "tls_info", {}))
                # Passwords are not persisted or logged; normal Python string
                # lifetimes apply (this does not promise memory zeroization).
                password = ""
            return await self.get_status()

    async def refresh_subscription(self):
        self._ensure()
        async with self.lock:
            self.subscription_state = "checking"
            detail = {"state": "checking", "stage": "download"}
            self.report["subscription"] = detail
            try:
                # Subscription links may rotate. Refresh the authenticated
                # account session before retrying a previously rejected URL.
                runtime = Path(decky.DECKY_PLUGIN_RUNTIME_DIR)
                if self.logged_in:
                    session = await asyncio.to_thread(self.client.session)
                    if result_code(session) != 200:
                        raise UserError('登录会话已过期，请重新登录后更新订阅。', 'session_expired')
                    latest = session.get('data', {}).get('subscriptionUrl')
                    if isinstance(latest, str) and latest:
                        detail['url_changed'] = latest != self.subscription_url
                        self.subscription_url = latest
                elif not self.subscription_url:
                    try:
                        self.subscription_url = json.loads((runtime / 'subscription-link.json').read_text())['url']
                    except (OSError, ValueError, KeyError):
                        try:
                            prefs = json.loads((Path(decky.DECKY_USER_HOME) / '.local/share/com.follow.clash/shared_preferences.json').read_text())
                            self.subscription_url = json.loads(prefs['flutter.sspanel_binding'])['lastSubscriptionUrl']
                        except (OSError, ValueError, KeyError):
                            raise UserError('请先登录喵子账号获取订阅。', 'login_required') from None
                if not self.subscription_url:
                    raise UserError("登录成功，但官方未返回可读取的订阅地址。", "subscription_missing")
                body, transport_info = await asyncio.to_thread(self.client.read_subscription, self.subscription_url)
                detail.update(transport_info)
                detail["stage"] = "format"
                config_text, format_info = inspect_subscription(body)
                detail.update(format_info)
                if transport_info["http_status"] != 200:
                    raise UserError(f"在线更新返回 HTTP {transport_info['http_status']}，现有节点已保留，请稍后重试。", "subscription_http")
                if config_text is None:
                    raise UserError("已收到订阅响应，其加密或签名格式仍需适配。请导出诊断。", "subscription_format")
                detail["stage"] = "parse"
                proxies = await self._module('cache_nodes').parse_online(body, Path(decky.DECKY_PLUGIN_DIR))
                # Commit only authenticated, successfully parsed content.
                runtime.mkdir(parents=True, exist_ok=True)
                target = runtime / 'online-subscription.json'
                previous = target.read_bytes() if target.exists() else None
                def persist(path, value):
                    fd, temp = tempfile.mkstemp(prefix='subscription-', dir=runtime)
                    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                        json.dump(value, stream, ensure_ascii=False)
                    os.replace(temp, path)
                if previous is not None:
                    fd, temp = tempfile.mkstemp(prefix='subscription-backup-', dir=runtime)
                    with os.fdopen(fd, 'wb') as stream: stream.write(previous)
                    os.replace(temp, runtime / 'online-subscription.previous.json')
                persist(target, {'version': 1, 'proxies': proxies, 'label': '喵子在线订阅', 'updated_at': time.time()})
                persist(runtime / 'subscription-link.json', {'url': self.subscription_url})
                await self._load_cache(force=True)
                service = await self._service('refresh')
                if service.get('error') or service.get('subscription_source') != 'online':
                    # Roll back disk and live state together when reload fails.
                    if previous is None:
                        target.unlink(missing_ok=True)
                    else:
                        persist(target, json.loads(previous))
                    await self._load_cache(force=True)
                    await self._service('refresh')
                    raise UserError('订阅下载成功，但后台重载失败，已恢复原节点缓存。请安装完整新版后重试。', 'subscription_apply')
                self.nodes = [{'name': p['name'], 'type': p.get('type', '')} for p in proxies]
                detail['node_count'] = len(proxies)
                self.subscription_state = 'updated'
                detail['state'] = 'updated'
                self.subscription_message = f'订阅已同步并应用，共 {len(proxies)} 个节点。'
            except UserError as exc:
                self.subscription_state = "needs_adaptation"
                detail["state"] = self.subscription_state
                detail["failure_kind"] = exc.kind
                detail.update(exc.details)
                self.subscription_message = str(exc)
            except Exception:
                self.subscription_state = "failed"
                detail["state"] = "failed"
                detail["failure_kind"] = "unexpected"
                self.subscription_message = "读取线路时出现适配错误，请导出诊断。"
            self.report["tls"] = dict(getattr(self.client, "tls_info", {}))
            self.message = self.subscription_message
            return await self.get_status()

    async def logout(self):
        self._ensure()
        async with self.lock:
            remote_ok = False
            try:
                if self.logged_in:
                    result = await asyncio.to_thread(self.client.request, self.client.base + "/client-api/logout", {}, True)
                    remote_ok = result_code(result) == 200
            except Exception:
                pass
            finally:
                self.client.clear()
                self.logged_in = False
                self.report["auth_state"] = "signed_out"
                self.auth_message = "已清除本地登录会话。"
                self.subscription_url = ""
                self.nodes = []
                self.subscription_state = "not_tested"
                self.subscription_message = "请先登录。"
            self.message = "已退出登录。" if remote_ok else "本地会话已清除。"
            return await self.get_status()

    async def check_core(self):
        self._ensure()
        async with self.lock:
            try:
                self.report["core"] = await core_check(Path(decky.DECKY_PLUGIN_DIR))
                self.message = "原版内核通讯正常；此测试未启动加速。"
            except UserError as exc:
                self.report["core"] = "failed"
                self.message = str(exc)
            except Exception:
                self.report["core"] = "failed"
                self.message = "内核测试未通过，请导出诊断。"
            return await self.get_status()

    async def export_diagnostic(self):
        self._ensure()
        await self._service()
        folder = Path(decky.DECKY_USER_HOME) / "Downloads"
        folder.mkdir(parents=True, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix="MiaoziDeck-diagnostic-", suffix=".txt", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write("Miaozi Deck — 仅含接口字段类型与状态码，不含字段值。\n")
            output.write(json.dumps(self.report, ensure_ascii=False, indent=2))
        return path

    async def _unload(self):
        self._ensure()
        async with self.lock:
            self.client.clear()
            self.logged_in = False
            self.subscription_url = ""
            self.nodes = []

    async def _uninstall(self):
        await self._unload()
