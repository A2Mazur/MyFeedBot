import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import json
from api.db import engine, SessionLocal, Base
import api.models
from api.models import User, Channel, Post
from sqlalchemy import desc, update, select, text, func
from fastapi import Body
import re


app = FastAPI(title="MyFeed API")
OWNER_TG_USER_ID = int(os.getenv("OWNER_TG_USER_ID", "0"))

class AddChannelIn(BaseModel):
    tg_user_id: int
    username: str

class AddPostIn(BaseModel):
    tg_user_id: int
    channel_username: str
    tg_message_id: int
    text: str
    published_at: datetime
    media_type: str | None = None
    media_paths: list[str] | None = None
    media_group_id: int | None = None

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

class SetChannelTitleIn(BaseModel):
    tg_user_id: int
    username: str
    title: str

class AdminVipGrantIn(BaseModel):
    admin_tg_user_id: int
    tg_user_id: int
    days: int | None = None
    forever: bool = False

class AdminVipRevokeIn(BaseModel):
    admin_tg_user_id: int
    tg_user_id: int

class UserProfileIn(BaseModel):
    tg_user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None

class FirstStartIn(BaseModel):
    tg_user_id: int
    trial_days: int = 7

class AdminBroadcastQuery(BaseModel):
    admin_tg_user_id: int
    group: str | None = None  # vip|free|active|all


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
                "ADD COLUMN IF NOT EXISTS welcome_sent BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS trial_vip_granted BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS vip_until TIMESTAMPTZ NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS username VARCHAR(255) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS first_name VARCHAR(255) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS last_name VARCHAR(255) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE posts "
                "ADD COLUMN IF NOT EXISTS media_type VARCHAR(50) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE posts "
                "ADD COLUMN IF NOT EXISTS media_paths TEXT NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE posts "
                "ADD COLUMN IF NOT EXISTS media_group_id BIGINT NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE channels "
                "ADD COLUMN IF NOT EXISTS title VARCHAR(255) NULL"
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

@app.post("/channels/title")
async def set_channel_title(payload: SetChannelTitleIn):
    username = payload.username.strip()
    if not username.startswith("@"):
        raise HTTPException(400, "username must start with @")
    title = payload.title.strip() if payload.title else ""
    if not title:
        return {"ok": True, "updated": False}
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == payload.tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            return {"ok": True, "updated": False}
        res = await session.execute(
            select(Channel).where(Channel.user_id == user.id, Channel.username == username)
        )
        channel = res.scalar_one_or_none()
        if not channel:
            return {"ok": True, "updated": False}
        if channel.title != title:
            channel.title = title
            await session.commit()
            return {"ok": True, "updated": True}
    return {"ok": True, "updated": False}

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
        media_paths = json.dumps(payload.media_paths) if payload.media_paths else None
        session.add(Post(
            channel_id=channel.id,
            tg_message_id=payload.tg_message_id,
            text=payload.text or "",
            media_type=payload.media_type,
            media_paths=media_paths,
            media_group_id=payload.media_group_id,
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
            select(Post, Channel.username, Channel.title)
            .join(Channel, Post.channel_id == Channel.id)
            .where(Channel.user_id == user.id)
            .order_by(desc(Post.published_at))
            .limit(limit)
        )
        posts = []
        for post, username, title in res.all():
            posts.append({
                "id": post.id,
                "channel": username,
                "channel_title": title,
                "tg_message_id": post.tg_message_id,
                "text": post.text,
                "media_type": post.media_type,
                "media_paths": json.loads(post.media_paths) if post.media_paths else None,
                "media_group_id": post.media_group_id,
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
            select(Post, Channel.username, Channel.title)
            .join(Channel, Post.channel_id == Channel.id)
            .where(Channel.user_id == user.id, Post.is_sent == False)
            .order_by(Post.published_at)
            .limit(limit * 3)
        )
        posts = []
        skipped_ids = []
        for post, username, title in res.all():
            if bool(user.spam_filter_on) and looks_like_ad(post.text):
                skipped_ids.append(post.id)
                continue
            posts.append({
                "id": post.id,
                "channel": username,
                "channel_title": title,
                "tg_message_id": post.tg_message_id,
                "text": post.text,
                "media_type": post.media_type,
                "media_paths": json.loads(post.media_paths) if post.media_paths else None,
                "media_group_id": post.media_group_id,
            })
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


@app.post("/users/profile")
async def upsert_user_profile(payload: UserProfileIn):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == payload.tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            user = User(tg_user_id=payload.tg_user_id)
            session.add(user)
            await session.flush()
        username = (payload.username or "").strip() or None
        if username and not username.startswith("@"):
            username = f"@{username}"
        user.username = username
        user.first_name = payload.first_name or user.first_name
        user.last_name = payload.last_name or user.last_name
        await session.commit()
        return {"ok": True}


@app.post("/users/first_start")
async def first_start(payload: FirstStartIn):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == payload.tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            user = User(tg_user_id=payload.tg_user_id)
            session.add(user)
            await session.flush()
        now = datetime.now(timezone.utc)
        welcome_needed = not bool(user.welcome_sent)
        trial_granted = False
        if welcome_needed:
            user.welcome_sent = True
        if not bool(user.trial_vip_granted):
            base = user.vip_until if user.vip_until and user.vip_until > now else now
            user.vip_until = base + timedelta(days=max(0, int(payload.trial_days)))
            user.trial_vip_granted = True
            trial_granted = True
        await session.commit()
        return {
            "welcome_needed": welcome_needed,
            "trial_granted": trial_granted,
            "vip_until": user.vip_until.isoformat() if user.vip_until else None,
        }


@app.get("/users/resolve")
async def resolve_user_id(username: str):
    username = username.strip()
    if not username:
        raise HTTPException(400, "username required")
    if not username.startswith("@"):
        username = f"@{username}"
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.username == username))
        user = res.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "user not found")
        return {"tg_user_id": user.tg_user_id}


