from __future__ import annotations

from datetime import datetime, time
from typing import Iterable


def match_keywords(text: str, keywords: Iterable[str]) -> list[str]:
    """Return configured keywords that occur in text, case-insensitively."""
    folded = (text or "").casefold()
    found: list[str] = []
    for keyword in keywords:
        value = str(keyword).strip()
        if value and value.casefold() in folded:
            found.append(value)
    return found


def parse_hhmm(value: str) -> time:
    hour, minute = (int(part) for part in value.strip().split(":", 1))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"invalid time: {value!r}")
    return time(hour=hour, minute=minute)


def schedule_is_due(now: datetime, slot: str, grace_minutes: int = 30) -> bool:
    """Whether now is inside the execution window after a HH:MM slot."""
    scheduled = datetime.combine(now.date(), parse_hhmm(slot), tzinfo=now.tzinfo)
    elapsed_seconds = (now - scheduled).total_seconds()
    return 0 <= elapsed_seconds <= max(0, grace_minutes) * 60


def message_link(entity: object, message_id: int) -> str | None:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"

    entity_id = getattr(entity, "id", None)
    if entity_id is None:
        return None
    # Telegram's private supergroup/channel links use the -100 prefix.
    raw_id = str(entity_id)
    internal_id = raw_id[4:] if raw_id.startswith("-100") else raw_id.lstrip("-")
    return f"https://t.me/c/{internal_id}/{message_id}"
