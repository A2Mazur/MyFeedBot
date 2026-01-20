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
