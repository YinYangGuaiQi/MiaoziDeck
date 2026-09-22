"""Embedded by the packager in a self-contained desktop launcher."""
import base64
import binascii
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

INSTALLER_SHA256 = 'SHELL_SHA256'
START = b'# __MIAOZI_SHELL_BASE64__'
END = b'# __MIAOZI_SHELL_END__'
MAX_INSTALLER_SIZE = 192 * 1024 * 1024


def source_path(location):
    # %k is provided by the desktop environment, as a filename or a file URI.
    if location.startswith('file:'):
        parsed = urlsplit(location)
        if parsed.netloc not in ('', 'localhost') or parsed.query or parsed.fragment:
            raise ValueError('请先将安装文件下载到本机，再双击运行。')
        return Path(unquote(parsed.path))
    if not location or '://' in location:
        raise ValueError('无法定位安装文件，请从文件管理器中双击运行。')
    return Path(location)


def extract_shell(source, target):
    digest = hashlib.sha256()
    size = 0
    started = ended = False
    with source.open('rb') as stream, target.open('xb') as output:
        for line in stream:
            line = line.rstrip(b'\r\n')
            if not started:
                if line == START:
                    started = True
                continue
            if line == END:
                ended = True
                break
            if not line.startswith(b'# '):
                raise ValueError('安装文件格式不完整，请重新下载。')
            chunk = base64.b64decode(line[2:], validate=True)
            size += len(chunk)
            if size > MAX_INSTALLER_SIZE:
                raise ValueError('安装文件大小异常，已停止安装。')
            digest.update(chunk)
            output.write(chunk)
        if not started or not ended or digest.hexdigest() != INSTALLER_SHA256:
            raise ValueError('安装文件校验失败，请重新下载。')


def install(location):
    source = source_path(location)
    with tempfile.TemporaryDirectory(prefix='miaozi-desktop-install-') as folder:
        shell = Path(folder) / 'install.sh'
        extract_shell(source, shell)
        return subprocess.run(['bash', str(shell)], check=False).returncode


def main():
    print('喵子 Deck 安装程序\n正在校验并准备安装资源，请稍候。', flush=True)
    try:
        if len(sys.argv) != 2:
            raise ValueError('请从文件管理器中双击完整安装文件。')
        result = install(sys.argv[1])
        if result:
            print('\n安装未完成，请查看上方提示。', flush=True)
    except (OSError, ValueError, binascii.Error) as error:
        print('\n安装未完成：' + str(error), flush=True)
        result = 1
    except KeyboardInterrupt:
        print('\n安装已取消。', flush=True)
        result = 130
    try:
        input('\n按回车关闭安装窗口。')
    except (EOFError, KeyboardInterrupt):
        pass
    return result


if __name__ == '__main__':
    raise SystemExit(main())
