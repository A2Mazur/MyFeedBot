import json
import logging
import os
from datetime import datetime, timezone, timedelta
from html import escape

import httpx

log = logging.getLogger(__name__)

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_BASE_URL = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai")


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def select_recent_posts(posts: list[dict], hours: int = 12, limit: int = 20) -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    selected = []
    for p in posts:
        if not p.get("is_sent"):
            continue
        dt = _parse_dt(p.get("published_at", ""))
        if not dt or dt < cutoff:
            continue
        selected.append(p)
        if len(selected) >= limit:
            break
    return selected


def _normalize_text(text: str, max_len: int = 800) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned


def _post_link(channel: str, msg_id: int) -> str:
    username = (channel or "").lstrip("@")
    if not username or not msg_id:
        return ""
    return f"https://t.me/{username}/{msg_id}"


def _build_prompt(posts: list[dict]) -> str:
    lines = []
    for p in posts:
        channel = p.get("channel", "")
        channel_title = p.get("channel_title", "") or ""
        msg_id = int(p.get("tg_message_id") or 0)
        text = _normalize_text(p.get("text", ""))
        if not text:
            continue
        link = _post_link(channel, msg_id)
        lines.append(f"CHANNEL={channel} TITLE={channel_title} LINK={link} TEXT={text}")
    return "\n".join(lines)


def _format_digest(items: list[dict]) -> str:
    lines = ["🤖 Сводка:", ""]
    for item in items:
        summary = escape(str(item.get("summary", "")).strip())
        sources = item.get("sources") or []
        links = []
        for s in sources:
            title = str(s.get("title", "")).strip()
            ch = escape(title if title else str(s.get("channel", "")).strip())
            link = str(s.get("link", "")).strip()
            if not ch or not link:
                continue
            links.append(f"<a href=\"{link}\">{ch}</a>")
        if not summary or not links:
            continue
        lines.append(f"• {summary} — {', '.join(links)}")
    return "\n".join(lines).strip()

def _extract_json(text: str) -> list[dict] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        snippet = cleaned[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return None
    return None


async def generate_digest(posts: list[dict]) -> str:
    if not MISTRAL_API_KEY:
        return "Ключ MISTRAL_API_KEY не задан. Добавь его в .env."

    payload = {
        "model": MISTRAL_MODEL,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Сделай краткую сводку на русском. "
                    "Используй только факты из постов, без выдумок. "
                    "Если несколько постов про одно и то же событие, объединяй в один пункт "
                    "и перечисляй все источники. "
                    "Верни ТОЛЬКО JSON-массив объектов, без пояснений. "
                    "Используй в источниках TITLE (название канала), не @username. "
                    "Формат объекта:\n"
                    "{\n"
                    "  \"summary\": \"одно предложение\",\n"
                    "  \"sources\": [\n"
                    "    {\"title\": \"Название канала\", \"link\": \"https://t.me/channel/123\"}\n"
                    "  ]\n"
                    "}\n"
                    "summary должно быть ОДНИМ предложением."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Сделай сводку по этим постам за последние 12 часов:\n\n"
                    f"{_build_prompt(posts)}"
                ),
            },
        ],
    }

    url = f"{MISTRAL_BASE_URL}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"].strip()
            items = _extract_json(content)
            if not items:
                log.error(f"Digest JSON parse failed. Raw content: {content[:500]}")
                return "Сводка не сформировалась (ошибка формата). Попробуй еще раз."
            return _format_digest(items)
        except Exception as e:
            log.exception(f"Digest generation failed: {e}")
            return "Не удалось сгенерировать сводку. Попробуй позже."
