import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, BotCommand
from bot.api_client import add_channel, list_channels
from bot.parsers import extract_channels
from aiogram.types import CallbackQuery
from bot.keyboards.subscriptions import build_subscriptions_kb
from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from bot.feed_worker import feed_loop

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
        parts = (msg.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await msg.answer("Формат: /delete @channel")
            return
        await msg.answer("Удаление сделаем следующим шагом (нужен endpoint в API).")

    @dp.message(Command("start"))
    async def cmd_start_forward(msg: Message):
        await msg.answer("Ок Пересылка будет реализована после подключения collector-а.")

    @dp.message(Command("stop"))
    async def cmd_stop_forward(msg: Message):
        await msg.answer("Ок  Пересылка будет реализована после подключения collector-а.")

    @dp.message(Command("digest"))
    async def cmd_digest(msg: Message):
        await msg.answer("Сводка пока не готова. Сначала подключим сбор постов и обработку.")

    @dp.message(Command("spam"))
    async def cmd_spam(msg: Message):
        await msg.answer("Фильтр рекламы сделаем после появления постов (нужны данные).")

    @dp.message(Command("switch_feed"))
    async def cmd_switch_feed(msg: Message):
        await msg.answer("Переключение ленты сделаем после MVP дайджеста.")

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

    await dp.start_polling(bot)
    
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

if __name__ == "__main__":
    asyncio.run(main())
