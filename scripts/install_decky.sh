#!/usr/bin/env bash
set -euo pipefail
SOURCE="$1"
HOME_BREW=/home/deck/homebrew
if [[ -L "$HOME_BREW" || -L "$HOME_BREW/services" || -L "$HOME_BREW/plugins" ]]; then
  printf 'Decky 路径含符号链接，停止自动安装以保护现有文件。\n' >&2
  exit 1
fi
if [[ "$(systemctl show plugin_loader.service -p LoadState --value 2>/dev/null)" != 'not-found' && -f "$HOME_BREW/services/PluginLoader" ]]; then
  exit 0
fi
printf '未发现完整的 Decky，将从安装包自动安装 Decky。\n'
python3 - "$SOURCE" <<'PY'
import hashlib,json,sys
from pathlib import Path
source=Path(sys.argv[1])
meta=json.loads((source/'SOURCE.json').read_text())
if hashlib.sha256((source/'PluginLoader').read_bytes()).hexdigest()!=meta['sha256']:
    raise SystemExit('Decky 文件校验失败。')
unit=(source/'plugin_loader.service.in').read_text()
if '${HOMEBREW_FOLDER}' not in unit:raise SystemExit('Decky 服务模板不匹配。')
(source/'plugin_loader.service').write_text(unit.replace('${HOMEBREW_FOLDER}','/home/deck/homebrew'))
(source/'loader.version').write_text(meta['version']+'\n')
PY
sudo install -d -o deck -g deck -m 755 "$HOME_BREW" "$HOME_BREW/plugins" "$HOME_BREW/services"
if [[ -e "$HOME_BREW/services/PluginLoader" || -e /etc/systemd/system/plugin_loader.service ]]; then
  BACKUP="$HOME_BREW/backups/decky-before-miaozi-$(date +%Y%m%d-%H%M%S)-$$"
  sudo install -d -m 700 "$BACKUP"
  if [[ -f "$HOME_BREW/services/PluginLoader" ]]; then sudo cp -a "$HOME_BREW/services/PluginLoader" "$BACKUP/"; fi
  if [[ -f /etc/systemd/system/plugin_loader.service ]]; then sudo cp -a /etc/systemd/system/plugin_loader.service "$BACKUP/"; fi
fi
sudo install -o root -g root -m 755 "$SOURCE/PluginLoader" "$HOME_BREW/services/PluginLoader"
sudo install -o root -g root -m 644 "$SOURCE/plugin_loader.service" /etc/systemd/system/plugin_loader.service
sudo install -o root -g root -m 644 "$SOURCE/loader.version" "$HOME_BREW/services/.loader.version"
python3 - "$SOURCE" <<'PY'
import json,sys
from pathlib import Path
source=Path(sys.argv[1])
steam=Path('/home/deck/.steam/steam')
if not steam.is_dir():raise SystemExit('未找到 Steam 用户目录。')
(steam/'.cef-enable-remote-debugging').touch()
PY
sudo systemctl daemon-reload
sudo systemctl enable plugin_loader.service
