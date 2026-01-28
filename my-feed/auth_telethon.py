import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv(Path(__file__).with_name(".env"))

api_id = int(os.getenv("TG_API_ID", "0"))
api_hash = os.getenv("TG_API_HASH")
session_name = os.getenv("TG_SESSION", "collector")
phone = os.getenv("TG_PHONE")

if not api_id or not api_hash:
    raise RuntimeError("TG_API_ID / TG_API_HASH are not set")

client = TelegramClient(session_name, api_id, api_hash)
client.start(phone=phone)  # попросит телефон/код при первом входе
print(f"OK (session={session_name})")
client.disconnect()
