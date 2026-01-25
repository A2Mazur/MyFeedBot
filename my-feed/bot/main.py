import asyncio
import logging
import os
from bot.keyboards.delete import build_delete_kb, DelCb

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, BotCommand
from bot.api_client import add_channel, list_channels, delete_channel, delete_all_channels, set_forwarding, get_forwarding, get_latest_posts, get_spam_filter, set_spam_filter, get_short_feed, set_short_feed
from bot.parsers import extract_channels
from aiogram.types import CallbackQuery
from bot.keyboards.subscriptions import build_subscriptions_kb
from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from bot.feed_worker import feed_loop
from bot.digest import select_recent_posts, generate_digest

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
        await set_forwarding(user_id, True)
        await msg.answer("Пересылка сообщений активирована ✅")

    @dp.message(Command("stop"))
    async def cmd_stop_forward(msg: Message):
        user_id = msg.from_user.id
        await set_forwarding(user_id, False)
        await msg.answer("Пересылка сообщений остановлена ⛔️")


    @dp.message(Command("digest"))
    async def cmd_digest(msg: Message):
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
        await msg.answer("VIP/оплата будет позже (после MVP).")

    @dp.message()
    async def any_text(msg: Message):
        text = msg.text or ""
        channels = extract_channels(text)

        if not channels:
            await msg.answer("Не вижу ссылок/username. Пришли, например: @durov или https://t.me/durov")
            return

        added = 0
        already = 0
        errors = 0

        for ch in channels:
            try:
                res = await add_channel(msg.from_user.id, ch)
                if res.get("message") == "already added":
                    already += 1
                else:
                    added += 1
            except Exception:
                errors += 1

        reply = []
        if added:
            reply.append(f"Добавлено ✅: {added}")
        if already:
            reply.append(f"Уже было 👍: {already}")
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



    await dp.start_polling(bot)
    

if __name__ == "__main__":
    asyncio.run(main())
