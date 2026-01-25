import os
import httpx

API_URL = os.getenv("API_URL", "http://api:8000")

async def add_channel(tg_user_id: int, username: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{API_URL}/channels/add", json={
            "tg_user_id": tg_user_id,
            "username": username
        })
        r.raise_for_status()
        return r.json()

async def list_channels(tg_user_id: int) -> list[str]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{API_URL}/channels/list", params={"tg_user_id": tg_user_id})
        r.raise_for_status()
        data = r.json()
        return data.get("channels", [])

async def get_unsent_posts(tg_user_id: int, limit: int = 10) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API_URL}/posts/unsent", params={"tg_user_id": tg_user_id, "limit": limit})
        r.raise_for_status()
        return r.json().get("posts", [])

async def get_latest_posts(tg_user_id: int, limit: int = 50) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API_URL}/posts/latest", params={"tg_user_id": tg_user_id, "limit": limit})
        r.raise_for_status()
        return r.json().get("posts", [])

async def mark_posts_sent(post_ids: list[int]) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{API_URL}/posts/mark_sent", json=post_ids)
        r.raise_for_status()

async def set_forwarding(tg_user_id: int, enabled: bool) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{API_URL}/users/forwarding", params={"tg_user_id": tg_user_id}, json=enabled)
        r.raise_for_status()
        return r.json()

async def get_forwarding(tg_user_id: int) -> bool:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API_URL}/users/forwarding", params={"tg_user_id": tg_user_id})
        r.raise_for_status()
        return bool(r.json().get("enabled", True))

async def get_spam_filter(tg_user_id: int) -> bool:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API_URL}/users/spam_filter", params={"tg_user_id": tg_user_id})
        r.raise_for_status()
        return bool(r.json().get("enabled", False))

async def set_spam_filter(tg_user_id: int, enabled: bool) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{API_URL}/users/spam_filter", params={"tg_user_id": tg_user_id}, json=enabled)
        r.raise_for_status()
        return r.json()

async def get_short_feed(tg_user_id: int) -> bool:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API_URL}/users/short_feed", params={"tg_user_id": tg_user_id})
        r.raise_for_status()
        return bool(r.json().get("enabled", False))

async def set_short_feed(tg_user_id: int, enabled: bool) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{API_URL}/users/short_feed", params={"tg_user_id": tg_user_id}, json=enabled)
        r.raise_for_status()
        return r.json()

async def get_vip_status(tg_user_id: int) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API_URL}/users/vip_status", params={"tg_user_id": tg_user_id})
        r.raise_for_status()
        return r.json()

async def extend_vip(tg_user_id: int, days: int) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{API_URL}/users/vip_extend", json={
            "tg_user_id": tg_user_id,
            "days": days,
        })
        r.raise_for_status()
        return r.json()

async def delete_channel(tg_user_id: int, username: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{API_URL}/channels/delete", json={
            "tg_user_id": tg_user_id,
            "username": username
        })
        r.raise_for_status()
        return r.json()

async def delete_all_channels(tg_user_id: int) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{API_URL}/channels/delete_all", json={
            "tg_user_id": tg_user_id
        })
        r.raise_for_status()
        return r.json()

async def get_channel_cursor(tg_user_id: int, username: str) -> int | None:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{API_URL}/channels/cursor", params={
            "tg_user_id": tg_user_id,
            "username": username
        })
        r.raise_for_status()
        return r.json().get("last_tg_message_id")

async def set_channel_cursor(tg_user_id: int, username: str, last_tg_message_id: int) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{API_URL}/channels/cursor", json={
            "tg_user_id": tg_user_id,
            "username": username,
            "last_tg_message_id": last_tg_message_id
        })
        r.raise_for_status()
        return r.json()
