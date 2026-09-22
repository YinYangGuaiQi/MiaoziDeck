#!/usr/bin/env bash
set -euo pipefail
printf '\n喵子 Deck — Yacd 仪表盘与后台加速\n\n'
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCE="$HERE/MiaoziDeck"
if [[ ! -f "$SOURCE/plugin.json" || ! -f "$SOURCE/dist/index.js" || ! -f "$SOURCE/bin/FlClashCore" ]]; then
  printf '安装资源不完整，请重新下载 Release 中的完整安装文件。\n' >&2
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
SERVICE_ROOT=/var/lib/miaozi-deck
# Only this root-owned code is executed with network capabilities. The official
# GUI, Decky and other large resources remain in the plugin under /home/deck.
SERVICE_FILES=(acceleration_service.py cache_nodes.py core_session.py vendor.json
  bin/FlClashCore py_modules dashboard)
for path in /home /home/deck /home/deck/homebrew /home/deck/homebrew/plugins \
  /home/deck/homebrew/backups "$TARGET" /var /var/lib "$SERVICE_ROOT" \
  "$SERVICE_ROOT/app" "$SERVICE_ROOT/state" /etc/systemd/system/miaozi-deck.service; do
  if [[ -L "$path" ]]; then
    printf '安装路径含符号链接，已停止安装：%s\n' "$path" >&2
    exit 1
  fi
done
printf '需要管理员密码来安装插件并重启 Decky。输入密码时不会显示字符。\n'
sudo -v
STAMP="$(date +%Y%m%d-%H%M%S)-$$"
SERVICE_ARCHIVE="/home/deck/homebrew/backups/miaozi-deck-service-$STAMP"
# Count allocated blocks and reserve extra room before touching either app.
FULL_KIB="$(du -sk -- "$SOURCE" | awk '{print $1}')"
SERVICE_KIB=0
for relative in "${SERVICE_FILES[@]}"; do
  if [[ ! -e "$SOURCE/$relative" || -n "$(find "$SOURCE/$relative" -type l -print -quit)" ]]; then
    printf '后台资源缺失或含符号链接：%s\n' "$relative" >&2
    exit 1
  fi
  size="$(du -sk -- "$SOURCE/$relative" | awk '{print $1}')"
  SERVICE_KIB=$((SERVICE_KIB + size))
done
shopt -s nullglob
LEGACY_BACKUPS=("$SERVICE_ROOT"/app-backup-*)
LEGACY_KIB=0
for path in "${LEGACY_BACKUPS[@]}"; do
  if [[ -L "$path" || ! -d "$path" ]]; then
    printf '旧后台备份路径异常，已停止安装。\n' >&2
    exit 1
  fi
  size="$(sudo du -sk -- "$path" | awk '{print $1}')"
  LEGACY_KIB=$((LEGACY_KIB + size))
done
HOME_FREE_KIB="$(df -Pk /home/deck | awk 'NR==2 {print $4}')"
CURRENT_SERVICE_KIB=0
if [[ -d "$SERVICE_ROOT/app" ]]; then
  CURRENT_SERVICE_KIB="$(sudo du -sk -- "$SERVICE_ROOT/app" | awk '{print $1}')"
fi
if (( HOME_FREE_KIB < FULL_KIB + LEGACY_KIB + CURRENT_SERVICE_KIB + 65536 )); then
  printf '用户分区空间不足，未更改现有安装。请至少释放 %s MiB 后重试。\n' \
    "$(((FULL_KIB + LEGACY_KIB + CURRENT_SERVICE_KIB + 65536 + 1023) / 1024))" >&2
  exit 1
fi
sudo install -d -o deck -g deck -m 755 /home/deck/homebrew /home/deck/homebrew/backups
sudo install -d -o root -g root -m 700 "$SERVICE_ARCHIVE"
for path in "${LEGACY_BACKUPS[@]}"; do
  # mv copies across filesystems and only removes a successfully copied source.
  # These are archives only: never execute privileged code from this directory.
  sudo mv -- "$path" "$SERVICE_ARCHIVE/"
done
sudo install -d -o root -g root -m 755 "$SERVICE_ROOT"
VAR_FREE_KIB="$(df -Pk "$SERVICE_ROOT" | awk 'NR==2 {print $4}')"
if (( VAR_FREE_KIB < SERVICE_KIB + 16384 )); then
  printf '系统数据分区空间不足，未替换现有程序。后台更新需要至少 %s MiB 可用空间。\n' \
    "$(((SERVICE_KIB + 16384 + 1023) / 1024))" >&2
  printf '旧后台备份已保留在：%s\n' "$SERVICE_ARCHIVE" >&2
  exit 1
