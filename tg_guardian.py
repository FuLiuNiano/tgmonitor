from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from core import match_keywords, message_link, schedule_is_due
from qq_notify import send_qq_private_message


LOG = logging.getLogger("tg_guardian")


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise SystemExit(f"找不到配置文件：{path}\n请复制 config.example.json 为 config.json 后再运行。") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"配置文件 JSON 格式错误：{exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit("配置文件根节点必须是 JSON 对象。")
    return value


def validate_config(config: dict[str, Any]) -> None:
    if not isinstance(config, dict):
        raise ValueError('配置必须是对象')
    zone = str(config.get('timezone', 'Asia/Shanghai'))
    if zone != 'Asia/Shanghai':
        ZoneInfo(zone)
    for key in ('alert', 'qq'):
        if not isinstance(config.get(key, {}), dict):
            raise ValueError(f'{key}必须是对象')
    cooldown = int(config.get('alert', {}).get('cooldown_seconds', 300))
    if config.get('qq', {}).get('provider') == 'official' and config.get('qq', {}).get('enabled'):
        raise ValueError('QQ官方机器人已停止主动推送，无法开启即时私聊提醒')
    if cooldown < 0:
        raise ValueError('冷却时间不能小于零')
    channels = config.get("channels")
    if not isinstance(channels, list):
        raise ValueError("channels 必须是数组，可以为空。")
    for index, channel in enumerate(channels, start=1):
        if not isinstance(channel, dict) or not channel.get("chat"):
            raise ValueError(f"channels[{index}] 缺少 chat。")
        checkin = channel.get("checkin", {})
        if not isinstance(checkin, dict):
            raise ValueError('checkin必须是对象')
        if checkin.get('mode', 'send_text') not in {'send_text', 'button'}:
            raise ValueError('未知签到动作')
        if checkin.get("enabled") and checkin.get("mode", "button") == "button":
            if not checkin.get("button_texts"):
                raise ValueError(f"channels[{index}] 的 button 签到必须配置 button_texts。")
        if not isinstance(channel.get('keywords', []), list):
            raise ValueError('keywords 必须是数组')
        if checkin.get('enabled'):
            from core import parse_hhmm
            if not checkin.get('times'):
                raise ValueError('签到需要至少一个时间')
            for slot in checkin['times']:
                parse_hhmm(slot)
            if checkin.get('mode') == 'send_text' and not str(checkin.get('command', '')).strip():
                raise ValueError('发送消息签到需要填写消息内容')


