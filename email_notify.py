"""Low-resource SMTP notifications; credentials are read only from environment."""
from __future__ import annotations

import asyncio
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr


def validate_email_config(config: dict) -> str:
    # Deliberately do not accept credentials in JSON, API responses or outbox rows.
    if any(key in config for key in ('password', 'auth_code', 'smtp_password', 'token')):
        raise ValueError('邮箱授权码只能填写服务器.env，不能保存到面板配置')
    recipient = str(config.get('recipient', '')).strip()
    if ('\r' in recipient or '\n' in recipient or len(recipient) > 254
            or parseaddr(recipient)[1] != recipient or recipient.count('@') != 1
            or not all(recipient.split('@')) or any(c.isspace() for c in recipient)):
        raise ValueError('请填写一个有效的收件邮箱地址')
    return recipient


async def send_email(config: dict, message: str) -> str:
    recipient = validate_email_config(config)
    sender = os.getenv('SMTP_USERNAME', '').strip()
    password = os.getenv('SMTP_AUTH_CODE', '').strip()
    if not sender or not password:
        raise ValueError('请在服务器.env填写SMTP_USERNAME和SMTP_AUTH_CODE，然后重启服务')
    validate_email_config({'recipient': sender})
    # QQ Mail implicit TLS; no plaintext SMTP or certificate-verification bypass.
    mail = EmailMessage()
    mail['From'] = sender
    mail['To'] = recipient
    mail['Subject'] = 'TG频道提醒：' + message.splitlines()[0][:100] if message else 'TG频道提醒'
    mail['Date'] = formatdate(localtime=False)
    mail['Message-ID'] = make_msgid()
    mail.set_content(message)

    def deliver():
        try:
            with smtplib.SMTP_SSL('smtp.qq.com', 465, timeout=20,
                                  context=ssl.create_default_context()) as client:
                client.login(sender, password)
                refused = client.send_message(mail)
                if refused:
                    raise RuntimeError('邮件服务器拒绝收件地址')
        except smtplib.SMTPAuthenticationError:
            raise RuntimeError('QQ邮箱认证失败，请检查SMTP服务和授权码') from None
        except Exception:
            # Do not expose SMTP replies, addresses, credentials or message bodies.
            raise RuntimeError('邮件发送失败，请检查SMTP网络、收件地址或稍后重试') from None
        return str(mail['Message-ID'])

    return await asyncio.to_thread(deliver)
