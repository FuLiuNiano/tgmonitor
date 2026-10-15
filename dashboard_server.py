from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from tg_guardian import validate_config
from qq_notify import send_qq_private_message


def read_json(path: Path, fallback):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


class DashboardHandler(SimpleHTTPRequestHandler):
    config_path: Path
    data_dir: Path

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def _json(self, payload, status: int = 200):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _api(self, method: str) -> bool:
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return False
        host = self.headers.get('Host', '')
        if host not in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}:
            self._json({'error': '仅接受本地面板访问'}, 403)
            return True
        if method in {'PUT', 'POST'}:
            origin = self.headers.get('Origin')
            if origin and origin != f'http://{host}':
                self._json({'error': '拒绝跨站请求'}, 403)
                return True
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self._json({'error': '需要JSON请求'}, 415)
                return True

        if method == "GET" and path == "/api/status":
            self._json(read_json(self.data_dir / "status.json", {"status": "starting"}))
            return True
        if method == "GET" and path == "/api/channels":
            self._json({"channels": read_json(self.data_dir / "channel_catalog.json", []), "source": "telegram"})
            return True
        if method == "GET" and path == "/api/config":
            config = read_json(self.config_path, {})
            self._json(config)
            return True
        if method == "PUT" and path == "/api/config":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2_000_000:
                    raise ValueError("请求体大小不合法")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict) or not isinstance(payload.get("channels"), list):
                    raise ValueError("配置必须包含 channels 数组")
                validate_config(payload)
                previous = read_json(self.config_path, {})
                for key in ('session', 'state_db'):
                    payload[key] = previous.get(key, 'data/tg_guardian' if key == 'session' else 'data/state.sqlite3')
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.config_path.parent, delete=False) as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                    temp_name = handle.name
                os.replace(temp_name, self.config_path)
                os.chmod(self.config_path, 0o600)
                self._json({"ok": True, "message": "配置已保存，后台会自动重新加载"})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return True
        if method == 'POST' and path == '/api/test-qq':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length < 20000:
                    raise ValueError('请求大小无效')
                qq = json.loads(self.rfile.read(length).decode('utf-8'))
                asyncio.run(send_qq_private_message(qq, 'MOMO TG频道助手：QQ机器人连接测试成功。'))
                self._json({'ok': True})
            except Exception as exc:
                self._json({'error': str(exc)}, 400)
            return True
        self._json({"error": "not found"}, 404)
        return True

    def do_GET(self):
        if not self._api("GET"):
            super().do_GET()

    def do_PUT(self):
        self._api("PUT")

    def do_POST(self):
        self._api('POST')

    def log_message(self, format, *args):
        return


def main():
    parser = argparse.ArgumentParser(description="TG Guardian dashboard and local config API")
    parser.add_argument("--directory", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    DashboardHandler.config_path = Path(args.config).resolve()
    DashboardHandler.data_dir = Path(args.data_dir).resolve()
    directory = str(Path(args.directory).resolve())
    server = ThreadingHTTPServer(("127.0.0.1", args.port), lambda *handler_args: DashboardHandler(*handler_args, directory=directory))
    print(f"Dashboard listening on http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