def proxy_from_env() -> dict[str, Any] | None:
    """Read a Telethon proxy dict from TG_PROXY, without logging credentials."""
    raw = os.getenv("TG_PROXY", "").strip()
    if not raw:
        host = os.getenv("TG_PROXY_HOST", "").strip()
        port = os.getenv("TG_PROXY_PORT", "").strip()
        if not host and not port:
            return None
        raw = f"socks5://{host}:{port}"
    if "://" not in raw:
        raw = f"socks5://{raw}"
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"socks5", "socks4", "http"} or not parsed.hostname or not parsed.port:
        raise SystemExit("TG_PROXY 格式应为 socks5://127.0.0.1:7890（也支持 socks4/http）。")
    proxy: dict[str, Any] = {
        "proxy_type": scheme,
        "addr": parsed.hostname,
        "port": parsed.port,
        "rdns": True,
    }
    if parsed.username:
        proxy["username"] = unquote(parsed.username)
    if parsed.password:
        proxy["password"] = unquote(parsed.password)
    return proxy


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                fingerprint TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkins (
                channel_key TEXT NOT NULL,
                run_date TEXT NOT NULL,
                slot TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                attempted_at TEXT NOT NULL,
                PRIMARY KEY (channel_key, run_date, slot)
            );
            CREATE TABLE IF NOT EXISTS qq_outbox (
                fingerprint TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                config TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL NOT NULL DEFAULT 0
            );
            """
        )
        self.db.commit()

    def alert_seen(self, fingerprint: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM alerts WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        return row is not None

    def remember_alert(self, fingerprint: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO alerts(fingerprint, created_at) VALUES (?, ?)",
            (fingerprint, datetime.now().isoformat(timespec="seconds")),
        )
        self.db.commit()

    def checkin(self, channel_key: str, run_date: str, slot: str) -> tuple[str, str] | None:
        row = self.db.execute(
            "SELECT status, attempted_at FROM checkins WHERE channel_key = ? AND run_date = ? AND slot = ?",
            (channel_key, run_date, slot),
        ).fetchone()
        return (str(row[0]), str(row[1])) if row else None

    def save_checkin(
        self,
        channel_key: str,
        run_date: str,
        slot: str,
        status: str,
        detail: str = "",
    ) -> None:
        self.db.execute(
            """
            INSERT INTO checkins(channel_key, run_date, slot, status, detail, attempted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_key, run_date, slot) DO UPDATE SET
                status = excluded.status,
                detail = excluded.detail,
                attempted_at = excluded.attempted_at
            """,
            (
                channel_key,
                run_date,
                slot,
                status,
                detail[:500],
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def enqueue_qq(self, payload: str, config: dict[str, Any]) -> None:
        key = hashlib.sha256((payload + json.dumps(config, sort_keys=True)).encode()).hexdigest()
        self.db.execute('INSERT OR IGNORE INTO qq_outbox(fingerprint,payload,config) VALUES(?,?,?)', (key, payload, json.dumps(config)))
        self.db.commit()


class Guardian:
    def __init__(self, config: dict[str, Any], config_path: Path) -> None:
        self.config = config
        self.config_path = config_path
        try:
            self.tz = ZoneInfo(str(config.get("timezone", "Asia/Shanghai")))
        except Exception as exc:
            # Windows minimal Python installations may not ship IANA zone data.
            # Keep the default China deployment usable without weakening named zones.
            if str(config.get("timezone", "Asia/Shanghai")) == "Asia/Shanghai":
                self.tz = timezone(timedelta(hours=8), name="Asia/Shanghai")
            else:
                raise SystemExit(f"无法识别 timezone：{config.get('timezone')}") from exc

        state_db = Path(str(config.get("state_db", "data/state.sqlite3")))
        if not state_db.is_absolute():
            state_db = config_path.parent / state_db
        self.store = Store(state_db)
        self.data_dir = state_db.parent
        self.catalog_path = self.data_dir / "channel_catalog.json"
        self.status_path = self.data_dir / "status.json"
        self.channels: list[dict[str, Any]] = list(config["channels"])
        self.entities: dict[int, Any] = {}
        self.channel_by_id: dict[int, dict[str, Any]] = {}
        self.channel_catalog: list[dict[str, Any]] = []
        self.config_mtime = config_path.stat().st_mtime_ns if config_path.exists() else 0
        self.client: TelegramClient | None = None
        self.alert_chats = config.get("alert_chats", ["me"])
        self.last_alert_at: dict[str, float] = {}
        if not isinstance(self.alert_chats, list) or not self.alert_chats:
            self.alert_chats = ["me"]

    @staticmethod
    def entity_ref(entity: Any) -> str:
        from telethon import utils
        return str(utils.get_peer_id(entity))

    @staticmethod
    def resolve_ref(value: Any) -> Any:
        text = str(value).strip()
        return int(text) if text.lstrip("-").isdigit() else text

    def write_data_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp, path)

    def publish_status(self, status: str = "running") -> None:
        self.write_data_json(
            self.status_path,
            {
                "status": status,
                "last_heartbeat": datetime.now(self.tz).isoformat(timespec="seconds"),
                "configured_channels": len(self.channels),
                "watched_channels": sum(item.get('enabled', True) is not False for item in self.channel_by_id.values()),
                "discovered_channels": len(self.channel_catalog),
            },
        )

    async def refresh_channel_catalog(self) -> None:
        assert self.client is not None
        from telethon import utils
        catalog: list[dict[str, Any]] = []
        selected = {}
        async for dialog in self.client.iter_dialogs():
            if not (getattr(dialog, "is_channel", False) or getattr(dialog, 'is_group', False)):
                continue
            entity = dialog.entity
            entity_id = utils.get_peer_id(entity)
            self.entities[entity_id] = entity
            ref = self.entity_ref(entity)
            configured = next(
                (
                    item
                    for item in self.channels
                    if str(item.get("chat", "")) == ref
                    or str(item.get('chat', '')) in {str(entity_id), str(entity.id)}
                    or str(item.get("chat", "")).lstrip("@") == str(getattr(entity, "username", ""))
                ),
                None,
            )
            if configured is not None:
                configured.setdefault("name", dialog.name or ref)
                selected[entity_id] = configured
            checkin = (configured or {}).get("checkin", {})
            catalog.append(
                {
                    "chat": ref,
                    "id": entity_id,
                    "name": (configured or {}).get("name") or dialog.name or ref,
                    "username": getattr(entity, "username", None),
                    "type": "channel" if getattr(entity, "broadcast", False) else "supergroup",
                    "configured": configured is not None,
                    "enabled": bool((configured or {}).get("enabled", True)) if configured else False,
                    "keywords": list((configured or {}).get("keywords", [])),
                    "checkin": checkin,
                }
            )
        self.channel_by_id = selected
        self.channel_catalog = sorted(catalog, key=lambda item: str(item.get("name", "")).casefold())
        self.last_catalog_refresh = time.monotonic()
        self.write_data_json(self.catalog_path, self.channel_catalog)
        self.publish_status()

    async def reload_config_if_changed(self) -> None:
        try:
            mtime = self.config_path.stat().st_mtime_ns
        except FileNotFoundError:
            return
        if mtime == self.config_mtime:
            return
        with self.config_path.open(encoding='utf-8') as handle:
            new_config = json.load(handle)
        validate_config(new_config)
        self.config = new_config
        try:
            self.tz = ZoneInfo(str(new_config.get('timezone', 'Asia/Shanghai')))
        except Exception:
            self.tz = timezone(timedelta(hours=8))
        self.channels = list(new_config["channels"])
        self.alert_chats = new_config.get("alert_chats", ["me"])
        if not isinstance(self.alert_chats, list) or not self.alert_chats:
            self.alert_chats = ["me"]
        await self.refresh_channel_catalog()
        self.config_mtime = mtime
        LOG.info("配置已重新加载：%s 个已配置频道。", len(self.channels))

    async def start(self) -> None:
        from telethon import TelegramClient, events

        api_id = os.getenv("TG_API_ID", "").strip()
        api_hash = os.getenv("TG_API_HASH", "").strip()
        phone = os.getenv("TG_PHONE", "").strip() or None
        if not api_id.isdigit() or not api_hash:
            raise SystemExit("请先设置 TG_API_ID 和 TG_API_HASH 环境变量。")
        proxy = proxy_from_env()
        if proxy:
            LOG.info("已启用 Telegram 代理：%s://%s:%s", proxy["proxy_type"], proxy["addr"], proxy["port"])

        session = Path(str(self.config.get("session", "data/tg_guardian")))
        if not session.is_absolute():
            session = self.config_path.parent / session
        session.parent.mkdir(parents=True, exist_ok=True)

        self.client = TelegramClient(str(session), int(api_id), api_hash, proxy=proxy)
        await self.client.start(phone=phone)
        for session_file in (Path(f"{session}.session"), session):
            if session_file.exists():
                try:
                    os.chmod(session_file, 0o600)
                except OSError:
                    pass
        LOG.info("Telegram 登录成功，正在解析频道配置。")

        await self.refresh_channel_catalog()
        watched_entities = list(self.channel_by_id.values())

        @self.client.on(events.NewMessage)
        async def on_new_message(event: Any) -> None:
            await self.handle_message(event, "new")

        @self.client.on(events.MessageEdited)
        async def on_edited_message(event: Any) -> None:
            await self.handle_message(event, "edited")

        asyncio.create_task(self.checkin_loop())
        await self.notify("✅ TG 频道助手已启动", f"已发现 {len(self.channel_catalog)} 个频道，当前监听 {len(watched_entities)} 个。", force=True)
        LOG.info("服务已启动。")
        await self.client.run_until_disconnected()

    async def handle_message(self, event: Any, kind: str) -> None:
        if event.out:
            return
        channel = self.channel_by_id.get(int(event.chat_id))
        if not channel or channel.get("enabled", True) is False:
            return
        text = event.raw_text or ""
        keywords = match_keywords(text, channel.get("keywords", []))
        if not keywords:
            return

        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        fingerprint = f"{kind}:{event.chat_id}:{event.id}:{digest}"
        if self.store.alert_seen(fingerprint):
            return

        cooldown_seconds = max(0, int(self.config.get("alert", {}).get("cooldown_seconds", 0)))
        cooldown_key = f"{event.chat_id}:{','.join(keywords)}"
        now_monotonic = time.monotonic()
        last_alert = self.last_alert_at.get(cooldown_key, 0.0)
        if cooldown_seconds and now_monotonic - last_alert < cooldown_seconds:
            self.store.remember_alert(fingerprint)
            LOG.info("关键词提醒处于冷却期，已抑制重复提醒：%s", cooldown_key)
            return

        title = channel.get("name") or str(channel.get("chat"))
        excerpt = " ".join(text.strip().split())[:500]
        link = message_link(self.entities[int(event.chat_id)], int(event.id))
        body = (
            f"🚨 关键词命中：{title}\n"
            f"关键词：{'、'.join(keywords)}\n"
            f"内容：{excerpt or '[媒体消息]'}"
        )
        if link:
            body += f"\n链接：{link}"
        if not await self.notify(title, body, qq=True):
            return
        self.store.remember_alert(fingerprint)
        self.last_alert_at[cooldown_key] = now_monotonic
        LOG.info("关键词命中：%s / %s", title, ",".join(keywords))

    async def notify(self, title: str, body: str, force: bool = False, qq: bool = False) -> bool:
        assert self.client is not None
        alert_config = self.config.get("alert", {})
        if not force and not alert_config.get("enabled", True):
            return False
        payload = f"{title}\n\n{body}"
        for chat in self.alert_chats:
            try:
                await self.client.send_message(chat, payload, parse_mode=None)
            except Exception:
                LOG.exception("发送提醒失败：%s", chat)
        qq_config = self.config.get("qq", {})
        if qq and qq_config.get("enabled"):
            try:
                await send_qq_private_message(qq_config, payload)
            except Exception:
                LOG.exception("发送 QQ 提醒失败")
                self.store.enqueue_qq(payload, qq_config)
        if alert_config.get("beep", True):
            # 在 SSH/容器里无法弹窗时，日志和 Telegram 消息仍然有效。
            print("\a", end="", flush=True)
        return True

    async def checkin_loop(self) -> None:
        interval = max(10, int(self.config.get("checkin_poll_seconds", 20)))
        while True:
            try:
                await self.reload_config_if_changed()
                if time.monotonic() - getattr(self, 'last_catalog_refresh', 0) > 300:
                    await self.refresh_channel_catalog()
                self.publish_status()
                await self.retry_qq_outbox()
                now = datetime.now(self.tz)
                for channel in self.channels:
                    checkin = channel.get("checkin", {})
                    if not checkin.get("enabled"):
                        continue
                    for slot in checkin.get("times", []):
                        if schedule_is_due(now, str(slot), int(checkin.get("grace_minutes", 30))):
                            await self.maybe_checkin(channel, str(slot), now)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("签到轮询发生异常")
            await asyncio.sleep(interval)

    async def retry_qq_outbox(self) -> None:
        if not self.config.get('qq', {}).get('enabled'):
            return
        rows = self.store.db.execute('SELECT fingerprint,payload,config,attempts FROM qq_outbox WHERE next_attempt <= ? AND attempts < 5 LIMIT 5', (time.time(),)).fetchall()
        for key, payload, config, attempts in rows:
            try:
                await send_qq_private_message(json.loads(config), payload)
                self.store.db.execute('DELETE FROM qq_outbox WHERE fingerprint=?', (key,))
            except Exception:
                LOG.warning('QQ通知补发失败，重试次数 %s/5', attempts + 1)
                self.store.db.execute('UPDATE qq_outbox SET attempts=?,next_attempt=? WHERE fingerprint=?', (attempts + 1, time.time() + 60, key))
            self.store.db.commit()

    async def maybe_checkin(self, channel: dict[str, Any], slot: str, now: datetime) -> None:
        channel_key = str(channel['chat'])
        run_date = now.date().isoformat()
        previous = self.store.checkin(channel_key, run_date, slot)
        if previous and previous[0] == "success":
            return
        if previous:
            retry_minutes = int(channel.get("checkin", {}).get("retry_minutes", 10))
            try:
                attempted_at = datetime.fromisoformat(previous[1])
                age = (datetime.now() - attempted_at).total_seconds() / 60
                if age < retry_minutes:
                    return
            except ValueError:
                pass

        self.store.save_checkin(channel_key, run_date, slot, "running")
        checkin = channel.get("checkin", {})
        entity = next(
            (self.entities[key] for key, value in self.channel_by_id.items() if value is channel),
            None,
        )
        if entity is None:
            self.store.save_checkin(channel_key, run_date, slot, "failed", "频道实体未加载")
            return

        try:
            detail = await self.execute_checkin(entity, checkin)
            self.store.save_checkin(channel_key, run_date, slot, "success", detail)
            LOG.info("签到动作已执行：%s / %s（需以频道回复确认签到结果）", channel_key, slot)
            if checkin.get("notify_success", False):
                await self.notify("✅ 自动签到成功", f"频道：{channel_key}\n时间：{slot}\n{detail}")
        except Exception as exc:
            detail = str(exc)
            self.store.save_checkin(channel_key, run_date, slot, "failed", detail)
            LOG.exception("签到失败：%s / %s", channel_key, slot)
            await self.notify("❌ 自动签到失败", f"频道：{channel_key}\n时间：{slot}\n原因：{detail}", qq=True)

    async def execute_checkin(self, entity: Any, checkin: dict[str, Any]) -> str:
        assert self.client is not None
        mode = str(checkin.get("mode", "button"))
        if mode == "send_text":
            command = str(checkin.get("command", "")).strip()
            if not command:
                raise ValueError("send_text 模式缺少 command")
            sent = await self.client.send_message(entity, command, parse_mode=None)
            return f"已发送：{command}（消息 {sent.id}）"
        if mode != "button":
            raise ValueError(f"不支持的签到模式：{mode}")

        message_keywords = checkin.get("message_keywords", [])
        button_texts = [str(item).casefold() for item in checkin.get("button_texts", [])]
        limit = max(1, int(checkin.get("search_limit", 30)))
        async for message in self.client.iter_messages(entity, limit=limit):
            text = message.raw_text or ""
            if message_keywords and not match_keywords(text, message_keywords):
                continue
            buttons = message.buttons or []
            for row in buttons:
                for button in row:
                    label = str(getattr(button, "text", "") or "")
                    original = getattr(button, "button", None)
                    if getattr(button, "url", None) or getattr(original, "url", None):
                        continue
                    if any(target in label.casefold() for target in button_texts):
                        await button.click()
                        return f"已点击“{label}”（消息 {message.id}）"
        raise RuntimeError("在最近消息中没有找到符合条件的签到按钮")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram 频道关键词监控与自动签到")
    parser.add_argument("--config", default="config.json", help="JSON 配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只检查配置，不连接 Telegram")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    validate_config(config)
    if args.dry_run:
        print(f"配置检查通过：{len(config['channels'])} 个频道。")
        return
    guardian = Guardian(config, config_path)
    try:
        asyncio.run(guardian.start())
    except KeyboardInterrupt:
        LOG.info("服务已停止。")
    finally:
        guardian.store.close()


if __name__ == "__main__":
    main()
