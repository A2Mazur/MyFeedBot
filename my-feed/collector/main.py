import asyncio
import os
import logging
from datetime import timezone
import httpx
from collector.telethon_client import build_client

logging.basicConfig(level=logging.INFO)

API_URL = os.getenv("API_URL", "http://api:8000")
OWNER_TG_USER_ID = int(os.getenv("OWNER_TG_USER_ID"))
INTERVAL = int(os.getenv("COLLECT_INTERVAL_SEC", "60"))

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


async def main():
    tg = build_client()
    await tg.start()
    async with httpx.AsyncClient(timeout=20) as api:
        while True:
            channels = await fetch_channels(api)

            for ch in channels:
                try:
                    entity = await tg.get_entity(ch)
                    cursor = await get_cursor(api, ch)
                    msgs = await tg.get_messages(entity, limit=1)
                    if not msgs:
                        continue

                    m = msgs[0]
                    if not m.id:
                        continue
                    text = (m.message or "").strip()
                    if not text and getattr(m, "media", None):
                        text = "[media]"
                    if cursor is None:
                        await set_cursor(api, ch, m.id)
                        logging.info(f"Baseline set for {ch}: last_tg_message_id={m.id} (no send)")
                        continue
                    if m.id > cursor:
                        published = m.date
                        if published.tzinfo is None:
                            published = published.replace(tzinfo=timezone.utc)
                        if text:
                            await send_post(
                                api,
                                channel=ch,
                                msg_id=m.id,
                                text=text,
                                published_at=published.isoformat(),
                            )
                        else:
                            logging.info(f"Skipped empty post from {ch}: {m.id}")
                        await set_cursor(api, ch, m.id)
                        logging.info(f"New post from {ch}: {m.id}")
                    else:
                        logging.info(f"No new posts in {ch} (cursor={cursor}, last={m.id})")
                except Exception as e:
                    logging.exception(f"Collector error for {ch}: {e}")
            await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
