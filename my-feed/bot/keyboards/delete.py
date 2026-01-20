from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData


class DelCb(CallbackData, prefix="del"):
    action: str 
    username: str | None = None
    page: int = 0


def build_delete_kb(channels: list[str], page: int = 0, page_size: int = 10) -> InlineKeyboardMarkup:
    start = page * page_size
    end = start + page_size
    items = channels[start:end]
    kb = InlineKeyboardBuilder()
    for ch in items:
        title = ch.lstrip("@")
        kb.button(
            text=f"🗑 {title}",
            callback_data=DelCb(action="ch", username=ch, page=page).pack()
        )
    kb.adjust(2)
    has_next = end < len(channels)
    has_prev = page > 0
    nav = InlineKeyboardBuilder()
    if has_prev:
        nav.button(text="◀️ Назад", callback_data=DelCb(action="page", page=page - 1).pack())
    if has_next:
        nav.button(text="Вперёд ▶️", callback_data=DelCb(action="page", page=page + 1).pack())
    if has_prev or has_next:
        kb.row(*nav.buttons)
    all_btn = InlineKeyboardBuilder()
    all_btn.button(
        text="Удалить все",
        callback_data=DelCb(action="all", page=page).pack()
    )
    kb.row(*list(all_btn.buttons))


    return kb.as_markup()
