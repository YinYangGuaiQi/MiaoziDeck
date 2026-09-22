#!/usr/bin/env bash
set -euo pipefail
REPO='YinYangGuaiQi/MiaoziDeck'
VERSION='v0.1.0-alpha.9'
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo|--version)
      [[ $# -ge 2 ]] || { printf '缺少参数。\n' >&2; exit 1; }
      if [[ "$1" == --repo ]]; then REPO="$2"; else VERSION="$2"; fi
      shift 2 ;;
    *) printf '用法：bash install.sh --repo 用户名/仓库名 [--version v0.1.0-alpha.9]\n'; exit 1 ;;
  esac
done
[[ "$REPO" =~ ^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { printf '请指定实际 GitHub 仓库。\n' >&2; exit 1; }
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ ]] || exit 1
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 && "$(id -un)" == deck ]] || { printf '请在 Steam Deck 上以 deck 用户运行。\n' >&2; exit 1; }
for command in curl python3; do command -v "$command" >/dev/null || { printf '缺少系统命令：%s\n' "$command"; exit 1; }; done
TEMP_DIR="$(mktemp -d -t miaozi-download-XXXXXXXX)"
trap 'if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then rm -rf -- "$TEMP_DIR"; fi' EXIT
ASSET="MiaoziDeck-${VERSION#v}.sh"
BASE="https://github.com/$REPO/releases/download/$VERSION"
printf '正在下载完整安装文件，无需另装原版喵子客户端。\n'
if ! curl -fL --show-error --proto '=https' --proto-redir '=https' --retry 2 --connect-timeout 20 --max-time 1200 "$BASE/$ASSET" -o "$TEMP_DIR/$ASSET"; then
  printf '下载失败，请检查 GitHub 网络和 Release 文件地址；私有仓库请登录 GitHub 下载完整 .desktop 文件，双击安装。\n' >&2
  exit 1
fi
curl -fL --show-error --proto '=https' --proto-redir '=https' --retry 2 --max-time 60 "$BASE/$ASSET.sha256" -o "$TEMP_DIR/$ASSET.sha256"
python3 - "$TEMP_DIR" "$ASSET" <<'PY'
import hashlib,re,sys
from pathlib import Path
root=Path(sys.argv[1]);name=sys.argv[2]
expected=(root/(name+'.sha256')).read_text().strip()
if not re.fullmatch(r'[0-9a-f]{64}  '+re.escape(name),expected):raise SystemExit('安装文件校验信息不匹配。')
if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected[:64]:raise SystemExit('安装文件校验失败。')
PY
bash "$TEMP_DIR/$ASSET"
