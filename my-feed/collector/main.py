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

async def main():
    tg = build_client()
    await tg.start()
    async with httpx.AsyncClient(timeout=20) as api:
        last_seen: dict[str, int] = {}
        while True:
            channels = await fetch_channels(api)
            for ch in channels:
                try:
                    entity = await tg.get_entity(ch)
                    messages = await tg.get_messages(entity, limit=20)
                    for m in reversed(messages):
                        if not m.id or not m.message:
                            continue
                        if last_seen.get(ch, 0) >= m.id:
                            continue
                        published = m.date
                        if published.tzinfo is None:
                            published = published.replace(tzinfo=timezone.utc)
                        await send_post(
                            api,
                            channel=ch,
                            msg_id=m.id,
                            text=m.message,
                            published_at=published.isoformat(),
                        )
                        last_seen[ch] = m.id
                    logging.info(f"Collected from {ch}")
                except Exception as e:
                    logging.exception(f"Collector error for {ch}: {e}")
            await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
