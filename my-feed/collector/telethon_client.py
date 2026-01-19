import os
from telethon import TelegramClient

def build_client() -> TelegramClient:
    api_id = int(os.getenv("TG_API_ID"))
    api_hash = os.getenv("TG_API_HASH")
    session_name = os.getenv("TG_SESSION", "collector")

    if not api_id or not api_hash:
        raise RuntimeError("TG_API_ID / TG_API_HASH are not set")

    return TelegramClient(session_name, api_id, api_hash)
