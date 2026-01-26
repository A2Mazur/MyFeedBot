import asyncio
import os
import logging
from datetime import timezone
from pathlib import Path
import json
import time
import httpx
from collector.telethon_client import build_client

logging.basicConfig(level=logging.INFO)

API_URL = os.getenv("API_URL", "http://api:8000")
OWNER_TG_USER_ID = int(os.getenv("OWNER_TG_USER_ID"))
INTERVAL = int(os.getenv("COLLECT_INTERVAL_SEC", "60"))
MEDIA_TTL_DAYS = int(os.getenv("MEDIA_TTL_DAYS", "3"))
MEDIA_CLEAN_INTERVAL_SEC = int(os.getenv("MEDIA_CLEAN_INTERVAL_SEC", "3600"))

async def fetch_channels(api: httpx.AsyncClient):
    r = await api.get(f"{API_URL}/channels/list", params={"tg_user_id": OWNER_TG_USER_ID})
    r.raise_for_status()
    return r.json().get("channels", [])

async def send_post(api: httpx.AsyncClient, channel: str, msg_id: int, text: str, published_at):
    payload = {
        "tg_user_id": OWNER_TG_USER_ID,
        "channel_username": channel,
        "tg_message_id": msg_id,
        "text": text,
        "published_at": published_at,
    }
    r = await api.post(f"{API_URL}/posts/add", json=payload)
    r.raise_for_status()

async def send_post_with_media(
    api: httpx.AsyncClient,
    channel: str,
    msg_id: int,
    text: str,
    published_at,
    media_type: str | None,
    media_paths: list[str] | None,
    media_group_id: int | None,
):
    payload = {
        "tg_user_id": OWNER_TG_USER_ID,
        "channel_username": channel,
        "tg_message_id": msg_id,
        "text": text,
        "published_at": published_at,
        "media_type": media_type,
        "media_paths": media_paths,
        "media_group_id": media_group_id,
    }
    r = await api.post(f"{API_URL}/posts/add", json=payload)
    r.raise_for_status()

def ensure_media_dir(channel: str) -> Path:
    base = Path("/app/media") / channel.lstrip("@")
    base.mkdir(parents=True, exist_ok=True)
    return base

async def download_media(tg, message, channel: str, suffix: str) -> str | None:
    base = ensure_media_dir(channel)
    path = base / f"{message.id}_{suffix}"
    try:
        saved = await tg.download_media(message, file=str(path))
        return str(saved) if saved else None
    except Exception:
        logging.exception("Failed to download media")
        return None

async def get_cursor(api: httpx.AsyncClient, channel: str) -> int | None:
    r = await api.get(f"{API_URL}/channels/cursor", params={
        "tg_user_id": OWNER_TG_USER_ID,
        "username": channel
    })
    r.raise_for_status()
    v = r.json().get("last_tg_message_id")
    return int(v) if v is not None else None

async def set_cursor(api: httpx.AsyncClient, channel: str, last_id: int) -> None:
    r = await api.post(f"{API_URL}/channels/cursor", json={
        "tg_user_id": OWNER_TG_USER_ID,
        "username": channel,
        "last_tg_message_id": int(last_id)
    })
    r.raise_for_status()

async def set_channel_title(api: httpx.AsyncClient, channel: str, title: str) -> None:
    r = await api.post(f"{API_URL}/channels/title", json={
        "tg_user_id": OWNER_TG_USER_ID,
        "username": channel,
        "title": title,
    })
    r.raise_for_status()


async def main():
    tg = build_client()
    await tg.start()
    last_media_cleanup = 0.0
    async with httpx.AsyncClient(timeout=20) as api:
        while True:
            channels = await fetch_channels(api)

            for ch in channels:
                try:
                    entity = await tg.get_entity(ch)
                    title = getattr(entity, "title", None)
                    if title:
                        await set_channel_title(api, ch, title)
                    cursor = await get_cursor(api, ch)
                    msgs = await tg.get_messages(entity, limit=10)
                    if not msgs:
                        continue
                    newest = max((m.id for m in msgs if m.id), default=None)
                    if newest is None:
                        continue
                    if cursor is None:
                        await set_cursor(api, ch, newest)
                        logging.info(f"Baseline set for {ch}: last_tg_message_id={newest} (no send)")
                        continue

                    new_msgs = [m for m in msgs if m.id and m.id > cursor]
                    if not new_msgs:
                        logging.info(f"No new posts in {ch} (cursor={cursor}, last={newest})")
                        continue

                    grouped = {}
                    singles = []
                    for m in new_msgs:
                        if m.grouped_id:
                            grouped.setdefault(m.grouped_id, []).append(m)
                        else:
                            singles.append(m)

                    for group_id, items in grouped.items():
                        items.sort(key=lambda x: x.id)
                        media_paths = []
                        media_type = "media_group"
                        caption_text = ""
                        for idx, item in enumerate(items, start=1):
                            if item.message:
                                caption_text = item.message.strip()
                            if getattr(item, "photo", None) or getattr(item, "video", None) or getattr(item, "document", None):
                                saved = await download_media(tg, item, ch, f"g{group_id}_{idx}")
                                if saved:
                                    media_paths.append(saved)
                        if not media_paths:
                            continue
                        published = items[-1].date
                        if published.tzinfo is None:
                            published = published.replace(tzinfo=timezone.utc)
                        await send_post_with_media(
                            api,
                            channel=ch,
                            msg_id=items[-1].id,
                            text=caption_text,
                            published_at=published.isoformat(),
                            media_type=media_type,
                            media_paths=media_paths,
                            media_group_id=group_id,
                        )

                    for m in singles:
                        text = (m.message or "").strip()
                        media_type = None
                        media_paths = None
                        if getattr(m, "photo", None):
                            media_type = "photo"
                            saved = await download_media(tg, m, ch, "photo")
                            media_paths = [saved] if saved else None
                        elif getattr(m, "video", None):
                            media_type = "video"
                            saved = await download_media(tg, m, ch, "video")
                            media_paths = [saved] if saved else None
                        elif getattr(m, "voice", None):
                            media_type = "voice"
                            saved = await download_media(tg, m, ch, "voice")
                            media_paths = [saved] if saved else None
                        elif getattr(m, "document", None):
                            media_type = "document"
                            saved = await download_media(tg, m, ch, "doc")
                            media_paths = [saved] if saved else None

                        published = m.date
                        if published.tzinfo is None:
                            published = published.replace(tzinfo=timezone.utc)
                        await send_post_with_media(
                            api,
                            channel=ch,
                            msg_id=m.id,
                            text=text,
                            published_at=published.isoformat(),
                            media_type=media_type,
                            media_paths=media_paths,
                            media_group_id=None,
                        )

                    await set_cursor(api, ch, max(m.id for m in new_msgs))
                    logging.info(f"New posts from {ch}: {len(new_msgs)}")
                except Exception as e:
                    logging.exception(f"Collector error for {ch}: {e}")

            now = time.time()
            if now - last_media_cleanup >= MEDIA_CLEAN_INTERVAL_SEC:
                media_root = Path("/app/media")
                if media_root.exists():
                    cutoff = now - MEDIA_TTL_DAYS * 24 * 3600
                    for path in media_root.rglob("*"):
                        if path.is_file():
                            try:
                                if path.stat().st_mtime < cutoff:
                                    path.unlink()
                            except Exception:
                                logging.exception("Failed to remove media file")
                    for path in sorted(media_root.rglob("*"), reverse=True):
                        if path.is_dir():
                            try:
                                if not any(path.iterdir()):
                                    path.rmdir()
                            except Exception:
                                pass
                last_media_cleanup = now
            await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
