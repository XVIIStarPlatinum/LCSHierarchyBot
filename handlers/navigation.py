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
from handlers.profile import get_cached_profile, get_cached_top_users
from handlers.screens import (
    render_entrance_hall,
    render_profile_screen,
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

    try:
        is_owner = user.id == OWNER_ID
        is_admin = db.is_admin(user.id)

        if action == "nav:home":
            text, keyboard = render_entrance_hall(is_owner, is_admin)

        elif action == "nav:profile":
            profile = await get_cached_profile(
                user.id, db, is_owner=is_admin or is_owner
            )
            if not profile:
                await query.answer("Профиль не найден. Напишите /start.")
                return
            text, keyboard = render_profile_screen(profile, bot_instance.rank_system)

        elif action == "nav:top":
            top_users = await get_cached_top_users(db, is_admin or is_owner)
            text, keyboard = render_top_screen(top_users)

        else:
            logger.warning(f"Unknown navigation callback_data: {action!r}")
            await query.answer("Неизвестное действие.")
            return

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
