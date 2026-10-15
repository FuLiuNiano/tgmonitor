#!/usr/bin/env bash
set -euo pipefail
cd /opt/tg-guardian
if [[ "$(id -u)" != 0 ]]; then
  echo '请使用root执行：bash install_napcat.sh'
  exit 1
fi
if [[ ! -f dashboard_server.py ]]; then
  echo '请先执行 bash update.sh 安装本更新包的TG助手。'
  exit 1
fi
source /etc/os-release
if [[ "$ID" != debian || "$VERSION_ID" != 12 ]]; then
  echo '该安装脚本适用于当前Debian服务器的Debian 12。'
  exit 1
fi
FREE_KB=$(df -Pk /opt | awk 'NR==2 {print $4}')
if (( FREE_KB < 2000000 )); then
  echo '可用磁盘不足2GB，请先释放空间再安装。'
  exit 1
fi
if ! id momonapcat >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /opt/napcat-user --shell /usr/sbin/nologin momonapcat
fi
if [[ "$(getent passwd momonapcat | cut -d: -f6)" != /opt/napcat-user ]]; then
  echo '已有momonapcat用户的目录不同，已停止安装。'
  exit 1
fi
install -d -m 0700 -o momonapcat -g momonapcat /opt/napcat-user/downloads
# Install only the libraries required by the Linux QQ client and headless display.
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl jq unzip zip xvfb xauth procps libnss3 libgbm1 libgssapi-krb5-2 libglib2.0-0 libatk1.0-0 libatspi2.0-0 libgtk-3-0 libasound2
NAPCAT_DIR=/opt/napcat-user/Napcat/opt/QQ/resources/app/app_launcher/napcat/config
if [[ ! -f /opt/napcat-user/Napcat/opt/QQ/resources/app/app_launcher/napcat/napcat.mjs ]]; then
  # Resolve then pin this official installer revision before downloading it.
  INSTALLER_REV=$(curl -fsSL --connect-timeout 15 --max-time 60 https://api.github.com/repos/NapNeko/NapCat-Installer/commits/main | jq -er '.sha')
  [[ "$INSTALLER_REV" =~ ^[0-9a-f]{40}$ ]]
  curl -fL --proto '=https' --connect-timeout 20 --max-time 120 -o /opt/napcat-user/downloads/install.sh "https://raw.githubusercontent.com/NapNeko/NapCat-Installer/$INSTALLER_REV/script/install.sh"
  bash -n /opt/napcat-user/downloads/install.sh
  chown momonapcat:momonapcat /opt/napcat-user/downloads/install.sh
  cd /opt/napcat-user/downloads
  runuser -u momonapcat -- env TERM=xterm bash ./install.sh --docker n --cli n --skip-deps --github-proxy 0 --proxy 0
  cd /opt/tg-guardian
fi
systemctl stop momo-napcat.service 2>/dev/null || true
venv/bin/python napcat_setup.py --napcat-config "$NAPCAT_DIR"
chown -R momonapcat:momonapcat /opt/napcat-user
chown tgguardian:tgguardian .env config.json data/napcat-api-token
install -m 0644 systemd/momo-napcat.service /etc/systemd/system/momo-napcat.service
systemctl daemon-reload
systemctl enable --now momo-napcat
systemctl restart tg-guardian-dashboard
if systemctl is-active --quiet tg-guardian; then
  systemctl restart tg-guardian
fi
echo 'NapCat已启动，等待小号扫码登录。'
echo '本地电脑执行：ssh -L 6099:127.0.0.1:6099 -L 8080:127.0.0.1:8080 root@YOUR_SERVER_IP'
echo '浏览器打开：http://127.0.0.1:6099/webui'
echo '面板登录令牌的读取命令见 /opt/tg-guardian/NAPCAT_GUIDE.md。请直接在服务器终端读取。'
