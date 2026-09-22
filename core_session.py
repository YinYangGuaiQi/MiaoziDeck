"""Vendor IPC transport for the future independent acceleration service.

This module is not enabled by the login preview. The eventual service owns
this session; opening or closing the Decky frontend must not own its lifetime.
"""
import asyncio
import json
from pathlib import Path
import tempfile


class CoreError(Exception):
    """A safe, fixed message, without vendor configuration or credentials."""


class CoreSession:
    def __init__(self, executable: Path, home: Path):
        self.executable = executable
        self.home = home
        self.process = None
        self.writer = None
        self.reader_task = None
        self.server = None
        self.socket_dir = None
        self.pending = {}
        self.sequence = 0
        self.send_lock = asyncio.Lock()

    @property
    def alive(self):
        return self.process is not None and self.process.returncode is None

    async def open(self):
        if self.alive:
            return
        await self.close()
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.socket_dir = tempfile.TemporaryDirectory(prefix="mz-core-")
        socket_path = str(Path(self.socket_dir.name) / "ipc.sock")
        connected = asyncio.get_running_loop().create_future()

        async def accept(reader, writer):
            if connected.done():
                writer.close()
                return
            self.writer = writer
            connected.set_result(reader)

        try:
            self.server = await asyncio.start_unix_server(accept, socket_path, limit=4 * 1024 * 1024)
            self.process = await asyncio.create_subprocess_exec(
                str(self.executable), socket_path, cwd=self.home,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            reader = await asyncio.wait_for(connected, 10)
            self.reader_task = asyncio.create_task(self._read(reader))
            initialized = await self.request("initClash", json.dumps({
                "home-dir": str(self.home), "version": 2026071801,
            }))
            if initialized is not True:
                raise CoreError("内核初始化失败。")
        except BaseException:
            await self.close()
            raise

    async def _read(self, reader):
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                response = json.loads(line)
                future = self.pending.get(response.get("id"))
                if future and not future.done():
                    if response.get("code") == 0:
                        future.set_result(response.get("data"))
                    else:
                        future.set_exception(CoreError("内核操作失败。"))
                # Unsolicited log/request events can contain private URLs.
                # Do not log, store or forward them to the panel.
        except (ValueError, OSError):
            pass
        finally:
            for future in tuple(self.pending.values()):
                if not future.done():
                    future.set_exception(CoreError("内核连接已中断。"))

    async def request(self, method, data=None, timeout=12):
        if not self.writer or self.writer.is_closing():
            raise CoreError("内核未连接。")
        self.sequence += 1
        ident = str(self.sequence)
        future = asyncio.get_running_loop().create_future()
        self.pending[ident] = future
        try:
            async with self.send_lock:
                self.writer.write((json.dumps({"id": ident, "method": method, "data": data}) + "\n").encode())
                await self.writer.drain()
            return await asyncio.wait_for(future, timeout)
        except (asyncio.TimeoutError, ConnectionError, OSError):
            raise CoreError("内核没有及时响应。") from None
        finally:
            self.pending.pop(ident, None)

    async def close(self):
        if self.writer and not self.writer.is_closing() and self.alive:
            try:
                await self.request("shutdown", timeout=3)
            except Exception:
                pass
        if self.server:
            self.server.close()
        if self.writer:
            self.writer.close()
            try:
                await asyncio.wait_for(self.writer.wait_closed(), 2)
            except (OSError, asyncio.TimeoutError):
                self.writer.transport.abort()
            self.writer = None
        if self.reader_task:
            self.reader_task.cancel()
            try:
                await self.reader_task
            except asyncio.CancelledError:
                pass
            self.reader_task = None
        if self.server:
            await self.server.wait_closed()
            self.server = None
        if self.process:
            if self.process.returncode is None:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), 4)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
            self.process = None
        if self.socket_dir:
            self.socket_dir.cleanup()
            self.socket_dir = None
