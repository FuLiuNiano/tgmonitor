from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from email_notify import send_email


async def send_qq_private_message(config: dict[str, Any], message: str) -> str:
    """Deliver a notification (the legacy entry point also supports email)."""
    if config.get('provider') == 'email':
        return await send_email(config, message)
    if config.get('provider', 'onebot') != 'onebot':
        raise ValueError('QQ官方机器人不支持全天候主动私聊推送，请选择其他通知方式')
    api_base = str(config.get("api_base", "http://127.0.0.1:5700")).rstrip("/")
    parsed = urlparse(api_base)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('QQ机器人地址需要填写http或https地址，不含密码或查询参数')
    user_id = str(config.get("user_id", "")).strip()
    if not user_id.isdigit() or int(user_id) <= 0:
        raise ValueError("请填写正确的QQ号")

    payload: dict[str, Any] = {"user_id": int(user_id) if user_id.isdigit() else user_id, "message": [{"type": "text", "data": {"text": message}}]}
    token = os.getenv("QQ_BOT_TOKEN", "").strip()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def request() -> str:
        request_obj = Request(
            f"{api_base}/send_private_msg",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request_obj, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"QQ 机器人连接失败：{exc}") from exc
        if not isinstance(result, dict):
            raise RuntimeError('QQ机器人返回格式错误')
        if result.get('status') != 'ok' or result.get('retcode', 0) != 0:
            raise RuntimeError(f"QQ 机器人返回失败：{result.get('wording') or result.get('retcode')}")
        return str((result.get('data') or {}).get('message_id', 'ok'))

    return await asyncio.to_thread(request)
