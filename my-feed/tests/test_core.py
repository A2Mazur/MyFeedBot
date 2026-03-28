import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.main import looks_like_ad, health
from bot.parsers import extract_channels
import bot.short_feed as short_feed


def test_health_function():
    assert health() == {"status": "ok"}


def test_looks_like_ad():
    assert looks_like_ad("Большая скидка только сегодня")
    assert looks_like_ad("Реклама: подпишись")
    assert not looks_like_ad("Обычная новость без рекламы")


def test_extract_channels():
    text = "Подпишись на @example и https://t.me/test_channel"
    assert extract_channels(text) == ["@example", "@test_channel"]


def test_summarize_fallback_first_sentence():
    short_feed.MISTRAL_API_KEY = None
    text = "Первое предложение. Второе предложение."
    result = asyncio.run(short_feed.summarize_to_one_sentence(text))
    assert result.strip() == "Первое предложение."
