import asyncio
import json
import tempfile
import threading
import types
import unittest
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dashboard_server import DashboardHandler
from qq_notify import send_qq_private_message
from tg_guardian import Guardian, validate_config


class IntegrationTests(unittest.TestCase):
    def test_discovery_marked_ids_selected_rules_and_message_delivery(self):
        async def run():
            entity = types.SimpleNamespace(id=123, username='news', broadcast=True)
            other = types.SimpleNamespace(id=456, username=None, broadcast=True)
            async def dialogs():
                for item in (entity, other):
                    yield types.SimpleNamespace(is_channel=True, entity=item, name='频道')
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'config.json'
                config = {'channels': [{'chat': '@news', 'keywords': ['上新'], 'enabled': True}], 'alert_chats': ['me'], 'qq': {'enabled': True, 'user_id': '12345'}, 'alert': {'beep': False}}
                path.write_text(json.dumps(config), encoding='utf-8')
                guardian = Guardian(config, path)
                guardian.client = types.SimpleNamespace(iter_dialogs=dialogs, send_message=AsyncMock())
                fake = types.SimpleNamespace(utils=types.SimpleNamespace(get_peer_id=lambda obj: -1000000000000 - obj.id))
                with patch.dict('sys.modules', {'telethon': fake}):
                    await guardian.refresh_channel_catalog()
                self.assertEqual(len(guardian.channel_catalog), 2)
                self.assertEqual(len(guardian.channel_by_id), 1)
                event = types.SimpleNamespace(chat_id=-1000000000123, id=7, raw_text='今日上新 [CQ:at,qq=all]', out=False)
                with patch('tg_guardian.send_qq_private_message', new_callable=AsyncMock) as qq:
                    await guardian.handle_message(event, 'new')
                    await guardian.handle_message(event, 'new')
                    self.assertEqual(qq.await_count, 1)
                    self.assertIn('https://t.me/news/7', qq.call_args.args[1])
                    event.out = True
                    event.id = 8
                    await guardian.handle_message(event, 'new')
                    self.assertEqual(qq.await_count, 1)
                config['channels'][0]['enabled'] = False
                path.write_text(json.dumps(config), encoding='utf-8')
                guardian.config_mtime = -1
                with patch.dict('sys.modules', {'telethon': fake}):
                    await guardian.reload_config_if_changed()
                self.assertFalse(guardian.channel_by_id[event.chat_id]['enabled'])
                guardian.store.close()
        asyncio.run(run())

    def test_onebot_http_auth_and_safe_text(self):
        received = {}
        class Bot(BaseHTTPRequestHandler):
            def do_POST(self):
                received['path'] = self.path
                received['auth'] = self.headers.get('Authorization')
                received['payload'] = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok","retcode":0,"data":{"message_id":42}}')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Bot)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict('os.environ', {'QQ_BOT_TOKEN': 'test-token'}):
                result = asyncio.run(send_qq_private_message({'api_base': f'http://127.0.0.1:{server.server_port}', 'user_id': '12345'}, '[CQ:at,qq=all]'))
            self.assertEqual(result, '42')
            self.assertEqual(received['path'], '/send_private_msg')
            self.assertEqual(received['auth'], 'Bearer test-token')
            self.assertEqual(received['payload']['message'][0]['type'], 'text')
        finally:
            server.shutdown()
            server.server_close()

    def test_dashboard_save_validation_and_origin(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            config = path / 'config.json'
            config.write_text('{"channels":[],"session":"data/original"}', encoding='utf-8')
            DashboardHandler.config_path = config
            DashboardHandler.data_dir = path
            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(DashboardHandler, directory=folder))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            def put(payload, origin=base):
                return urlopen(Request(base + '/api/config', data=json.dumps(payload).encode(), method='PUT', headers={'Content-Type': 'application/json', 'Origin': origin}))
            try:
                with put({'channels': [], 'session': '/root/nope'}) as response:
                    self.assertTrue(json.load(response)['ok'])
                self.assertEqual(json.loads(config.read_text())['session'], 'data/original')
                with self.assertRaises(HTTPError) as error:
                    put({'channels': []}, 'http://evil.example')
                self.assertEqual(error.exception.code, 403)
                with self.assertRaises(HTTPError) as error:
                    put({'channels': [{'chat': '1', 'checkin': {'enabled': True, 'mode': 'send_text', 'command': '/sign', 'times': ['99:99']}}]})
                self.assertEqual(error.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()

    def test_empty_channels_allowed(self):
        validate_config({'channels': []})

    def test_official_push_cannot_be_enabled(self):
        with self.assertRaises(ValueError):
            validate_config({'channels': [], 'qq': {'provider': 'official', 'enabled': True}})

    def test_failed_qq_delivery_is_persisted_and_retried(self):
        async def run():
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'config.json'
                config = {'channels': [], 'qq': {'enabled': True, 'provider': 'onebot', 'user_id': '12345'}, 'alert_chats': ['me'], 'alert': {'beep': False}}
                path.write_text(json.dumps(config), encoding='utf-8')
                guardian = Guardian(config, path)
                guardian.client = types.SimpleNamespace(send_message=AsyncMock())
                with patch('tg_guardian.send_qq_private_message', new_callable=AsyncMock, side_effect=RuntimeError('offline')):
                    with self.assertLogs('tg_guardian', level='ERROR'):
                        await guardian.notify('测试', '消息', qq=True)
                self.assertEqual(guardian.store.db.execute('SELECT COUNT(*) FROM qq_outbox').fetchone()[0], 1)
                with patch('tg_guardian.send_qq_private_message', new_callable=AsyncMock) as qq:
                    await guardian.retry_qq_outbox()
                    self.assertEqual(qq.await_count, 1)
                self.assertEqual(guardian.store.db.execute('SELECT COUNT(*) FROM qq_outbox').fetchone()[0], 0)
                guardian.store.close()
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
