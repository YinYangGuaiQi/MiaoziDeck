#!/usr/bin/env bash
set -euo pipefail
printf '\n喵子 Deck — Yacd 仪表盘与后台加速\n\n'
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCE="$HERE/MiaoziDeck"
if [[ ! -f "$SOURCE/plugin.json" || ! -f "$SOURCE/dist/index.js" || ! -f "$SOURCE/bin/FlClashCore" ]]; then
  printf '文件不完整，请完整解压 ZIP，再进入解压后的文件夹运行。\n' >&2
  exit 1
fi
if [[ "$(uname -m)" != x86_64 ]]; then
  printf '此包仅支持 Steam Deck 使用的 x86_64 Linux。\n' >&2
  exit 1
fi
if [[ "$(id -un)" != deck ]]; then
  printf '请以 deck 用户运行本脚本，不要在脚本前加 sudo。\n' >&2
  exit 1
fi
python3 - "$SOURCE" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1])
for name in ('dashboard/index.html','certs/cacert.pem','py_modules/Cryptodome/__init__.py','acceleration_service.py','miaozi-deck.service','vendor.json','bootstrap_profile.py','official/FlClash','official/lib/libapp.so','official/vendor/SOURCES.json','decky/PluginLoader','install_decky.sh'):
    if not (root/name).is_file(): raise SystemExit('安装包资源缺失：'+name)
expected=json.loads((root/'vendor.json').read_text())['sha256']
if hashlib.sha256((root/'bin/FlClashCore').read_bytes()).hexdigest()!=expected:
    raise SystemExit('原版内核校验失败，未安装。')
import os,subprocess
for relative in ('bin/FlClashCore','official/FlClash','official/FlClashCore','decky/PluginLoader'):
    (root/relative).chmod(0o755)
env=dict(os.environ,LD_LIBRARY_PATH=str(root/'official/vendor')+':'+str(root/'official/lib'))
result=subprocess.run(['ldd',str(root/'official/FlClash')],env=env,capture_output=True,text=True)
missing=[line.strip().split(' => ')[0] for line in result.stdout.splitlines() if 'not found' in line]
if result.returncode or missing:
    raise SystemExit('当前系统缺少基础运行库：'+', '.join(missing or ['无法检查运行库']))
PY
TARGET=/home/deck/homebrew/plugins/MiaoziDeck
if [[ -L "$TARGET" || -L /home/deck/homebrew/plugins ]]; then
  printf '插件目录是符号链接，已停止自动安装。\n' >&2
  exit 1
fi
printf '需要管理员密码来安装插件并重启 Decky。输入密码时不会显示字符。\n'
sudo -v
bash "$SOURCE/install_decky.sh" "$SOURCE/decky"
BACKUP=''
STAGING="$(sudo mktemp -d /home/deck/homebrew/.miaozi-stage-XXXXXXXX)"
trap 'if [[ -n "$STAGING" && -d "$STAGING" ]]; then sudo rm -rf -- "$STAGING"; fi' EXIT
sudo cp -a -- "$SOURCE/." "$STAGING/"
sudo chown -R deck:deck -- "$STAGING"
sudo find "$STAGING" -type d -exec chmod 755 '{}' +
sudo find "$STAGING" -type f -exec chmod 644 '{}' +
sudo chmod 755 -- "$STAGING/bin/FlClashCore"
sudo chmod 755 -- "$STAGING/official/FlClash" "$STAGING/official/FlClashCore"
if [[ -e "$TARGET" ]]; then
  sudo mkdir -p -- /home/deck/homebrew/backups
  BACKUP="/home/deck/homebrew/backups/MiaoziDeck-$(date +%Y%m%d-%H%M%S)-$$"
  sudo mv -- "$TARGET" "$BACKUP"
fi
if ! sudo mv -- "$STAGING" "$TARGET"; then
  if [[ -n "$BACKUP" ]]; then sudo mv -- "$BACKUP" "$TARGET"; fi
  printf '安装失败，已尝试恢复原插件。\n' >&2
  exit 1
fi
STAGING=''
SERVICE_ROOT=/var/lib/miaozi-deck
if [[ -L "$SERVICE_ROOT" || -L "$SERVICE_ROOT/app" || -L "$SERVICE_ROOT/state" ]]; then
  printf '后台目录是符号链接，已停止安装。\n' >&2
  exit 1
fi
sudo install -d -o root -g root -m 755 "$SERVICE_ROOT"
sudo install -d -o deck -g deck -m 700 "$SERVICE_ROOT/state"
if [[ -d "$SERVICE_ROOT/app" ]]; then
  sudo systemctl stop miaozi-deck.service || true
  sudo mv "$SERVICE_ROOT/app" "$SERVICE_ROOT/app-backup-$(date +%Y%m%d-%H%M%S)-$$"
fi
sudo cp -a "$SOURCE" "$SERVICE_ROOT/app"
sudo chown -R root:root "$SERVICE_ROOT/app"
sudo find "$SERVICE_ROOT/app" -type d -exec chmod 755 '{}' +
sudo find "$SERVICE_ROOT/app" -type f -exec chmod 644 '{}' +
sudo chmod 755 "$SERVICE_ROOT/app/bin/FlClashCore"
sudo chmod 755 "$SERVICE_ROOT/app/official/FlClash" "$SERVICE_ROOT/app/official/FlClashCore"
if [[ -f /etc/systemd/system/miaozi-deck.service ]]; then
  sudo cp -a /etc/systemd/system/miaozi-deck.service "$SERVICE_ROOT/service-backup-$(date +%Y%m%d-%H%M%S)-$$"
fi
sudo install -o root -g root -m 644 "$SOURCE/miaozi-deck.service" /etc/systemd/system/miaozi-deck.service
if [[ ! -f "$SERVICE_ROOT/state/settings.json" ]]; then
  sudo -u deck /usr/bin/python3 - <<'PY'
import os,json
path='/var/lib/miaozi-deck/state/settings.json'
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as stream: json.dump({'enabled':False,'node':''},stream)
PY
fi
sudo systemctl daemon-reload
sudo systemctl enable --now miaozi-deck.service
if ! sudo systemctl restart plugin_loader.service; then
  printf '文件已安装，但 Decky 服务重启失败。请重启 Steam Deck。\n' >&2
  exit 1
fi
printf '\n安装完成。回到游戏模式 → … → Decky → Miaozi Deck。\n'
printf '后台加速服务已安装并启动。打开 Yacd 可切换节点、批量测速。\n'
printf '首次使用：在插件设置登录喵子账号，再开启加速。组件已内置，无需另装原版客户端。\n'
printf '应急关闭：sudo systemctl stop miaozi-deck.service\n'
if [[ -n "$BACKUP" ]]; then printf '旧版本已备份到：%s\n' "$BACKUP"; fi
