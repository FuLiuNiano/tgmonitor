import json
import tempfile
import unittest
from pathlib import Path

from sync_sources import sync


class SourceDeploymentTests(unittest.TestCase):
    def test_sync_preserves_runtime_secrets_sessions_and_database(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, target = root / 'source', root / 'runtime'
            (source / 'frontend/dist').mkdir(parents=True)
            (target / 'data').mkdir(parents=True)
            (source / 'publish_manifest.json').write_text(json.dumps(['README.md', 'publish_manifest.json']), encoding='utf-8')
            (source / 'README.md').write_text('Reviewed source', encoding='utf-8')
            (source / '.env').write_text('do-not-deploy-source-settings', encoding='utf-8')
            (source / 'frontend/dist/index.html').write_text('<html>built</html>', encoding='utf-8')
            preserved = {
                '.env': b'keep-runtime-settings',
                'config.json': b'{"channels": []}',
                'data/tg_guardian.session': b'keep-session',
                'data/state.sqlite3': b'keep-database',
            }
            for name, content in preserved.items():
                (target / name).write_bytes(content)
            self.assertEqual(sync(source, target), 3)
            self.assertEqual((target / 'README.md').read_text(), 'Reviewed source')
            self.assertEqual((target / 'frontend/dist/index.html').read_text(), '<html>built</html>')
            for name, content in preserved.items():
                self.assertEqual((target / name).read_bytes(), content)

    def test_missing_frontend_or_invalid_manifest_never_changes_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, target = root / 'source', root / 'runtime'
            source.mkdir()
            target.mkdir()
            (source / 'publish_manifest.json').write_text('["README.md"]', encoding='utf-8')
            (source / 'README.md').write_text('new', encoding='utf-8')
            (target / 'README.md').write_text('old', encoding='utf-8')
            with self.assertRaises(ValueError):
                sync(source, target)
            self.assertEqual((target / 'README.md').read_text(), 'old')
            (source / 'frontend/dist').mkdir(parents=True)
            (source / 'frontend/dist/index.html').write_text('build', encoding='utf-8')
            (source / 'publish_manifest.json').write_text('["../runtime/README.md"]', encoding='utf-8')
            with self.assertRaises(ValueError):
                sync(source, target)
            self.assertEqual((target / 'README.md').read_text(), 'old')


if __name__ == '__main__':
    unittest.main()
