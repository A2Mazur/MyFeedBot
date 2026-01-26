from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class VipCb(CallbackData, prefix="vip"):
    action: str
    plan: str | None = None


TARIFFS = {
    "7d": {"label": "🔥 7 дней — 199₽", "title": "7 дней", "price": 199, "stars": 150},
    "1m": {"label": "💪 1 месяц — 399₽", "title": "1 месяц", "price": 399, "stars": 250},
    "12m": {"label": "👑 12 месяцев — 1499₽", "title": "12 месяцев", "price": 1499, "stars": 750},
}


def get_tariff(plan: str) -> dict:
    return TARIFFS[plan]


def build_vip_tariffs_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for plan, data in TARIFFS.items():
        kb.button(text=data["label"], callback_data=VipCb(action="plan", plan=plan).pack())
    kb.adjust(1)
    return kb.as_markup()


def build_vip_payment_kb(plan: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Оплата картой", callback_data=VipCb(action="pay_card", plan=plan).pack())
    kb.button(text="🌳 Оплата по QR", callback_data=VipCb(action="pay_qr", plan=plan).pack())
    kb.button(text="⭐ Telegram Stars", callback_data=VipCb(action="pay_stars", plan=plan).pack())
    kb.button(text="⬅️ Назад", callback_data=VipCb(action="back").pack())
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def build_vip_stars_kb(plan: str, invoice_url: str) -> InlineKeyboardMarkup:
    tariff = get_tariff(plan)
    kb = InlineKeyboardBuilder()
    kb.button(text=f"⭐ {tariff['stars']} Telegram Stars", url=invoice_url)
    kb.button(text="← Назад", callback_data=VipCb(action="back_pay", plan=plan).pack())
    kb.adjust(1)
    return kb.as_markup()
