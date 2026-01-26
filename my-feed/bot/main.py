import asyncio
import logging
import os
import uuid

import httpx
import qrcode
from datetime import datetime, timezone
from io import BytesIO
from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from bot.api_client import (
    add_channel,
    delete_all_channels,
    delete_channel,
    get_forwarding,
    get_latest_posts,
    get_vip_status,
    get_short_feed,
    get_spam_filter,
    list_channels,
    extend_vip,
    set_forwarding,
    set_short_feed,
    set_spam_filter,
)
from bot.digest import select_recent_posts, generate_digest
from bot.feed_worker import feed_loop
from bot.keyboards.delete import build_delete_kb, DelCb
from bot.keyboards.subscriptions import build_subscriptions_kb
from bot.keyboards.vip import (
    VipCb,
    build_vip_payment_kb,
    build_vip_stars_kb,
    build_vip_tariffs_kb,
    get_tariff,
)
from bot.parsers import extract_channels


class YkBadRequestError(Exception):
    pass


async def yk_create_payment(
    user_id: int,
    plan: str,
    confirmation_type: str = "redirect",
    payment_method_data: dict | None = None,
) -> tuple[str, dict]:
    shop_id = os.getenv("YOOKASSA_SHOP_ID")
    secret_key = os.getenv("YOOKASSA_SECRET_KEY")
    tax_system_code = int(os.getenv("YOOKASSA_TAX_SYSTEM_CODE", "1"))
    if not shop_id or not secret_key:
        raise RuntimeError("YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY are not set in .env")
    receipt_email = os.getenv("YOOKASSA_RECEIPT_EMAIL") or f"user{user_id}@example.com"

    tariff = get_tariff(plan)
    amount_value = f"{tariff['price']:.2f}"
    return_url = os.getenv("YOOKASSA_RETURN_URL", "https://t.me")
    idempotence_key = str(uuid.uuid4())

    confirmation = {"type": confirmation_type, "return_url": return_url}
    payload = {
        "amount": {"value": amount_value, "currency": "RUB"},
        "confirmation": confirmation,
        "capture": True,
        "description": f"VIP на {tariff['title']}",
        "metadata": {"user_id": user_id, "plan": plan},
        "receipt": {
            "customer": {"email": receipt_email},
            "tax_system_code": tax_system_code,
            "items": [
                {
                    "description": f"VIP на {tariff['title']}",
                    "quantity": "1.00",
                    "amount": {"value": amount_value, "currency": "RUB"},
                    "vat_code": 1,
                    "payment_subject": "service",
                    "payment_mode": "full_prepayment",
                }
            ],
        },
    }
    if payment_method_data:
        payload["payment_method_data"] = payment_method_data

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                "https://api.yookassa.ru/v3/payments",
                auth=(shop_id, secret_key),
                headers={"Idempotence-Key": idempotence_key},
                json=payload,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            detail = e.response.text.strip()
            if e.response.status_code == 400:
                raise YkBadRequestError(detail) from e
            raise RuntimeError(f"YooKassa error: {detail}") from e
        data = resp.json()
        return data["id"], data["confirmation"]


async def yk_check_payment(payment_id: str) -> str:
    shop_id = os.getenv("YOOKASSA_SHOP_ID")
    secret_key = os.getenv("YOOKASSA_SECRET_KEY")
    if not shop_id or not secret_key:
        raise RuntimeError("YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY are not set in .env")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"https://api.yookassa.ru/v3/payments/{payment_id}",
            auth=(shop_id, secret_key),
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("status", "unknown")


