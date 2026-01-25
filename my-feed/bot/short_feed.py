import logging
import os

import httpx

log = logging.getLogger(__name__)

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_BASE_URL = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai")


def _first_sentence(text: str) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    for sep in (". ", "! ", "? ", "… "):
        idx = text.find(sep)
        if idx != -1:
            return text[: idx + 1]
    return text


async def summarize_to_one_sentence(text: str) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    if not MISTRAL_API_KEY:
        return _first_sentence(text)

    payload = {
        "model": MISTRAL_MODEL,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Сократи текст до ОДНОГО предложения на русском. "
                    "Без эмодзи, без добавления фактов."
                ),
            },
            {"role": "user", "content": text},
        ],
    }

    url = f"{MISTRAL_BASE_URL}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            result = data["choices"][0]["message"]["content"].strip()
            return result or _first_sentence(text)
        except Exception as e:
            log.exception(f"Short feed summarize failed: {e}")
            return _first_sentence(text)
