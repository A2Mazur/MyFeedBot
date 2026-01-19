from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from datetime import datetime
from api.db import engine, SessionLocal, Base
import api.models
from api.models import User, Channel, Post
from sqlalchemy import desc, update


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

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
        res = await session.execute(
            select(Post, Channel.username)
            .join(Channel, Post.channel_id == Channel.id)
            .where(Channel.user_id == user.id, Post.is_sent == False)
            .order_by(Post.published_at)
            .limit(limit)
        )
        posts = []
        for post, username in res.all():
            posts.append({"id": post.id, "channel": username, "text": post.text})
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
