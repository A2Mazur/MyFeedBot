from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from api.db import engine, SessionLocal, Base
import api.models
from api.models import User, Channel, Post
from sqlalchemy import desc, update, select, text, func
from fastapi import Body
import re


app = FastAPI(title="MyFeed API")

class AddChannelIn(BaseModel):
    tg_user_id: int
    username: str

class AddPostIn(BaseModel):
    tg_user_id: int
    channel_username: str
    tg_message_id: int
    text: str
    published_at: datetime

class DeleteChannelIn(BaseModel):
    tg_user_id: int
    username: str

class DeleteAllChannelsIn(BaseModel):
    tg_user_id: int

class SetCursorIn(BaseModel):
    tg_user_id: int
    username: str
    last_tg_message_id: int

class VipExtendIn(BaseModel):
    tg_user_id: int
    days: int


AD_PATTERNS = [
    r"\bреклама\b",
    r"\bспонсор\b",
    r"\bпартнер(?:ский|ская|ское|ские)?\b",
    r"\bпромокод\b",
    r"\bскидк[аиу]\b",
    r"\bакци[яи]\b",
    r"\bкупить\b",
    r"\bзакажи\b",
    r"\bподписывайся\b",
    r"\bподпишись\b",
    r"\bрозыгрыш\b",
    r"\bдарим\b",
    r"\bsale\b",
    r"\bad\b",
    r"\bsponsored\b",
    r"\bpromo\b",
]
AD_RE = re.compile("|".join(AD_PATTERNS), re.IGNORECASE)


def looks_like_ad(text_value: str) -> bool:
    text_value = (text_value or "").strip()
    if not text_value:
        return False
    return bool(AD_RE.search(text_value))


@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS spam_filter_on BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS short_feed_on BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS vip_until TIMESTAMPTZ NULL"
            )
        )

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/channels/add")
async def add_channel(payload: AddChannelIn):
    username = payload.username.strip()
    if not username.startswith("@"):
        raise HTTPException(400, "username must start with @")

    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == payload.tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            user = User(tg_user_id=payload.tg_user_id)
            session.add(user)
            await session.flush() 
        now = datetime.now(timezone.utc)
        vip_active = bool(user.vip_until and user.vip_until > now)
        limit = 50 if vip_active else 10
        res = await session.execute(
            select(func.count(Channel.id)).where(Channel.user_id == user.id)
        )
        channel_count = int(res.scalar() or 0)
        if channel_count >= limit:
            return {"ok": False, "message": "limit reached", "limit": limit}
        res = await session.execute(
            select(Channel).where(Channel.user_id == user.id, Channel.username == username)
        )
        if res.scalar_one_or_none():
            return {"ok": True, "message": "already added"}
        session.add(Channel(user_id=user.id, username=username))
        await session.commit()
    return {"ok": True}

# Получаем список каналов пользователя
@app.get("/channels/list")
async def list_channels(tg_user_id: int):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            return {"channels": []}
        res = await session.execute(select(Channel.username).where(Channel.user_id == user.id))
        channels = [row[0] for row in res.all()]
        return {"channels": channels}
    
@app.get("/channels/cursor")
async def get_channel_cursor(tg_user_id: int, username: str):
    username = username.strip()
    if not username.startswith("@"):
        raise HTTPException(400, "username must start with @")

    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            return {"last_tg_message_id": None}

        res = await session.execute(
            select(Channel.last_tg_message_id)
            .where(Channel.user_id == user.id, Channel.username == username)
        )
        row = res.one_or_none()
        return {"last_tg_message_id": row[0] if row else None}


@app.post("/channels/cursor")
async def set_channel_cursor(payload: SetCursorIn):
    username = payload.username.strip()
    if not username.startswith("@"):
        raise HTTPException(400, "username must start with @")

    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == payload.tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "user not found")

        res = await session.execute(
            select(Channel).where(Channel.user_id == user.id, Channel.username == username)
        )
        channel = res.scalar_one_or_none()
        if not channel:
            raise HTTPException(404, "channel not found")

        channel.last_tg_message_id = payload.last_tg_message_id
        await session.commit()

    return {"ok": True}

@app.post("/channels/delete")
async def delete_channel(payload: DeleteChannelIn):
    username = payload.username.strip()
    if not username.startswith("@"):
        raise HTTPException(400, "username must start with @")
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == payload.tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            return {"ok": True, "deleted": False, "message": "user not found"}
        res = await session.execute(
            select(Channel).where(Channel.user_id == user.id, Channel.username == username)
        )
        channel = res.scalar_one_or_none()
        if not channel:
            return {"ok": True, "deleted": False, "message": "channel not found"}

        await session.delete(channel)
        await session.commit()

    return {"ok": True, "deleted": True}


@app.post("/channels/delete_all")
async def delete_all_channels(payload: DeleteAllChannelsIn):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == payload.tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            return {"ok": True, "deleted": 0}
        res = await session.execute(select(Channel).where(Channel.user_id == user.id))
        channels = res.scalars().all()
        deleted = 0
        for ch in channels:
            await session.delete(ch)
            deleted += 1
        await session.commit()

    return {"ok": True, "deleted": deleted}



