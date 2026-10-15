#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR=/opt/tg-guardian
if [[ "$(id -u)" != 0 ]]; then
  echo '请在服务器root终端执行部署脚本。'
  exit 1
fi
if [[ "$SOURCE_DIR" == "$APP_DIR" ]]; then
  echo '请将Git仓库克隆在独立目录，例如/opt/tgmonitor-src。'
  exit 1
fi
cd "$SOURCE_DIR"
command -v npm >/dev/null
command -v curl >/dev/null
/usr/bin/python3 check_privacy.py
/usr/bin/python3 -m unittest discover -s tests -v
# Build before stopping services. A clean checkout never contains frontend/dist.
npm ci --prefix frontend --no-audit --no-fund
npm run build --prefix frontend
TG_WAS_ACTIVE=false
if systemctl is-active --quiet tg-guardian; then
  TG_WAS_ACTIVE=true
fi
systemctl stop tg-guardian tg-guardian-dashboard 2>/dev/null || true
/usr/bin/python3 sync_sources.py --target "$APP_DIR"
cd "$APP_DIR"
bash deploy.sh
sudo -u tgguardian "$APP_DIR/venv/bin/python" tg_guardian.py --config config.json --dry-run
systemctl enable --now tg-guardian-dashboard
if [[ "$TG_WAS_ACTIVE" == true ]]; then
  systemctl start tg-guardian
fi
for attempt in 1 2 3 4 5; do
  if curl -fsS --max-time 3 http://127.0.0.1:8080/api/status >/dev/null; then
    echo '前端配置API检查通过。'
    break
  fi
  if [[ "$attempt" == 5 ]]; then
    echo '前端API检查失败，请查看tg-guardian-dashboard服务日志。'
    exit 1
  fi
  sleep 1
done
echo '源码部署完成。后续更新：在源码目录git pull --ff-only，再执行bash deploy_from_git.sh。'
if [[ "$TG_WAS_ACTIVE" == false ]]; then
  echo 'Telegram首次登录：bash /opt/tg-guardian/login.sh；成功后启用tg-guardian服务。'
fi
echo '安装QQ通知组件：bash /opt/tg-guardian/install_napcat.sh。'
