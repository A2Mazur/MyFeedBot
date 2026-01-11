from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

PAGE_SIZE = 10  # 10 кнопок на страницу (2 колонки = 5 рядов)

def _normalize(username: str) -> str:
    # Превращаем "@durov" -> "durov"
    return username.lstrip("@").strip()

def build_subscriptions_kb(channels: list[str], page: int) -> InlineKeyboardMarkup:
    """
    Делает клавиатуру как на скрине:
    - 2 колонки каналов
    - кнопки-ссылки на https://t.me/<username>
    - кнопки пагинации Назад/Вперёд
    """
    total = len(channels)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = channels[start:end]

    kb = InlineKeyboardBuilder()

    # Кнопки каналов (URL кнопки)
    for ch in page_items:
        uname = _normalize(ch)
        kb.button(text=uname, url=f"https://t.me/{uname}")

    kb.adjust(2)  # 2 колонки

    # Пагинация
    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="⬅️ Назад", callback_data=f"subs_page:{page-1}")
    if end < total:
        nav.button(text="Вперёд ▶️", callback_data=f"subs_page:{page+1}")

    if nav.buttons:
        kb.attach(nav)

    return kb.as_markup()