@app.post("/posts/add")
async def add_post(payload: AddPostIn):
    ch = payload.channel_username.strip()
    if not ch.startswith("@"):
        raise HTTPException(400, "channel_username must start with @")
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == payload.tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "user not found")
        res = await session.execute(
            select(Channel).where(Channel.user_id == user.id, Channel.username == ch)
        )
        channel = res.scalar_one_or_none()
        if not channel:
            raise HTTPException(404, "channel not found")
        res = await session.execute(
            select(Post).where(Post.channel_id == channel.id, Post.tg_message_id == payload.tg_message_id)
        )
        if res.scalar_one_or_none():
            return {"ok": True, "message": "already exists"}
        session.add(Post(
            channel_id=channel.id,
            tg_message_id=payload.tg_message_id,
            text=payload.text or "",
            published_at=payload.published_at,
            is_sent=False,
        ))
        await session.commit()
    return {"ok": True}

@app.get("/posts/latest")
async def latest_posts(tg_user_id: int, limit: int = 20):
    limit = max(1, min(limit, 100))
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            return {"posts": []}
        res = await session.execute(
            select(Post, Channel.username)
            .join(Channel, Post.channel_id == Channel.id)
            .where(Channel.user_id == user.id)
            .order_by(desc(Post.published_at))
            .limit(limit)
        )
        posts = []
        for post, username in res.all():
            posts.append({
                "id": post.id,
                "channel": username,
                "tg_message_id": post.tg_message_id,
                "text": post.text,
                "published_at": post.published_at.isoformat(),
                "is_sent": post.is_sent,
            })
        return {"posts": posts}

@app.get("/posts/unsent")
async def unsent_posts(tg_user_id: int, limit: int = 10):
    limit = max(1, min(limit, 50))
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            return {"posts": []}
        if not bool(user.forwarding_on):
            return {"posts": []}
        res = await session.execute(
            select(Post, Channel.username)
            .join(Channel, Post.channel_id == Channel.id)
            .where(Channel.user_id == user.id, Post.is_sent == False)
            .order_by(Post.published_at)
            .limit(limit * 3)
        )
        posts = []
        skipped_ids = []
        for post, username in res.all():
            if bool(user.spam_filter_on) and looks_like_ad(post.text):
                skipped_ids.append(post.id)
                continue
            posts.append({"id": post.id, "channel": username, "text": post.text})
            if len(posts) >= limit:
                break
        if skipped_ids:
            await session.execute(
                update(Post).where(Post.id.in_(skipped_ids)).values(is_sent=True)
            )
            await session.commit()
        return {"posts": posts}

@app.post("/posts/mark_sent")
async def mark_posts_sent(post_ids: list[int]):
    if not post_ids:
        return {"ok": True}
    async with SessionLocal() as session:
        await session.execute(
            update(Post).where(Post.id.in_(post_ids)).values(is_sent=True)
        )
        await session.commit()
    return {"ok": True}

@app.get("/users/forwarding")
async def get_user_forwarding(tg_user_id: int):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()
        return {"enabled": bool(user.forwarding_on) if user else True}



@app.post("/users/forwarding")
async def set_user_forwarding(tg_user_id: int, enabled: bool = Body(...)):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()

        if not user:
            user = User(tg_user_id=tg_user_id, forwarding_on=bool(enabled))
            session.add(user)
            await session.commit()
            return {"ok": True, "enabled": bool(user.forwarding_on)}

        user.forwarding_on = bool(enabled)
        await session.commit()
        return {"ok": True, "enabled": bool(user.forwarding_on)}


@app.get("/users/spam_filter")
async def get_user_spam_filter(tg_user_id: int):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()
        return {"enabled": bool(user.spam_filter_on) if user else False}


@app.post("/users/spam_filter")
async def set_user_spam_filter(tg_user_id: int, enabled: bool = Body(...)):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()

        if not user:
            user = User(tg_user_id=tg_user_id, forwarding_on=True, spam_filter_on=bool(enabled))
            session.add(user)
            await session.commit()
            return {"ok": True, "enabled": bool(user.spam_filter_on)}

        user.spam_filter_on = bool(enabled)
        await session.commit()
        return {"ok": True, "enabled": bool(user.spam_filter_on)}


@app.get("/users/short_feed")
async def get_user_short_feed(tg_user_id: int):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()
        return {"enabled": bool(user.short_feed_on) if user else False}


@app.post("/users/short_feed")
async def set_user_short_feed(tg_user_id: int, enabled: bool = Body(...)):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()

        if not user:
            user = User(
                tg_user_id=tg_user_id,
                forwarding_on=True,
                spam_filter_on=False,
                short_feed_on=bool(enabled),
            )
            session.add(user)
            await session.commit()
            return {"ok": True, "enabled": bool(user.short_feed_on)}

        user.short_feed_on = bool(enabled)
        await session.commit()
        return {"ok": True, "enabled": bool(user.short_feed_on)}


@app.get("/users/vip_status")
async def get_user_vip_status(tg_user_id: int):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
        user = res.scalar_one_or_none()
        vip_until = user.vip_until if user else None
        now = datetime.now(timezone.utc)
        active = bool(vip_until and vip_until > now)
        return {
            "active": active,
            "vip_until": vip_until.isoformat() if vip_until else None,
        }


@app.post("/users/vip_extend")
async def extend_user_vip(payload: VipExtendIn):
    if payload.days <= 0:
        raise HTTPException(400, "days must be > 0")
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == payload.tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            user = User(tg_user_id=payload.tg_user_id)
            session.add(user)
            await session.flush()

        now = datetime.now(timezone.utc)
        base = user.vip_until if user.vip_until and user.vip_until > now else now
        user.vip_until = base + timedelta(days=payload.days)
        await session.commit()
        return {"ok": True, "vip_until": user.vip_until.isoformat()}
