import asyncio
import os
import logging

from bot.api_client import get_unsent_posts, mark_posts_sent

log = logging.getLogger(__name__)

OWNER_TG_USER_ID = int(os.getenv("OWNER_TG_USER_ID", "0"))
INTERVAL = int(os.getenv("FEED_INTERVAL_SEC", "5"))

async def feed_loop(bot):
    if OWNER_TG_USER_ID == 0:
        raise RuntimeError("OWNER_TG_USER_ID is not set")

    while True:
        try:
            posts = await get_unsent_posts(OWNER_TG_USER_ID, limit=10)

            if posts:
                sent_ids = []
                for p in posts:
                    text = f"📰 {p['channel']}\n\n{p['text']}"
                    await bot.send_message(OWNER_TG_USER_ID, text)
                    sent_ids.append(p["id"])

                await mark_posts_sent(sent_ids)
                log.info(f"Sent {len(sent_ids)} posts")

        except Exception as e:
            log.exception(f"feed_loop error: {e}")

        await asyncio.sleep(INTERVAL)