fi
BACKUP=''
STAGING=''
SERVICE_STAGING=''
SERVICE_BACKUP="$SERVICE_ROOT/app-backup-$STAMP"
UNIT_BACKUP=''
PLUGIN_CHANGED=0
SERVICE_CHANGED=0
SERVICE_STOPPED=0
UNIT_CHANGED=0
COMMITTED=0
SERVICE_WAS_ACTIVE=0
if systemctl is-active --quiet miaozi-deck.service; then SERVICE_WAS_ACTIVE=1; fi
cleanup() {
  result=$?
  trap - EXIT
  set +e
  if (( result != 0 && COMMITTED == 0 )); then
    if (( SERVICE_CHANGED )); then
      sudo systemctl stop miaozi-deck.service
      sudo rm -rf -- "$SERVICE_ROOT/app"
      if [[ -d "$SERVICE_BACKUP" ]]; then sudo mv -- "$SERVICE_BACKUP" "$SERVICE_ROOT/app"; fi
    fi
    if (( UNIT_CHANGED )); then
      if [[ -n "$UNIT_BACKUP" ]]; then
        sudo cp -a -- "$UNIT_BACKUP" /etc/systemd/system/miaozi-deck.service
      else
        sudo rm -f -- /etc/systemd/system/miaozi-deck.service
      fi
      sudo systemctl daemon-reload
    fi
    if (( PLUGIN_CHANGED )); then
      sudo rm -rf -- "$TARGET"
      if [[ -n "$BACKUP" ]]; then sudo mv -- "$BACKUP" "$TARGET"; fi
      sudo systemctl restart plugin_loader.service
    fi
    if (( SERVICE_STOPPED && SERVICE_WAS_ACTIVE )); then sudo systemctl start miaozi-deck.service; fi
    printf '安装未完成，已尝试恢复原插件及后台程序；账号和订阅数据未删除。\n' >&2
  fi
  if [[ "$STAGING" == /home/deck/homebrew/.miaozi-stage-* ]]; then sudo rm -rf -- "$STAGING"; fi
  if [[ "$SERVICE_STAGING" == "$SERVICE_ROOT"/.app-stage-* ]]; then sudo rm -rf -- "$SERVICE_STAGING"; fi
  if [[ "$UNIT_BACKUP" == "$SERVICE_ROOT"/.unit-backup-* ]]; then sudo rm -f -- "$UNIT_BACKUP"; fi
  exit "$result"
}
trap cleanup EXIT
SERVICE_STAGING="$(sudo mktemp -d "$SERVICE_ROOT/.app-stage-XXXXXXXX")"
for relative in "${SERVICE_FILES[@]}"; do
  sudo mkdir -p -- "$SERVICE_STAGING/$(dirname -- "$relative")"
  sudo cp -a -- "$SOURCE/$relative" "$SERVICE_STAGING/$relative"
done
sudo chown -R root:root -- "$SERVICE_STAGING"
sudo find "$SERVICE_STAGING" -type d -exec chmod 755 '{}' +
sudo find "$SERVICE_STAGING" -type f -exec chmod 644 '{}' +
sudo chmod 755 -- "$SERVICE_STAGING/bin/FlClashCore"
if [[ -f /etc/systemd/system/miaozi-deck.service ]]; then
  UNIT_BACKUP="$(sudo mktemp "$SERVICE_ROOT/.unit-backup-XXXXXXXX")"
  sudo cp -a -- /etc/systemd/system/miaozi-deck.service "$UNIT_BACKUP"
fi
bash "$SOURCE/install_decky.sh" "$SOURCE/decky"
STAGING="$(sudo mktemp -d /home/deck/homebrew/.miaozi-stage-XXXXXXXX)"
sudo cp -a -- "$SOURCE/." "$STAGING/"
sudo chown -R deck:deck -- "$STAGING"
sudo find "$STAGING" -type d -exec chmod 755 '{}' +
sudo find "$STAGING" -type f -exec chmod 644 '{}' +
sudo chmod 755 -- "$STAGING/bin/FlClashCore"
sudo chmod 755 -- "$STAGING/official/FlClash" "$STAGING/official/FlClashCore"
if [[ -e "$TARGET" ]]; then
  sudo mkdir -p -- /home/deck/homebrew/backups
  BACKUP="/home/deck/homebrew/backups/MiaoziDeck-$STAMP"
  sudo mv -- "$TARGET" "$BACKUP"
fi
PLUGIN_CHANGED=1
sudo mv -- "$STAGING" "$TARGET"
STAGING=''
sudo install -d -o deck -g deck -m 700 "$SERVICE_ROOT/state"
sudo systemctl stop miaozi-deck.service || true
SERVICE_STOPPED=1
if [[ -d "$SERVICE_ROOT/app" ]]; then
  sudo mv -- "$SERVICE_ROOT/app" "$SERVICE_BACKUP"
fi
SERVICE_CHANGED=1
sudo mv -- "$SERVICE_STAGING" "$SERVICE_ROOT/app"
SERVICE_STAGING=''
UNIT_CHANGED=1
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
  printf 'Decky 服务重启失败，将恢复原安装。\n' >&2
  exit 1
fi
COMMITTED=1
if [[ -d "$SERVICE_BACKUP" ]]; then sudo mv -- "$SERVICE_BACKUP" "$SERVICE_ARCHIVE/"; fi
if [[ -n "$UNIT_BACKUP" ]]; then sudo mv -- "$UNIT_BACKUP" "$SERVICE_ARCHIVE/miaozi-deck.service"; UNIT_BACKUP=''; fi
printf '\n安装完成。回到游戏模式 → … → Decky → Miaozi Deck。\n'
printf '后台加速服务已安装并启动。打开 Yacd 可切换节点、批量测速。\n'
printf '首次使用：在插件设置登录喵子账号，再开启加速。组件已内置，无需另装原版客户端。\n'
printf '应急关闭：sudo systemctl stop miaozi-deck.service\n'
if [[ -n "$BACKUP" ]]; then printf '旧版本已备份到：%s\n' "$BACKUP"; fi
