"""Test real proxy connections using the supplied vendor core, without TUN.

This module is ready for integration once the official subscription loads.
It does not label core startup, DNS resolution or direct traffic as a node test.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile

TEST_URL = "https://www.gstatic.com/generate_204"


class NodeProbe:
    def __init__(self, executable: Path):
        spec = importlib.util.spec_from_file_location("miaozi_probe_transport", Path(__file__).with_name("core_session.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.transport = module
        self.executable = executable

    async def test(self, proxies, names, timeout_ms=6000, test_url=TEST_URL):
        if not isinstance(proxies, list) or not isinstance(names, list) or not names:
            raise ValueError("需要实际节点配置及待测节点。")
        if not 1000 <= timeout_ms <= 15000 or len(names) > 20:
            raise ValueError("单批最多测试 20 个节点。")
        by_name = {}
        for proxy in proxies:
            if not isinstance(proxy, dict) or not isinstance(proxy.get("name"), str):
                raise ValueError("节点配置格式不符。")
            name = proxy["name"]
            if name in by_name or name in ("DIRECT", "REJECT", "GLOBAL"):
                raise ValueError("节点名称重复或使用保留名称。")
            if str(proxy.get("type", "")).lower() in ("direct", "reject", "reject-drop", "pass", "compatible"):
                continue
            by_name[name] = proxy
        if len(names) != len(set(names)) or any(name not in by_name for name in names):
            raise ValueError("待测列表包含无效节点。")

        with tempfile.TemporaryDirectory(prefix="mz-probe-") as folder:
            home = Path(folder)
            # Preserve protocol-specific fields (including Miaozi's custom
            # protocol). Do not import a subscription's ports, TUN, DNS or UI.
            config = {
                "proxies": list(by_name.values()), "proxy-groups": [],
                "mixed-port": 0, "port": 0, "socks-port": 0,
                "redir-port": 0, "tproxy-port": 0,
                "external-controller": "", "external-ui": "",
                "allow-lan": False, "mode": "rule",
                "tun": {"enable": False}, "dns": {"enable": False},
                "rules": ["MATCH,DIRECT"], "log-level": "silent",
            }
            config_path = home / "config.yaml"
            # YAML readers reject JSON's escaped surrogate pairs for flag
            # emoji. Emit UTF-8 directly for the vendor's YAML parser.
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            config_path.chmod(0o600)
            core = self.transport.CoreSession(self.executable, home)
            try:
                await core.open()
                failure = await core.request("setupConfig", json.dumps({"selected-map": {}, "test-url": test_url}))
                if failure:
                    # The core's parse error can mention a credential. Strip
                    # every string value from the supplied proxy definitions.
                    secrets = set()
                    def collect(value):
                        if isinstance(value, str) and value:
                            secrets.add(value)
                        elif isinstance(value, dict):
                            for item in value.values(): collect(item)
                        elif isinstance(value, list):
                            for item in value: collect(item)
                    collect(proxies)
                    safe = str(failure)
                    for value in sorted(secrets, key=len, reverse=True):
                        safe = safe.replace(value, '<value>')
                    raise self.transport.CoreError("内核不能加载待测配置：" + safe[:300])
                throttle = asyncio.Semaphore(3)

                async def one(name):
                    async with throttle:
                        try:
                            response = await core.request("asyncTestDelay", json.dumps({
                                "proxy-name": name, "test-url": test_url, "timeout": timeout_ms,
                            }), timeout=timeout_ms / 1000 + 3)
                            result = json.loads(response) if isinstance(response, str) else response
                            value = result.get("value") if isinstance(result, dict) else None
                            if isinstance(value, int) and value > 0:
                                return {"name": name, "status": "reachable", "delay_ms": value}
                            return {"name": name, "status": "unreachable", "delay_ms": None}
                        except (self.transport.CoreError, ValueError):
                            return {"name": name, "status": "error", "delay_ms": None}

                return await asyncio.gather(*(one(name) for name in names))
            finally:
                await core.close()
