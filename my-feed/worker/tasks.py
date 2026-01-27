import asyncio
import os
import httpx

from worker.celery_app import celery

@celery.task
def ping():
    return "pong"

def _first_sentence(text: str) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    for sep in (". ", "! ", "? ", "… "):
        idx = text.find(sep)
        if idx != -1:
            return text[: idx + 1]
    return text


@celery.task
def summarize_text(text: str) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    mistral_key = os.getenv("MISTRAL_API_KEY")
    mistral_model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    base_url = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai")
    if not mistral_key:
        return _first_sentence(text)

    payload = {
        "model": mistral_model,
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
    headers = {"Authorization": f"Bearer {mistral_key}"}
    url = f"{base_url}/v1/chat/completions"

    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        result = data["choices"][0]["message"]["content"].strip()
        return result or _first_sentence(text)
    except Exception:
        return _first_sentence(text)
