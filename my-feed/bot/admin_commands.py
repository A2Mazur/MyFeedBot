from datetime import datetime

from aiogram.filters import Command
from aiogram.types import Message

from bot.api_client import get_admin_stats, admin_grant_vip, admin_revoke_vip, resolve_user_id, get_broadcast_targets


def _format_date(iso_value: str | None) -> str:
    if not iso_value:
        return ""
    try:
        dt = datetime.fromisoformat(iso_value)
        return dt.strftime("%d.%m.%Y")
    except ValueError:
        return iso_value


async def _resolve_user_id(msg: Message, raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    if not raw.startswith("@"):
        raw = f"@{raw}"
    resolved = await resolve_user_id(raw)
    if resolved:
        return int(resolved)
    try:
        chat = await msg.bot.get_chat(raw)
        return int(chat.id)
    except Exception:
        return None


def register_admin_commands(dp, owner_tg_user_id: int) -> None:
    @dp.message(Command("users"))
    async def cmd_users(msg: Message):
        if msg.from_user.id != owner_tg_user_id:
            await msg.answer("⛔ Команда доступна только администратору.")
            return
        stats = await get_admin_stats(msg.from_user.id)
        lines = [
            "МОЯ ЛЕНТА | Персональные новости",
            "",
            f"👥 Всего пользователей: {stats.get('users_total', 0)}",
            f"📬 Доставку включили: {stats.get('forwarding_on', 0)}",
            f"⚡ Fast-feed: {stats.get('short_feed_on', 0)}  •  🚫 Anti-spam: {stats.get('spam_filter_on', 0)}",
            f"💎 Активных VIP: {stats.get('vip_active', 0)}  (⏳ истечёт ≤7д: {stats.get('vip_expiring_7d', 0)})",
            "",
            f"🔗 Подписок всего: {stats.get('channels_total', 0)}",
            "",
            f"📊 Активность за 7 дней: {stats.get('posts_7d', 0)} постов / {stats.get('active_users_7d', 0)} активных юзеров",
        ]
        top_activity = stats.get("top_activity_7d", [])
        if top_activity:
            lines.append("🏆 Топ-10 по активности (7д):")
            for row in top_activity:
                lines.append(f"— {row.get('user_id')}: {row.get('count')} пост(ов)")
        top_channels = stats.get("top_channels", [])
        if top_channels:
            lines.append("")
            lines.append("🏅 Топ-10 по числу подписок:")
            for row in top_channels:
                lines.append(f"— {row.get('user_id')}: {row.get('count')} канал(ов)")
        await msg.answer("\n".join(lines))

    @dp.message(Command("grant_vip"))
    async def cmd_grant_vip(msg: Message):
        if msg.from_user.id != owner_tg_user_id:
            await msg.answer("⛔ Команда доступна только администратору.")
            return
        parts = (msg.text or "").split()
        if len(parts) < 3:
            await msg.answer("Использование: /grant_vip user_id|@username <days|forever>")
            return
        target = await _resolve_user_id(msg, parts[1])
        if not target:
            await msg.answer("Не удалось найти пользователя. Убедись, что он писал боту.")
            return
        arg = parts[2].lower()
        if arg == "forever":
            res = await admin_grant_vip(msg.from_user.id, target, forever=True)
            vip_date = _format_date(res.get("vip_until"))
            await msg.answer(f"✅ VIP выдан навсегда. Активен до {vip_date}")
            try:
                await msg.bot.send_message(
                    target,
                    f"🎁 Вам подарили VIP-доступ! Подписка активна до {vip_date}.",
                )
            except Exception:
                pass
            return
        if not arg.isdigit():
            await msg.answer("Неверный формат дней. Пример: /grant_vip @user 30")
            return
        days = int(arg)
        res = await admin_grant_vip(msg.from_user.id, target, days=days)
        vip_date = _format_date(res.get("vip_until"))
        await msg.answer(f"✅ VIP выдан на {days} дней. Активен до {vip_date}")
        try:
            await msg.bot.send_message(
                target,
                f"🎁 Вам подарили VIP-доступ на {days} дней! Подписка активна до {vip_date}.",
            )
        except Exception:
            pass

    @dp.message(Command("revoke_vip"))
    async def cmd_revoke_vip(msg: Message):
        if msg.from_user.id != owner_tg_user_id:
            await msg.answer("⛔ Команда доступна только администратору.")
            return
        parts = (msg.text or "").split()
        if len(parts) < 2:
            await msg.answer("Использование: /revoke_vip user_id|@username")
            return
        target = await _resolve_user_id(msg, parts[1])
        if not target:
            await msg.answer("Не удалось найти пользователя. Убедись, что он писал боту.")
            return
        res = await admin_revoke_vip(msg.from_user.id, target)
        if res.get("revoked"):
            await msg.answer("✅ VIP снят.")
        else:
            await msg.answer("ℹ️ Пользователь не найден или VIP уже не активен.")

    @dp.message(Command("broadcast"))
    async def cmd_broadcast(msg: Message):
        if msg.from_user.id != owner_tg_user_id:
            await msg.answer("⛔ Команда доступна только администратору.")
            return

        parts = (msg.text or "").split(maxsplit=2)
        group = "all"
        text = None
        if len(parts) >= 2 and parts[1] in {"vip", "free", "active"}:
            group = parts[1]
            if len(parts) == 3:
                text = parts[2]
        elif len(parts) == 2:
            text = parts[1]

        if not text and not msg.reply_to_message:
            await msg.answer("Использование: /broadcast [vip|free|active] <текст> или ответом на сообщение.")
            return

        targets = await get_broadcast_targets(msg.from_user.id, group=group)
        if not targets:
            await msg.answer("Нет получателей для рассылки.")
            return

        sent = 0
        failed = 0
        for uid in targets:
            try:
                if text:
                    await msg.bot.send_message(uid, text)
                else:
                    await msg.reply_to_message.copy_to(uid)
                sent += 1
            except Exception:
                failed += 1
        await msg.answer(f"✅ Рассылка завершена. Успешно: {sent}, ошибок: {failed}.")
