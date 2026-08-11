"""
Модуль диспетчера инлайн-навигации (обработка нажатий на кнопки).

Каждая кнопка перехода (callback_data вида "nav:...") редактирует уже
существующее сообщение вместо отправки нового — поэтому переписка в
ЛС не растёт при обычной навигации по меню (в отличие от команд,
которые всё ещё создают новое сообщение и полагаются на
самоочистку — см. private_chat.py).

ВАЖНО: то, что кнопка не показана пользователю — не является защитой
доступа сама по себе. Обработчик здесь заново проверяет права
(is_admin/OWNER_ID) для каждого действия, точно так же, как это уже
делают сами команды — подделанный или переигранный callback_data не
должен давать доступ к тому, что человеку не положено видеть.
"""

import logging

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
from telegram.ext._utils.types import BD

from config import LOG_ENCODING, LOG_FORMAT, LOG_LEVEL, OWNER_ID
from handlers.admin import get_admin_list_lines
from handlers.profile import get_cached_profile, get_cached_top_users
from handlers.screens import (
    render_admins_screen,
    render_entrance_hall,
    render_profile_screen,
    render_target_profile_screen,
    render_top_screen,
)

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/navigation.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


async def handle_navigation_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Единая точка входа для всех кнопок навигации (callback_data,
    начинающийся с "nav:"). Разбирает callback_data и вызывает
    соответствующий экран, редактируя текущее сообщение.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    query = update.callback_query
    user = update.effective_user
    action = query.data if query else None

    bot_instance = context.bot_data.get("bot_instance")
    if not bot_instance or not query:
        if query:
            await query.answer("Произошла ошибка. Попробуйте позже.")
        return

    db = bot_instance.db

    # "nav:home" -> base="home", target_id=None
    # "nav:target_profile:123" -> base="target_profile", target_id=123
    parts = (action or "").split(":")
    base = parts[1] if len(parts) > 1 else None
    target_id = None
    if len(parts) > 2 and parts[2].lstrip("-").isdigit():
        target_id = int(parts[2])

    # Заполняется только тем действиям, которым нужно показать
    # собственный toast-текст (например, подтверждение сброса
    # таймера) — иначе используется обычный пустой query.answer().
    answer_text = None

    try:
        is_owner = user.id == OWNER_ID
        is_admin = db.is_admin(user.id)
        can_manage = is_owner or is_admin

        if base == "home":
            text, keyboard = render_entrance_hall(is_owner, is_admin)

        elif base == "profile":
            profile = await get_cached_profile(user.id, db, is_owner=can_manage)
            if not profile:
                await query.answer("Профиль не найден. Напишите /start.")
                return
            text, keyboard = render_profile_screen(profile, bot_instance.rank_system)

        elif base == "top":
            top_users = await get_cached_top_users(db, can_manage)
            text, keyboard = render_top_screen(top_users, can_view_profiles=can_manage)

        elif base == "admins":
            # Кнопка скрыта от обычных участников в render_entrance_hall,
            # но, как отмечено в docstring модуля, это не защита доступа
            # сама по себе — переигранный/подделанный callback_data не
            # должен давать доступ тому, кому не положено.
            if not can_manage:
                await query.answer(
                    "❌ У вас нет прав для просмотра списка администраторов.",
                    show_alert=True,
                )
                return
            admin_lines = get_admin_list_lines(db)
            text, keyboard = render_admins_screen(admin_lines)

        elif base == "target_profile" and target_id is not None:
            # Доступно только с экрана "Топ" для админов/владельца
            # (см. render_top_screen), но, как и везде здесь, права
            # перепроверяются заново, а не наследуются от того, что
            # кнопка была видна.
            if not can_manage:
                await query.answer(
                    "❌ У вас нет прав для просмотра чужих профилей.",
                    show_alert=True,
                )
                return
            target_user = db.get_user(target_id)
            if not target_user:
                await query.answer("Пользователь не найден.")
                return
            text, keyboard = render_target_profile_screen(target_user)

        elif base == "reset" and target_id is not None:
            if not can_manage:
                await query.answer(
                    "❌ У вас нет прав для использования этой команды.",
                    show_alert=True,
                )
                return
            target_user = db.get_user(target_id)
            if not target_user:
                await query.answer("Пользователь не найден.")
                return

            success = db.reset_inactivity_timer(target_id)
            if not success:
                await query.answer("❌ Ошибка при сбросе таймера неактивности.")
                return

            username = target_user["username"] or f"user{target_id}"
            answer_text = f"✅ Таймер неактивности для @{username} сброшен."

            # Перечитываем пользователя, чтобы экран сразу показал
            # обновлённое время последней активности, а не устаревшее.
            target_user = db.get_user(target_id)
            text, keyboard = render_target_profile_screen(target_user)

            logger.info(
                f"Inactivity timer reset via button: admin_id={user.id}, "
                f"target_user_id={target_id}"
            )

        else:
            logger.warning(f"Unknown navigation callback_data: {action!r}")
            await query.answer("Неизвестное действие.")
            return

        if answer_text:
            await query.answer(answer_text)
        else:
            await query.answer()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

        logger.info(f"Navigation '{action}' rendered for user_id={user.id}")

    except Exception as e:
        logger.error(
            f"Error handling navigation callback {action!r} for "
            f"user_id={getattr(user, 'id', 'unknown')}: {e}",
            exc_info=True,
        )
        try:
            await query.answer("Произошла ошибка. Попробуйте позже.")
        except Exception:
            pass


def register_handlers(application: Application, bot_instance: BD) -> None:
    """
    Эта функция осуществляет регистрацию обработчика нажатий на
    инлайн-кнопки навигации (callback_data, начинающийся с "nav:").
    Args:
        application (Application): Экземпляр приложения.
        bot_instance (BD): Экземпляр бота.
    """
    application.bot_data["bot_instance"] = bot_instance

    application.add_handler(
        CallbackQueryHandler(handle_navigation_callback, pattern=r"^nav:")
    )

    logger.info("Navigation handlers registered successfully")
