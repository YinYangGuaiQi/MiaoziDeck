"""Independent per-machine service. The installer grants only network capabilities.

Control socket is owner-only; the core API is loopback-only and authenticated.
Closing Decky or changing Steam sessions does not stop this process.
"""
import asyncio
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import urllib.request
import urllib.parse

from cache_nodes import read_cache
from core_session import CoreSession

APP = Path(__file__).resolve().parent
GROUP = '喵子节点'
PORT = 17891
SOCKET = Path('/run/miaozi-deck/control.sock')
STATE = Path('/var/lib/miaozi-deck/state')


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False)
    os.replace(temp, path)


class Service:
    def __init__(self, state=STATE, tun=True):
        self.state = state
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.core = CoreSession(APP / 'bin/FlClashCore', state)
        self.lock = asyncio.Lock()
        self.running = False
        self.ready = False
        self.error = ''
        self.tun_enabled = tun
        self.selected = ''
        self.proxies = []
        self.meta = {}
        self.desired = False
        try:
            saved = json.loads((state / 'settings.json').read_text())
            self.selected = saved.get('node', '')
            self.desired = saved.get('enabled', False) is True
        except (OSError, ValueError):
            pass
        tokenfile = state / 'api-secret'
        if not tokenfile.exists():
            fd = os.open(tokenfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                stream.write(secrets.token_urlsafe(32))
        self.secret = tokenfile.read_text().strip()

    def save(self):
        atomic_json(self.state / 'settings.json', {'node': self.selected, 'enabled': self.desired})

    def tun(self, enabled):
        return {'enable': enabled, 'device': 'mzdeck', 'stack': 'mixed',
                'auto-route': True, 'auto-detect-interface': True,
                'dns-hijack': ['any:53', 'tcp://any:53'], 'route-address': [],
                'route-exclude-address': ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fe80::/10', 'fc00::/7'],
                'inet6-address': ['fdfe:dcba:9876::1/126'], 'mtu': 1500,
                'iproute2-table-index': 2079, 'iproute2-rule-index': 9079}

    def api(self, path):
        request = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}',
                    headers={'Authorization': 'Bearer ' + self.secret})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=3) as response:
            return json.load(response)

    async def prepare(self):
        self.ready = False
        await self.core.close()
        shutil.copytree(APP / 'dashboard', self.state / 'dashboard', dirs_exist_ok=True)
        self.proxies, self.meta = await read_cache(APP, '/home/deck')
        if not self.proxies:
            raise RuntimeError('缓存没有可用节点。')
        names = [item['name'] for item in self.proxies]
        if self.selected not in names:
            # Prefer a previously measured working node, without retesting all nodes.
            try:
                results = json.loads(Path('/home/deck/homebrew/data/MiaoziDeck/node-results.json').read_text())['tested']
                candidates = sorted((r for r in results if r.get('status') == 'reachable' and r['name'] in names),
                                    key=lambda r: r.get('delay_ms') or 999999)
                self.selected = candidates[0]['name'] if candidates else names[0]
            except (OSError, ValueError, KeyError, TypeError):
                self.selected = names[0]
        config = {
            'proxies': self.proxies, 'proxy-groups': [{'name': GROUP, 'type': 'select', 'proxies': names}],
            'mode': 'rule', 'mixed-port': 17890, 'allow-lan': False, 'bind-address': '127.0.0.1',
            'external-controller': f'127.0.0.1:{PORT}', 'secret': self.secret,
            'external-ui': 'dashboard', 'log-level': 'silent',
            'ipv6': True, 'find-process-mode': 'off', 'profile': {'store-selected': True},
            'tun': self.tun(False),
            'dns': {'enable': True, 'listen': '127.0.0.1:17853', 'ipv6': True,
                    'enhanced-mode': 'fake-ip', 'fake-ip-range': '198.18.0.1/16',
                    'fake-ip-filter': ['*.lan', '*.local'],
                    'default-nameserver': ['223.5.5.5', '119.29.29.29'],
                    'proxy-server-nameserver': ['223.5.5.5', '119.29.29.29'],
                    'nameserver': ['https://dns.alidns.com/dns-query', 'https://doh.pub/dns-query']},
            'rules': ['IP-CIDR,127.0.0.0/8,DIRECT,no-resolve', 'IP-CIDR,10.0.0.0/8,DIRECT,no-resolve',
                      'IP-CIDR,172.16.0.0/12,DIRECT,no-resolve', 'IP-CIDR,192.168.0.0/16,DIRECT,no-resolve',
                      'IP-CIDR6,fc00::/7,DIRECT,no-resolve', 'IP-CIDR6,fe80::/10,DIRECT,no-resolve', f'MATCH,{GROUP}'],
        }
        atomic_json(self.state / 'config.yaml', config)
        await self.core.open()
        result = await self.core.request('setupConfig', json.dumps({'selected-map': {GROUP: self.selected},
                                         'test-url': 'https://www.gstatic.com/generate_204'}), timeout=25)
        if result:
            raise RuntimeError('内核未接受加速配置。')
        await asyncio.to_thread(self.api, '/version')
        self.ready = True

    async def start(self):
        if self.running:
            return
        if not self.core.alive or not self.ready:
            await self.prepare()
        # Refuse to compete with another TUN. Never stop another client's process.
        if self.tun_enabled:
            for iface in Path('/sys/class/net').iterdir():
                if (iface / 'tun_flags').exists() and iface.name != 'mzdeck':
                    raise RuntimeError('检测到其他 VPN 虚拟网卡，请先关闭原客户端的 TUN。')
        try:
            result = await self.core.request('updateConfig', json.dumps({'tun': self.tun(self.tun_enabled)}))
            if result:
                raise RuntimeError('无法启用虚拟网卡。')
            await self.core.request('startListener')
            if self.tun_enabled:
                for _ in range(20):
                    if Path('/sys/class/net/mzdeck').exists():
                        break
                    await asyncio.sleep(0.1)
                else:
                    raise RuntimeError('虚拟网卡未创建，请重新运行安装脚本授予网络权限。')
            self.running = True
            self.desired = True
            self.error = ''
            self.save()
        except Exception:
            await self.stop()
            raise

    async def stop(self):
        try:
            if self.core.alive:
                await self.core.request('stopListener')
                await self.core.request('updateConfig', json.dumps({'tun': self.tun(False)}))
        finally:
            self.running = False
            self.desired = False
            self.save()

    async def status(self):
        if self.core.alive:
            try:
                current = await asyncio.to_thread(self.api, '/proxies/' + urllib.parse.quote(GROUP, safe=''))
                now = current.get('now', '')
                if now and now != self.selected:
                    self.selected = now
                    self.save()
            except Exception:
                pass
        active = self.running and self.core.alive and (not self.tun_enabled or Path('/sys/class/net/mzdeck').exists())
        return {'available': True, 'running': active, 'selected_node': self.selected,
                'error': self.error, 'node_count': len(self.proxies),
                'subscription_source': self.meta.get('source', 'official_local_cache'),
                'cache_updated': self.meta.get('cache_updated'),
                'dashboard_url': f'http://127.0.0.1:{PORT}/ui/?' + urllib.parse.urlencode({
                    'hostname': '127.0.0.1', 'port': PORT, 'secret': self.secret, 'theme': 'dark'})}

    async def handle(self, reader, writer):
        try:
            request = json.loads(await asyncio.wait_for(reader.readline(), 5))
            async with self.lock:
                operation = request.get('op')
                if operation == 'start':
                    await self.start()
                elif operation == 'stop':
                    await self.stop()
                elif operation == 'refresh':
                    wanted = self.desired
                    try:
                        await self.stop()
                        await self.core.close()
                        await self.prepare()
                        if wanted:
                            await self.start()
                        self.error = ''
                    except Exception:
                        # Preserve intent so the backend's rollback can restart
                        # the old working subscription instead of leaving it off.
                        self.desired = wanted
                        self.save()
                        raise
                elif operation == 'select':
                    name = request.get('name')
                    if not any(p['name'] == name for p in self.proxies):
                        raise RuntimeError('节点不存在。')
                    await self.core.request('changeProxy', json.dumps({'group-name': GROUP, 'proxy-name': name}))
                    self.selected = name
                    self.save()
                elif operation != 'status':
                    raise RuntimeError('不支持此操作。')
                response = await self.status()
        except RuntimeError as exc:
            self.error = str(exc)
            response = {'available': True, 'running': self.running, 'error': str(exc)}
        except Exception:
            response = {'available': True, 'running': False, 'error': '后台操作失败，请导出诊断。'}
        writer.write((json.dumps(response) + '\n').encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()


async def main():
    os.umask(0o077)
    service = Service()
    SOCKET.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    SOCKET.unlink(missing_ok=True)
    server = await asyncio.start_unix_server(service.handle, str(SOCKET), limit=16384)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        try:
            await service.prepare()
            if service.desired:
                await service.start()
        except Exception:
            if not Path('/home/deck/homebrew/data/MiaoziDeck/online-subscription.json').is_file() and not Path('/home/deck/.local/share/com.follow.clash/config.yeml').is_file():
                service.error = '尚未配置订阅，请在插件设置中登录账号。'
            else:
                service.error = '后台准备失败，请关闭其他 VPN 后重新开启加速。'
            await service.core.close()
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), 5)
            except asyncio.TimeoutError:
                async with service.lock:
                    if service.ready and service.core.alive:
                        await service.status()
    finally:
        server.close()
        await server.wait_closed()
        await service.core.close()
        SOCKET.unlink(missing_ok=True)


if __name__ == '__main__':
    asyncio.run(main())
