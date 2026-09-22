#!/usr/bin/env bash
set -euo pipefail
command -v python3 >/dev/null || { printf '需要 SteamOS 自带的 Python 3。\n' >&2; exit 1; }
python3 - "$0" <<'PY'
import hashlib,io,stat,subprocess,sys,tempfile,zipfile
from pathlib import Path,PurePosixPath
payload=Path(sys.argv[1]).read_bytes().split(b'\n__MIAOZI_PAYLOAD__\n',1)[1]
if hashlib.sha256(payload).hexdigest()!='PAYLOAD_SHA256':
    raise SystemExit('安装文件损坏，未执行安装。请重新下载。')
with tempfile.TemporaryDirectory(prefix='miaozi-full-install-') as folder:
    destination=Path(folder)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names=set(); total=0
        for entry in archive.infolist():
            path=PurePosixPath(entry.filename)
            if (not path.parts or path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                or (path.parts[0]!='MiaoziDeck' and entry.filename!='install.sh') or entry.filename in names):
                raise SystemExit('安装文件包含异常路径。')
            if stat.S_IFMT(entry.external_attr>>16) not in (0,stat.S_IFREG,stat.S_IFDIR):
                raise SystemExit('安装文件包含不支持的特殊文件。')
            total+=entry.file_size
            if total>768*1024*1024 or len(names)>20000:raise SystemExit('安装文件大小超出预期。')
            names.add(entry.filename)
        required={'install.sh','MiaoziDeck/official/FlClash','MiaoziDeck/decky/PluginLoader','MiaoziDeck/bootstrap_profile.py'}
        if not required.issubset(names):raise SystemExit('安装文件组件不完整。')
        archive.extractall(destination)
    subprocess.run(['bash',str(destination/'install.sh')],check=True)
PY
exit 0
