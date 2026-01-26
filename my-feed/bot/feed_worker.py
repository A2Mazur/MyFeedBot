import asyncio
import os
import logging
from pathlib import Path
from bot.api_client import get_unsent_posts, mark_posts_sent, get_short_feed
from bot.short_feed import summarize_to_one_sentence
from aiogram.types import FSInputFile, InputMediaDocument, InputMediaPhoto, InputMediaVideo
from worker.tasks import summarize_text as summarize_text_task

log = logging.getLogger(__name__)

OWNER_TG_USER_ID = int(os.getenv("OWNER_TG_USER_ID", "0"))
INTERVAL = int(os.getenv("FEED_INTERVAL_SEC", "5"))

def build_source_line(p: dict) -> str:
    channel = (p.get("channel") or "").lstrip("@")
    channel_title = (p.get("channel_title") or "").strip()
    msg_id = p.get("tg_message_id")
    source_url = f"https://t.me/{channel}/{msg_id}" if channel and msg_id else None
    source_name = channel_title or channel
    if source_url:
        return f'<b>Источник:</b> <a href="{source_url}">{source_name}</a>'
    return f"<b>Источник:</b> {source_name}"


async def feed_loop(bot):
    if OWNER_TG_USER_ID == 0:
        raise RuntimeError("OWNER_TG_USER_ID is not set")

    while True:
        try:
            short_feed_on = await get_short_feed(OWNER_TG_USER_ID)
            posts = await get_unsent_posts(OWNER_TG_USER_ID, limit=10)

            if posts:
                sent_ids = []
                for p in posts:
                    text_body = p.get("text", "")
                    if short_feed_on:
                        try:
                            async_result = summarize_text_task.delay(text_body)
                            text_body = await asyncio.to_thread(async_result.get, timeout=10)
                        except Exception:
                            text_body = await summarize_to_one_sentence(text_body)
                    source_line = build_source_line(p)
                    media_type = p.get("media_type")
                    media_paths = p.get("media_paths") or []

                    if media_paths:
                        files = [Path(path) for path in media_paths if path]
                        files = [f for f in files if f.exists()]
                        if media_type == "media_group" and files:
                            media = []
                            for idx, f in enumerate(files):
                                suffix = f.suffix.lower()
                                if suffix in VIDEO_EXTS:
                                    item = InputMediaVideo(media=FSInputFile(f))
                                elif suffix in IMAGE_EXTS:
                                    item = InputMediaPhoto(media=FSInputFile(f))
                                else:
                                    item = InputMediaDocument(media=FSInputFile(f))
                                if idx == 0:
                                    caption = source_line
                                    if text_body:
                                        caption = f"{source_line}\n\n{text_body}"
                                    item.caption = caption
                                    item.parse_mode = "HTML"
                                media.append(item)
                            await bot.send_media_group(OWNER_TG_USER_ID, media)
                        elif media_type == "voice" and files:
                            caption = source_line
                            if text_body:
                                caption = f"{source_line}\n\n{text_body}"
                            await bot.send_voice(
                                OWNER_TG_USER_ID,
                                voice=FSInputFile(files[0]),
                                caption=caption,
                                parse_mode="HTML",
                            )
                        elif media_type == "video" and files:
                            caption = source_line
                            if text_body:
                                caption = f"{source_line}\n\n{text_body}"
                            if files[0].suffix.lower() in VIDEO_EXTS:
                                await bot.send_video(
                                    OWNER_TG_USER_ID,
                                    video=FSInputFile(files[0]),
                                    caption=caption,
                                    parse_mode="HTML",
                                )
                            else:
                                await bot.send_document(
                                    OWNER_TG_USER_ID,
                                    document=FSInputFile(files[0]),
                                    caption=caption,
                                    parse_mode="HTML",
                                )
                        elif files:
                            caption = source_line
                            if text_body:
                                caption = f"{source_line}\n\n{text_body}"
                            if files[0].suffix.lower() in IMAGE_EXTS:
                                await bot.send_photo(
                                    OWNER_TG_USER_ID,
                                    photo=FSInputFile(files[0]),
                                    caption=caption,
                                    parse_mode="HTML",
                                )
                            else:
                                await bot.send_document(
                                    OWNER_TG_USER_ID,
                                    document=FSInputFile(files[0]),
                                    caption=caption,
                                    parse_mode="HTML",
                                )
                        else:
                            text = f"{source_line}\n\n{text_body}" if text_body else source_line
                            await bot.send_message(
                                OWNER_TG_USER_ID,
                                text,
                                parse_mode="HTML",
                                disable_web_page_preview=True,
                            )
                    else:
                        text = f"{source_line}\n\n{text_body}" if text_body else source_line
                        await bot.send_message(
                            OWNER_TG_USER_ID,
                            text,
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                        )
                    sent_ids.append(p["id"])

                await mark_posts_sent(sent_ids)
                log.info(f"Sent {len(sent_ids)} posts")

        except Exception as e:
            log.exception(f"feed_loop error: {e}")

        await asyncio.sleep(INTERVAL)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv"}