@app.post("/admin/broadcast_targets")
async def get_broadcast_targets(payload: AdminBroadcastQuery):
    if OWNER_TG_USER_ID and payload.admin_tg_user_id != OWNER_TG_USER_ID:
        raise HTTPException(403, "forbidden")
    group = (payload.group or "all").lower()
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        stmt = select(User.tg_user_id)
        if group == "vip":
            stmt = stmt.where(User.vip_until.is_not(None), User.vip_until > now)
        elif group == "free":
            stmt = stmt.where((User.vip_until.is_(None)) | (User.vip_until <= now))
        elif group == "active":
            cutoff = now - timedelta(days=7)
            active_ids = (
                select(func.distinct(Channel.user_id))
                .select_from(Post)
                .join(Channel, Post.channel_id == Channel.id)
                .where(Post.is_sent == True, Post.published_at >= cutoff)
            )
            stmt = stmt.where(User.id.in_(active_ids))
        res = await session.execute(stmt)
        ids = [row[0] for row in res.all()]
        return {"targets": ids}


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


@app.get("/admin/stats")
async def get_admin_stats(tg_user_id: int):
    if OWNER_TG_USER_ID and tg_user_id != OWNER_TG_USER_ID:
        raise HTTPException(403, "forbidden")
    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    async with SessionLocal() as session:
        total_users = int((await session.execute(select(func.count(User.id)))).scalar() or 0)
        forwarding_on = int((await session.execute(
            select(func.count(User.id)).where(User.forwarding_on == True)
        )).scalar() or 0)
        short_feed_on = int((await session.execute(
            select(func.count(User.id)).where(User.short_feed_on == True)
        )).scalar() or 0)
        spam_filter_on = int((await session.execute(
            select(func.count(User.id)).where(User.spam_filter_on == True)
        )).scalar() or 0)
        vip_active = int((await session.execute(
            select(func.count(User.id)).where(User.vip_until.is_not(None), User.vip_until > now)
        )).scalar() or 0)
        vip_expiring_7d = int((await session.execute(
            select(func.count(User.id)).where(User.vip_until.is_not(None), User.vip_until > now, User.vip_until <= now + timedelta(days=7))
        )).scalar() or 0)
        channels_total = int((await session.execute(select(func.count(Channel.id)))).scalar() or 0)

        posts_7d = int((await session.execute(
            select(func.count(Post.id)).where(Post.is_sent == True, Post.published_at >= cutoff_7d)
        )).scalar() or 0)
        active_users_7d = int((await session.execute(
            select(func.count(func.distinct(Channel.user_id)))
            .select_from(Post)
            .join(Channel, Post.channel_id == Channel.id)
            .where(Post.is_sent == True, Post.published_at >= cutoff_7d)
        )).scalar() or 0)

        top_activity = (await session.execute(
            select(Channel.user_id, func.count(Post.id).label("cnt"))
            .select_from(Post)
            .join(Channel, Post.channel_id == Channel.id)
            .where(Post.is_sent == True, Post.published_at >= cutoff_7d)
            .group_by(Channel.user_id)
            .order_by(func.count(Post.id).desc())
            .limit(10)
        )).all()

        top_channels = (await session.execute(
            select(Channel.user_id, func.count(Channel.id).label("cnt"))
            .group_by(Channel.user_id)
            .order_by(func.count(Channel.id).desc())
            .limit(10)
        )).all()

    return {
        "users_total": total_users,
        "forwarding_on": forwarding_on,
        "short_feed_on": short_feed_on,
        "spam_filter_on": spam_filter_on,
        "vip_active": vip_active,
        "vip_expiring_7d": vip_expiring_7d,
        "channels_total": channels_total,
        "posts_7d": posts_7d,
        "active_users_7d": active_users_7d,
        "top_activity_7d": [{"user_id": uid, "count": cnt} for uid, cnt in top_activity],
        "top_channels": [{"user_id": uid, "count": cnt} for uid, cnt in top_channels],
    }


@app.post("/admin/vip_grant")
async def admin_grant_vip(payload: AdminVipGrantIn):
    if OWNER_TG_USER_ID and payload.admin_tg_user_id != OWNER_TG_USER_ID:
        # allow only admin to call this endpoint
        raise HTTPException(403, "forbidden")
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == payload.tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            user = User(tg_user_id=payload.tg_user_id)
            session.add(user)
            await session.flush()
        now = datetime.now(timezone.utc)
        if payload.forever:
            user.vip_until = now + timedelta(days=365 * 100)
        else:
            if not payload.days or payload.days <= 0:
                raise HTTPException(400, "days must be > 0")
            base = user.vip_until if user.vip_until and user.vip_until > now else now
            user.vip_until = base + timedelta(days=payload.days)
        await session.commit()
        return {"ok": True, "vip_until": user.vip_until.isoformat()}


@app.post("/admin/vip_revoke")
async def admin_revoke_vip(payload: AdminVipRevokeIn):
    if OWNER_TG_USER_ID and payload.admin_tg_user_id != OWNER_TG_USER_ID:
        raise HTTPException(403, "forbidden")
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_user_id == payload.tg_user_id))
        user = res.scalar_one_or_none()
        if not user:
            return {"ok": True, "revoked": False}
        user.vip_until = None
        await session.commit()
        return {"ok": True, "revoked": True}


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
