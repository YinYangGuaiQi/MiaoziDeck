#!/usr/bin/env bash
set -euo pipefail
REPO='YinYangGuaiQi/MiaoziDeck'
VERSION='latest'
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo|--version)
      [[ $# -ge 2 ]] || { printf '缺少参数。\n' >&2; exit 1; }
      if [[ "$1" == --repo ]]; then REPO="$2"; else VERSION="$2"; fi
      shift 2 ;;
    *) printf '用法：bash install.sh [--repo 用户名/仓库名] [--version latest 或版本标签]\n'; exit 1 ;;
  esac
done
[[ "$REPO" =~ ^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { printf '请指定实际 GitHub 仓库。\n' >&2; exit 1; }
[[ "$VERSION" == latest || "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ ]] || { printf '版本参数无效。\n' >&2; exit 1; }
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 && "$(id -un)" == deck ]] || { printf '请在 Steam Deck 上以 deck 用户运行。\n' >&2; exit 1; }
for command in curl python3; do command -v "$command" >/dev/null || { printf '缺少系统命令：%s\n' "$command"; exit 1; }; done
TEMP_DIR="$(mktemp -d -t miaozi-download-XXXXXXXX)"
trap 'if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then rm -rf -- "$TEMP_DIR"; fi' EXIT
if [[ "$VERSION" == latest ]]; then
  printf '正在获取最新发布版。\n'
  if ! RELEASE_URL="$(curl -fLsS --head --proto '=https' --proto-redir '=https' --retry 2 --connect-timeout 20 --max-time 60 --output /dev/null --write-out '%{url_effective}' "https://github.com/$REPO/releases/latest")"; then
    printf '无法获取最新发布版，请检查网络或从 Release 页面下载完整 .desktop 文件。\n' >&2
    exit 1
  fi
  [[ "$RELEASE_URL" == "https://github.com/$REPO/releases/tag/"* ]] || { printf '最新发布版地址无效。\n' >&2; exit 1; }
  VERSION="${RELEASE_URL##*/}"
  [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ ]] || { printf '最新版本标签格式不受支持。\n' >&2; exit 1; }
fi
ASSET="MiaoziDeck-${VERSION#v}.sh"
BASE="https://github.com/$REPO/releases/download/$VERSION"
printf '正在下载 %s 的完整安装文件，无需另装原版喵子客户端。\n' "$VERSION"
if ! curl -fL --show-error --proto '=https' --proto-redir '=https' --retry 2 --connect-timeout 20 --max-time 1200 "$BASE/$ASSET" -o "$TEMP_DIR/$ASSET"; then
  printf '下载失败，请检查 GitHub 网络，或从 Release 页面下载完整 .desktop 文件双击安装。\n' >&2
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
