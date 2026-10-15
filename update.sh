#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/opt/tg-guardian
cd "$APP_DIR"
if [[ "$(id -u)" != 0 ]]; then
  echo '请使用root执行更新脚本'
  exit 1
fi
if [[ ! -f .env || ! -f config.json ]]; then
  echo '未找到现有配置，请先执行deploy.sh'
  exit 1
fi
if [[ ! -f frontend/dist/index.html ]]; then
  echo '更新包缺少前端构建文件'
  exit 1
fi
systemctl stop tg-guardian tg-guardian-dashboard
if [[ ! -x venv/bin/python ]]; then
  /usr/bin/python3 -m venv venv
fi
venv/bin/pip install --no-cache-dir -r requirements.txt
venv/bin/python -m unittest discover -s tests -v
venv/bin/python tg_guardian.py --config config.json --dry-run
chown -R tgguardian:tgguardian "$APP_DIR"
chmod 600 .env config.json
install -m 0644 systemd/tg-guardian.service /etc/systemd/system/tg-guardian.service
install -m 0644 systemd/tg-guardian-dashboard.service /etc/systemd/system/tg-guardian-dashboard.service
systemctl daemon-reload
systemctl enable --now tg-guardian-dashboard
SESSION_PATH=$(venv/bin/python -c 'import json,pathlib; c=json.load(open("config.json")); p=pathlib.Path(c.get("session","data/tg_guardian")); print(str(p)+".session")')
if [[ -f "$SESSION_PATH" ]]; then
  systemctl enable --now tg-guardian
else
  echo '请先执行 bash login.sh 完成首次Telegram登录，再启动tg-guardian。'
fi
echo '更新完成。配置、Telegram登录会话和签到记录已保留。'
