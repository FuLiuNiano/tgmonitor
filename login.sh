#!/usr/bin/env bash
set -euo pipefail
cd /opt/tg-guardian
set -a
. /opt/tg-guardian/.env
set +a
exec sudo -u tgguardian --preserve-env=TG_API_ID,TG_API_HASH,TG_PHONE,TG_PROXY,LOG_LEVEL,QQ_BOT_TOKEN,SMTP_USERNAME,SMTP_AUTH_CODE /opt/tg-guardian/venv/bin/python /opt/tg-guardian/tg_guardian.py --config /opt/tg-guardian/config.json
