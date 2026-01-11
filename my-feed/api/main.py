from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.db import engine, SessionLocal, Base
import api.models
from api.models import User, Channel

app = FastAPI(title="MyFeed API")

class AddChannelIn(BaseModel):
    tg_user_id: int
    username: str

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
