import json
import tempfile
import unittest
from pathlib import Path

from napcat_setup import configure


class NapcatConfigTests(unittest.TestCase):
    def test_tokens_local_bindings_existing_account_and_tg_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            app = base / 'app'
            config_dir = base / 'napcat'
            app.mkdir()
            config_dir.mkdir()
            (app / '.env').write_text('TG_API_ID=123\nTG_API_HASH=private-hash\nQQ_BOT_TOKEN=old\n')
            (app / 'config.json').write_text(json.dumps({'channels': [{'chat': '123', 'keywords': ['通知']}], 'qq': {'provider': 'official', 'user_id': '12345'}}))
            (config_dir / 'webui.json').write_text('{"host":"0.0.0.0","token":"napcat"}')
            (config_dir / 'onebot11_123.json').write_text('{"network":{"httpServers":[{"host":"0.0.0.0"}]}}')
            configure(config_dir, app)
            token = (app / 'data/napcat-api-token').read_text()
            self.assertGreater(len(token), 32)
            self.assertIn('TG_API_HASH=private-hash', (app / '.env').read_text())
            self.assertEqual((app / '.env').read_text().count('QQ_BOT_TOKEN='), 1)
            self.assertIn('QQ_BOT_TOKEN=' + token, (app / '.env').read_text())
            webui = json.loads((config_dir / 'webui.json').read_text())
            self.assertEqual(webui['host'], '127.0.0.1')
            self.assertNotEqual(webui['token'], token)
            for path in (config_dir / 'onebot11.json', config_dir / 'onebot11_123.json'):
                server = json.loads(path.read_text())['network']['httpServers'][0]
                self.assertEqual(server['host'], '127.0.0.1')
                self.assertEqual(server['token'], token)
                self.assertEqual(server['port'], 5700)
            saved = json.loads((app / 'config.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['channels'][0]['keywords'], ['通知'])
            self.assertEqual(saved['qq']['user_id'], '12345')
            self.assertFalse(saved['qq']['enabled'])
            configure(config_dir, app)
            self.assertEqual((app / 'data/napcat-api-token').read_text(), token)


if __name__ == '__main__':
    unittest.main()