def format_vip_until(iso_value: str | None) -> str | None:
    if not iso_value:
        return None
    try:
        dt = datetime.fromisoformat(iso_value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%d.%m.%Y")


def build_vip_screen_text(vip_until_iso: str | None) -> str:
    vip_date = format_vip_until(vip_until_iso)
    if vip_date:
        header = f"🔒 Подписка активна до {vip_date}\n\n"
    else:
        header = "🔒 Подписка не активна\n\n"
    return (
        header
        + "📌 Тарифы для подписчиков\n\n"
        + "💎 VIP-подписка\n"
        + "— Возможность добавить до 50 каналов (у обычных пользователей — максимум 10).\n"
        + "— Доступ к ИИ-опциям: краткая лента, сжатие постов, сводка новостей.\n"
        + "— Возможность отключить рекламные и партнёрские посты каналов.\n"
        + "— Приоритетная поддержка и более быстрая доставка постов.\n\n"
        + "Выберите тариф:"
    )


def get_tariff_days(plan: str, tariff: dict) -> int | None:
    days = tariff.get("days")
    if days:
        return int(days)
    fallback = {"7d": 7, "1m": 30, "12m": 365}
    return fallback.get(plan)


async def ensure_vip(msg: Message, feature_name: str, feature_desc: str) -> bool:
    status = await get_vip_status(msg.from_user.id)
    if status.get("active"):
        return True
    text = (
        "🔒 Эта функция доступна только для VIP-пользователей.\n\n"
        f"{feature_name} — {feature_desc}\n\n"
        "🚀 Оформите подписку через команду /vip — и получите доступ к функциям."
    )
    await msg.answer(text)
    return False

async def setup_commands(bot: Bot):
    commands = [
        BotCommand(command="subscriptions", description="Ваши подписки 📋"),
        BotCommand(command="digest", description="Сводка ✍️"),
        BotCommand(command="switch_feed", description="Краткая лента 🗒️"),
        BotCommand(command="spam", description="Отключить рекламу и партнерские посты каналов 🚫📣"),
        BotCommand(command="start", description="Активировать пересылку ✅"),
        BotCommand(command="stop", description="Остановить пересылку ⛔"),
        BotCommand(command="vip", description="Стать VIP-пользователем 💎"),
        BotCommand(command="delete", description="Удалить подписку ❌"),
        BotCommand(command="help", description="Инструкция бота ⚙️"),
    ]
    await bot.set_my_commands(commands)

async def main():
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set in .env")
    bot = Bot(token=token)
    asyncio.create_task(feed_loop(bot))
    dp = Dispatcher()
    welcomed_users: set[int] = set()
    card_payments: dict[tuple[int, str], str] = {}
    qr_payments: dict[tuple[int, str], str] = {}
    stars_payloads: dict[str, str] = {}
    stars_last_plan: dict[int, str] = {}
    await setup_commands(bot)
    @dp.message(Command("help"))
    async def cmd_help(msg: Message):
        await msg.answer(
            "📰 Твоя персональная лента новостей в Telegram!\n\n"

            "Вот что умеет бот:\n\n"

            "• /subscriptions — список твоих подписок.\n"
            "• /digest — ИИ-сводка по всем каналам в одно сообщение.\n"
            "• /switch_feed — включить режим Краткой ленты: только текст, только суть.\n"
            "• /spam – Отключить рекламные и партнерские посты каналов.\n"
            "• /start — включить доставку постов с каналов.\n"
            "• /stop — приостановить пересылку.\n"
            "• /delete — удалить ненужные каналы.\n"
            "• /vip — доступ к 50 каналам, ИИ-режиму и приоритетной скорости.\n\n"

            "Как добавить канал: просто пришли ссылку или @ник (например, @telegram).\n\n"

            "Оставайся в курсе главного — быстро, удобно, без лишнего ✨"
        )

    @dp.message(Command("subscriptions"))
    async def cmd_subscriptions(msg: Message):
        channels = await list_channels(msg.from_user.id)
        if not channels:
            await msg.answer("Подписок пока нет. Пришли @username или ссылку на канал — я добавлю ✅")
            return
        text = "Ваши подписки:"
        kb = build_subscriptions_kb(channels, page=0)
        await msg.answer(text, reply_markup=kb)


    @dp.message(Command("delete"))
    async def cmd_delete(msg: Message):
        channels = await list_channels(msg.from_user.id)
        if not channels:
            await msg.answer("Подписок пока нет. /subscriptions — посмотреть список")
            return
        text = "Выберите канал для удаления:"
        kb = build_delete_kb(channels, page=0)
        await msg.answer(text, reply_markup=kb)

    WELCOME_TEXT = (
        "👋 Добро пожаловать!\n\n"
        "Я — твоя персональная лента новостей из Telegram 📲\n\n"
        "📌 Как пользоваться:\n"
        "— Отправь ссылку или @ник канала, чтобы подписаться.\n"
        "— Посты будут приходить прямо сюда.\n"
        "— Для полного списка команд используй /help.\n\n"
        "✨ Хочешь до 50 каналов, сводки ИИ и фильтр рекламы? Жми /vip."
    )

    @dp.message(Command("start"))
    async def cmd_start_forward(msg: Message):
        user_id = msg.from_user.id
        if user_id not in welcomed_users:
            welcomed_users.add(user_id)
            await msg.answer(WELCOME_TEXT)
            #активация бесплатной подписки на 7 дней всем пользователям, активирующим бота
            try:
                await extend_vip(user_id, 7)
                await msg.answer("🎁 Вам активирована бесплатная VIP-подписка на 7 дней!")
            except Exception:
                await msg.answer("🎁 Вам доступен бесплатный VIP на 7 дней. Активируйте его через /vip.")
        await set_forwarding(user_id, True)
        await msg.answer("Пересылка сообщений активирована ✅")

    @dp.message(Command("stop"))
    async def cmd_stop_forward(msg: Message):
        user_id = msg.from_user.id
        await set_forwarding(user_id, False)
        await msg.answer("Пересылка сообщений остановлена ⛔️")


    @dp.message(Command("digest"))
    async def cmd_digest(msg: Message):
        if not await ensure_vip(msg, "Digest", "умная сводка новостей."):
            return
        await msg.answer("Готовлю сводку... 📝")
        posts = await get_latest_posts(msg.from_user.id, limit=50)
        recent = select_recent_posts(posts, hours=12, limit=20)
        if not recent:
            await msg.answer("За последние 12 часов нет постов для сводки.")
            return
        digest = await generate_digest(recent)
        await msg.answer(digest, parse_mode="HTML", disable_web_page_preview=True)

    @dp.message(Command("spam"))
    async def cmd_spam(msg: Message):
        if not await ensure_vip(msg, "Spam", "фильтр, скрывающий рекламные публикации."):
            return
        user_id = msg.from_user.id
        enabled = await get_spam_filter(user_id)
        new_state = not enabled
        await set_spam_filter(user_id, new_state)
        if new_state:
            await msg.answer("✅ Фильтр рекламы включён. Партнёрские/рекламные посты больше не будут приходить.")
        else:
            await msg.answer("✅ Фильтр рекламы выключен. Буду присылать все посты.")

    @dp.message(Command("switch_feed"))
    async def cmd_switch_feed(msg: Message):
        if not await ensure_vip(msg, "Switch Feed", "переключение между полной и краткой лентой."):
            return
        user_id = msg.from_user.id
        enabled = await get_short_feed(user_id)
        new_state = not enabled
        await set_short_feed(user_id, new_state)
        if new_state:
            await msg.answer("✅ Включён режим «Для тех, кто ценит время».")
        else:
            await msg.answer("✅ Обычный режим ленты снова активен.")

    @dp.message(Command("vip"))
    async def cmd_vip(msg: Message):
        status = await get_vip_status(msg.from_user.id)
        text = build_vip_screen_text(status.get("vip_until"))
        await msg.answer(text, reply_markup=build_vip_tariffs_kb())

    @dp.message()
    async def any_text(msg: Message):
        if msg.successful_payment:
            return
        text = msg.text or ""
        channels = extract_channels(text)

        if not channels:
            await msg.answer("Не вижу ссылок/username. Пришли, например: @durov или https://t.me/durov")
            return

        added = 0
        already = 0
        errors = 0
        limit_reached = None

        for ch in channels:
            try:
                res = await add_channel(msg.from_user.id, ch)
                if res.get("message") == "already added":
                    already += 1
                elif res.get("message") == "limit reached":
                    limit_reached = res.get("limit")
                    break
                else:
                    added += 1
            except Exception:
                errors += 1

        reply = []
        if added:
            reply.append(f"Добавлено ✅: {added}")
        if already:
            reply.append(f"Уже было 👍: {already}")
        if limit_reached:
            reply.append(f"🚫 Достигнут лимит: {limit_reached} каналов. /vip — увеличить лимит.")
        if errors:
            reply.append(f"Ошибки ⚠️: {errors}")

        reply.append("\n/subscriptions — посмотреть список")
        await msg.answer("\n".join(reply))

    @dp.callback_query(F.data.startswith("subs_page:"))
    async def cb_subs_page(cb: CallbackQuery):
        page = int(cb.data.split(":")[1])

        channels = await list_channels(cb.from_user.id)
        text = "Ваши подписки:"
        kb = build_subscriptions_kb(channels, page=page)

        try:
            await cb.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise

        await cb.answer()

    @dp.callback_query(DelCb.filter())
    async def cb_delete(cb: CallbackQuery, callback_data: DelCb):
        channels = await list_channels(cb.from_user.id)
        if callback_data.action == "page":
            page = max(0, callback_data.page)
            text = "Выберите канал для удаления:"
            kb = build_delete_kb(channels, page=page)

            try:
                await cb.message.edit_text(text, reply_markup=kb)
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e).lower():
                    raise

            await cb.answer()
            return
        if callback_data.action == "ch" and callback_data.username:
            username = callback_data.username
            await delete_channel(cb.from_user.id, username)
            channels = await list_channels(cb.from_user.id)
            if not channels:
                await cb.message.edit_text("✅ Все каналы удалены.\n\nТеперь список пуст.")
                await cb.answer()
                return
            page = max(0, callback_data.page)
            page_size = 10
            max_page = max(0, (len(channels) - 1) // page_size)
            page = min(page, max_page)

            text = f"✅ Канал {username} удалён из ваших подписок.\n\nВыберите канал для удаления:"
            kb = build_delete_kb(channels, page=page)
            await cb.message.edit_text(text, reply_markup=kb)
            await cb.answer()
            return
        if callback_data.action == "all":
            await delete_all_channels(cb.from_user.id)
            await cb.message.edit_text("✅ Все каналы удалены.\n\nТеперь список пуст.")
            await cb.answer()
            return

        await cb.answer("Неизвестное действие", show_alert=True)

    @dp.callback_query(VipCb.filter())
    async def cb_vip(cb: CallbackQuery, callback_data: VipCb):
        if callback_data.action == "plan" and callback_data.plan:
            tariff = get_tariff(callback_data.plan)
            text = (
                f"Вы выбрали подписку на {tariff['title']}. "
                "Выберите способ оплаты:"
            )
            await cb.message.edit_text(
                text,
                reply_markup=build_vip_payment_kb(callback_data.plan),
            )
            await cb.answer()
            return

        if callback_data.action == "back_pay" and callback_data.plan:
            tariff = get_tariff(callback_data.plan)
            text = (
                f"Вы выбрали подписку на {tariff['title']}. "
                "Выберите способ оплаты:"
            )
            try:
                await cb.message.edit_text(
                    text,
                    reply_markup=build_vip_payment_kb(callback_data.plan),
                )
            except TelegramBadRequest:
                await cb.message.answer(
                    text,
                    reply_markup=build_vip_payment_kb(callback_data.plan),
                )
                try:
                    await cb.message.delete()
                except Exception:
                    pass
            await cb.answer()
            return

        if callback_data.action == "back":
            status = await get_vip_status(cb.from_user.id)
            text = build_vip_screen_text(status.get("vip_until"))
            await cb.message.edit_text(text, reply_markup=build_vip_tariffs_kb())
            await cb.answer()
            return

        if callback_data.action == "pay_card" and callback_data.plan:
            plan = callback_data.plan
            try:
                payment_id, confirmation = await yk_create_payment(cb.from_user.id, plan)
                confirmation_url = confirmation.get("confirmation_url")
                if not confirmation_url:
                    raise RuntimeError("Не удалось получить ссылку на оплату.")
            except Exception as e:
                await cb.message.edit_text(f"❌ Не удалось создать платёж: {e}")
                await cb.answer()
                return

            card_payments[(cb.from_user.id, plan)] = payment_id
            tariff = get_tariff(plan)
            kb = [
                [InlineKeyboardButton(text=f"💳 Оплатить {tariff['price']}₽", url=confirmation_url)],
                [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=VipCb(action="check_card", plan=plan).pack())],
                [InlineKeyboardButton(text="← Назад", callback_data=VipCb(action="back_pay", plan=plan).pack())],
            ]
            await cb.message.edit_text(
                text="Нажмите «Оплатить», завершите оплату и затем вернитесь сюда и нажмите «Проверить оплату».",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            )
            await cb.answer()
            return

        if callback_data.action == "pay_qr" and callback_data.plan:
            plan = callback_data.plan
            try:
                payment_id, confirmation = await yk_create_payment(
                    cb.from_user.id,
                    plan,
                    confirmation_type="qr",
                    payment_method_data={"type": "sbp"},
                )
            except YkBadRequestError as e:
                await cb.message.edit_text(
                    "❌ Не удалось создать платёж СБП. Проверьте, что СБП включён в YooKassa "
                    "и доступен для вашего магазина.\n\n"
                    f"Техническая ошибка: {e}"
                )
                await cb.answer()
                return
            except Exception as e:
                await cb.message.edit_text(f"❌ Не удалось создать платёж: {e}")
                await cb.answer()
                return

            confirmation_url = confirmation.get("confirmation_url")
            confirmation_data = confirmation.get("confirmation_data")
            if not confirmation_url and not confirmation_data:
                await cb.message.edit_text("❌ Не удалось получить данные для оплаты по СБП.")
                await cb.answer()
                return
            qr_payments[(cb.from_user.id, plan)] = payment_id
            tariff = get_tariff(plan)
            kb = [
                [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=VipCb(action="check_qr", plan=plan).pack())],
                [InlineKeyboardButton(text="← Назад", callback_data=VipCb(action="back_pay", plan=plan).pack())],
            ]
            if confirmation_url:
                kb.insert(0, [InlineKeyboardButton(text="💠 Оплатить по СБП", url=confirmation_url)])
                await cb.message.edit_text(
                    text=(
                        "Нажмите «Оплатить», завершите оплату по СБП и затем вернитесь сюда и "
                        "нажмите «Проверить оплату»."
                    ),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
                    disable_web_page_preview=True,
                )
            else:
                qr = qrcode.QRCode(border=2, box_size=6)
                qr.add_data(confirmation_data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buf = BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                await cb.message.answer_photo(
                    BufferedInputFile(buf.getvalue(), filename="sbp_qr.png"),
                    caption=f"Отсканируйте QR для оплаты {tariff['price']}₽ по СБП.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
                )
                try:
                    await cb.message.delete()
                except Exception:
                    pass
            await cb.answer()
            return


        if callback_data.action == "pay_stars" and callback_data.plan:
            tariff = get_tariff(callback_data.plan)

            provider_token = os.getenv("STARS_PROVIDER_TOKEN", "STARS")
            payload = f"vip:{callback_data.plan}:{uuid.uuid4()}"
            stars_payloads[payload] = callback_data.plan
            stars_last_plan[cb.from_user.id] = callback_data.plan

            try:
                invoice_url = await cb.bot.create_invoice_link(
                    title="VIP-подписка",
                    description=f"VIP на {tariff['title']}",
                    payload=payload,
                    provider_token=provider_token,
                    currency="XTR",
                    prices=[LabeledPrice(label=tariff["title"], amount=tariff["stars"])],
                )
            except Exception as e:
                await cb.message.edit_text(f"❌ Не удалось подготовить оплату Stars: {e}")
                await cb.answer()
                return

            text = (
                "Стоимость премиума:\n"
                f"~{tariff['price']}₽ / $1.99 или {tariff['stars']} Telegram Stars за {tariff['title']}\n\n"
                "🚨 Если вы из России, вы можете купить Stars на 40% дешевле в официальном боте "
                "Телеграма: @premiumbot"
            )

            await cb.message.edit_text(
                text,
                reply_markup=build_vip_stars_kb(callback_data.plan, invoice_url=invoice_url),
                disable_web_page_preview=True,
            )
            await cb.answer()
            return

        if callback_data.action == "check_card" and callback_data.plan:
            plan = callback_data.plan
            payment_id = card_payments.get((cb.from_user.id, plan))
            if not payment_id:
                await cb.answer("Платёж не найден. Нажмите «Оплатить» ещё раз.", show_alert=True)
                return

            try:
                status = await yk_check_payment(payment_id)
            except Exception as e:
                await cb.answer(f"❌ Ошибка проверки: {e}", show_alert=True)
                return

            if status == "succeeded":
                tariff = get_tariff(plan)
                days = get_tariff_days(plan, tariff)
                if not days:
                    await cb.message.edit_text("⚠️ Не удалось активировать VIP: отсутствует срок тарифа.")
                    return
                vip_res = await extend_vip(cb.from_user.id, int(days))
                vip_date = format_vip_until(vip_res.get("vip_until"))
                if vip_date:
                    await cb.message.edit_text(f"✅ Оплата прошла успешно. Подписка активна до {vip_date}.")
                else:
                    await cb.message.edit_text("✅ Оплата прошла успешно. Доступ к VIP включён.")
            else:
                await cb.answer("⏳ Платёж ещё не завершён. Попробуйте позже.", show_alert=True)
            return

        if callback_data.action == "check_qr" and callback_data.plan:
            plan = callback_data.plan
            payment_id = qr_payments.get((cb.from_user.id, plan))
            if not payment_id:
                await cb.answer("Платёж не найден. Попробуйте создать QR ещё раз.", show_alert=True)
                return
            try:
                status = await yk_check_payment(payment_id)
            except Exception as e:
                await cb.answer(f"❌ Ошибка проверки: {e}", show_alert=True)
                return

            if status == "succeeded":
                tariff = get_tariff(plan)
                days = get_tariff_days(plan, tariff)
                if not days:
                    await cb.message.answer("⚠️ Не удалось активировать VIP: отсутствует срок тарифа.")
                    return
                vip_res = await extend_vip(cb.from_user.id, int(days))
                vip_date = format_vip_until(vip_res.get("vip_until"))
                if vip_date:
                    await cb.message.answer(f"✅ Оплата прошла успешно. Подписка активна до {vip_date}.")
                else:
                    await cb.message.answer("✅ Оплата прошла успешно. Доступ к VIP включён.")
            else:
                await cb.answer("⏳ Платёж ещё не завершён. Попробуйте позже.", show_alert=True)
            return

        await cb.answer("Неизвестное действие", show_alert=True)

    @dp.pre_checkout_query()
    async def pre_checkout_query(pre_checkout: PreCheckoutQuery):
        await pre_checkout.answer(ok=True)

    @dp.message(F.successful_payment)
    async def on_successful_payment(msg: Message):
        payload = msg.successful_payment.invoice_payload
        plan = None
        if payload.startswith("vip:"):
            parts = payload.split(":")
            if len(parts) >= 2:
                plan = parts[1]
        if not plan:
            plan = stars_payloads.get(payload) or stars_last_plan.get(msg.from_user.id)
        if plan:
            tariff = get_tariff(plan)
            days = get_tariff_days(plan, tariff)
            if not days:
                await msg.answer("⚠️ Не удалось активировать VIP: отсутствует срок тарифа.")
                return
            vip_res = await extend_vip(msg.from_user.id, int(days))
            text = build_vip_screen_text(vip_res.get("vip_until"))
            await msg.answer(text, reply_markup=build_vip_tariffs_kb())
            return
        await msg.answer("✅ Оплата прошла успешно. Доступ к VIP включён.")



    await dp.start_polling(bot)
    

if __name__ == "__main__":
    asyncio.run(main())
