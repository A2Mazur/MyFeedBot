from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from sqlalchemy import DateTime, Text, BigInteger, ForeignKey, UniqueConstraint, Boolean, String, Integer
from api.db import Base

# Table users
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    forwarding_on: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    spam_filter_on: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    short_feed_on: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    welcome_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trial_vip_granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vip_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

# The table of channels that the user added
class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    username: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    __table_args__ = (UniqueConstraint("user_id", "username", name="uq_user_channel"),)
    last_tg_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        index=True,
    )
    tg_message_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    media_paths: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    __table_args__ = (
        UniqueConstraint("channel_id", "tg_message_id", name="uq_channel_msg"),
    )
