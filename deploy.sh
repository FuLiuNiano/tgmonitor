#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/tg-guardian"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(id -u)" != "0" ]]; then
  echo "请用 root 执行：bash deploy.sh"
  exit 1
fi

if [[ "$SCRIPT_DIR" != "$APP_DIR" ]]; then
  echo "请将压缩包解压到 $APP_DIR 后再执行。"
  echo "当前目录：$SCRIPT_DIR"
  exit 1
fi

if ! id -u tgguardian >/dev/null 2>&1; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin tgguardian
fi

install -d -m 0750 -o tgguardian -g tgguardian "$APP_DIR/data"
/usr/bin/python3 -m venv "$APP_DIR/venv"
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
  npm install --prefix "$APP_DIR/frontend" --no-audit --no-fund
  npm run build --prefix "$APP_DIR/frontend"
else
  echo "警告：未找到 npm，前端尚未构建。"
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
