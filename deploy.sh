#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/tg-guardian"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(id -u)" != "0" ]]; then
  echo "请用 root 执行：bash deploy.sh"
  exit 1
fi

if [[ "$SCRIPT_DIR" != "$APP_DIR" ]]; then
  echo "请通过deploy_from_git.sh同步代码到 $APP_DIR 后执行。"
  echo "当前目录：$SCRIPT_DIR"
  exit 1
fi

if systemctl is-active --quiet tg-guardian || systemctl is-active --quiet tg-guardian-dashboard; then
  echo '运行服务尚未停止，请从独立源码目录使用deploy_from_git.sh更新。'
  exit 1
fi

if ! id -u tgguardian >/dev/null 2>&1; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin tgguardian
fi

install -d -m 0750 -o tgguardian -g tgguardian "$APP_DIR/data"
/usr/bin/python3 -m venv --clear "$APP_DIR/venv"
"$APP_DIR/venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f "$APP_DIR/.env" ]]; then
  install -m 0640 -o tgguardian -g tgguardian "$APP_DIR/.env.example" "$APP_DIR/.env"
fi
if [[ ! -f "$APP_DIR/config.json" ]]; then
  install -m 0640 -o tgguardian -g tgguardian "$APP_DIR/config.example.json" "$APP_DIR/config.json"
fi

if [[ -f "$APP_DIR/frontend/dist/index.html" ]]; then
  echo '使用更新包内已构建的前端。'
elif command -v npm >/dev/null 2>&1; then
  npm ci --prefix "$APP_DIR/frontend" --no-audit --no-fund
  npm run build --prefix "$APP_DIR/frontend"
else
  echo "未找到npm，也没有已构建前端，部署失败。"
  exit 1
fi

chown -R tgguardian:tgguardian "$APP_DIR"
chmod 600 "$APP_DIR/.env" "$APP_DIR/config.json"
install -m 0644 "$APP_DIR/systemd/tg-guardian.service" /etc/systemd/system/tg-guardian.service
install -m 0644 "$APP_DIR/systemd/tg-guardian-dashboard.service" /etc/systemd/system/tg-guardian-dashboard.service
systemctl daemon-reload

echo
echo "部署准备完成。请先编辑："
echo "  $APP_DIR/.env"
echo "  $APP_DIR/config.json"
echo
echo "然后启动："
echo "  systemctl enable --now tg-guardian"
echo "  systemctl enable --now tg-guardian-dashboard"
echo
echo "首次 Telegram 登录："
echo "  bash /opt/tg-guardian/login.sh"
