import asyncio
import json
import smtplib
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from email_notify import send_email, validate_email_config
from qq_notify import send_qq_private_message
from tg_guardian import Guardian, validate_config


class EmailTests(unittest.TestCase):
    def test_163_email_uses_163_smtp_and_environment_credentials(self):
        settings = {'provider': 'email', 'mail_service': '163', 'recipient': 'receiver@example.invalid'}
        validate_config({'channels': [], 'qq': {**settings, 'enabled': True}})
        with patch.dict('os.environ', {'SMTP_USERNAME': 'sender@example.invalid', 'SMTP_AUTH_CODE': 'synthetic-test-only'}):
            with patch('email_notify.smtplib.SMTP_SSL') as smtp:
                client = smtp.return_value.__enter__.return_value
                client.send_message.return_value = {}
                asyncio.run(send_qq_private_message(settings, '163邮件提醒测试'))
                self.assertEqual(smtp.call_args.args, ('smtp.163.com', 465))
                self.assertTrue(smtp.call_args.kwargs['context'].check_hostname)
                client.login.assert_called_once_with('sender@example.invalid', 'synthetic-test-only')
                mail = client.send_message.call_args.args[0]
                self.assertEqual(mail['From'], 'sender@example.invalid')
                self.assertEqual(mail['To'], settings['recipient'])

    def test_unsupported_mail_service_is_rejected_before_connection(self):
        with patch('email_notify.smtplib.SMTP_SSL') as smtp:
            for enabled in (False, True):
                with self.assertRaises(ValueError):
                    validate_config({'channels': [], 'qq': {'provider': 'email', 'enabled': enabled, 'mail_service': 'custom'}})
            with self.assertRaises(ValueError):
                asyncio.run(send_email({'mail_service': 'custom', 'recipient': 'receiver@example.invalid'}, 'test'))
            smtp.assert_not_called()

    def test_encrypted_email_dispatch(self):
        settings = {'provider': 'email', 'recipient': 'receiver@example.invalid'}
        with patch.dict('os.environ', {'SMTP_USERNAME': 'sender@example.invalid', 'SMTP_AUTH_CODE': 'synthetic-test-only'}):
            with patch('email_notify.smtplib.SMTP_SSL') as smtp:
                client = smtp.return_value.__enter__.return_value
                client.send_message.return_value = {}
                result = asyncio.run(send_qq_private_message(settings, '关键词命中\n频道内容与链接'))
                self.assertTrue(result.startswith('<'))
                self.assertEqual(smtp.call_args.args, ('smtp.qq.com', 465))
                self.assertTrue(smtp.call_args.kwargs['context'].check_hostname)
                client.login.assert_called_once_with('sender@example.invalid', 'synthetic-test-only')
                mail = client.send_message.call_args.args[0]
                self.assertEqual(mail['To'], settings['recipient'])
                self.assertIn('频道内容与链接', mail.get_content())
                self.assertNotIn('synthetic-test-only', mail.as_string())

    def test_missing_credentials_never_connects(self):
        with patch.dict('os.environ', {}, clear=True), patch('email_notify.smtplib.SMTP_SSL') as smtp:
            with self.assertRaises(ValueError):
                asyncio.run(send_email({'recipient': 'receiver@example.invalid'}, 'test'))
            smtp.assert_not_called()

    def test_recipient_and_secret_validation(self):
        for recipient in ('', 'bad', 'a@', 'a@example.invalid\r\nBcc:other@example.invalid', 'a@example.invalid,b@example.invalid'):
            with self.assertRaises(ValueError):
                validate_email_config({'recipient': recipient})
        for enabled in (False, True):
            with self.assertRaises(ValueError):
                validate_config({'channels': [], 'qq': {'provider': 'email', 'enabled': enabled, 'password': 'synthetic-test-only'}})

    def test_error_response_does_not_expose_smtp_details(self):
        with patch.dict('os.environ', {'SMTP_USERNAME': 'sender@example.invalid', 'SMTP_AUTH_CODE': 'synthetic-test-only'}):
            with patch('email_notify.smtplib.SMTP_SSL', side_effect=smtplib.SMTPAuthenticationError(535, b'synthetic-test-only')):
                with self.assertRaises(RuntimeError) as error:
                    asyncio.run(send_email({'recipient': 'receiver@example.invalid'}, 'test'))
                self.assertNotIn('synthetic-test-only', str(error.exception))

    def test_email_failure_retries_and_changed_destination_is_not_used(self):
        async def run():
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'config.json'
                config = {'channels': [], 'qq': {'enabled': True, 'provider': 'email', 'recipient': 'receiver@example.invalid'}, 'alert_chats': [], 'alert': {'beep': False}}
                path.write_text(json.dumps(config), encoding='utf-8')
                guardian = Guardian(config, path)
                guardian.client = types.SimpleNamespace(send_message=AsyncMock())
                try:
                    with patch('tg_guardian.send_qq_private_message', new_callable=AsyncMock, side_effect=RuntimeError('offline')):
                        with self.assertLogs('tg_guardian', level='WARNING'):
                            await guardian.notify('关键词', '摘要', qq=True)
                    with patch('tg_guardian.send_qq_private_message', new_callable=AsyncMock) as deliver:
                        await guardian.retry_qq_outbox()
                        self.assertEqual(deliver.await_count, 1)
                    guardian.store.enqueue_qq('old message', config['qq'])
                    guardian.config['qq'] = {**config['qq'], 'recipient': 'changed@example.invalid'}
                    with patch('tg_guardian.send_qq_private_message', new_callable=AsyncMock) as deliver:
                        await guardian.retry_qq_outbox()
                        deliver.assert_not_awaited()
                    self.assertEqual(guardian.store.db.execute('SELECT COUNT(*) FROM qq_outbox').fetchone()[0], 0)
                finally:
                    guardian.store.close()
        asyncio.run(run())
