import logging
import re
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.ext._utils.types import BD

from config import (
    CHAT_ID,
    LOG_ENCODING,
    LOG_FORMAT,
    LOG_LEVEL,
    OWNER_ID,
    TOPIC_ID,
    TOPIC_IMPORTANT_ID,
)

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/admin.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


async def handle_add_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку команды `/add`.
    Доступно админам и владельцу. Добавляет/убавляет баллы указанному пользователю.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message

    # Проверка что команда в ЛС
    if message.chat.type != "private":
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db
    rank_system = bot_instance.rank_system

    # Проверка прав
    if user.id != OWNER_ID and not db.is_admin(user.id):
        await message.reply_text("❌ У вас нет прав для использования этой команды.")
        return

    # Проверка аргументов
    if len(context.args) < 3:
        await message.reply_text(
            "❌ Неверный формат команды.\n"
            "Используйте: /add @username <баллы> причина: <текст>"
        )
        return

    # Парсинг аргументов
    username_arg = context.args[0]
    points_arg = context.args[1]
    reason_start = 2

    # Обработка username с @
    username = username_arg.lstrip("@")

    # Поиск пользователя в базе данных
    target_user = db.get_user_by_username(username)

    if not target_user:
        await message.reply_text(
            f"❌ Пользователь @{username} не найден в базе данных."
        )
        return

    # Парсинг баллов
    try:
        points = float(points_arg)
    except ValueError:
        await message.reply_text(
            "❌ Неверный формат баллов. Используйте число (например, 10 или -5.5)"
        )
        return

    # Парсинг причины
    if (
        context.args[reason_start].lower() == "причина:"
        and len(context.args) > reason_start + 1
    ):
        reason = " ".join(context.args[reason_start + 1 :])
    else:
        reason = " ".join(context.args[reason_start:])

    if not reason.strip():
        await message.reply_text("❌ Укажите причину изменения баллов.")
        return

    # Обновление баллов
    try:
        success = db.add_points_manually(
            target_user["user_id"], points, user.id, reason
        )
        if not success:
            await message.reply_text("❌ Ошибка при обновлении баллов пользователя.")
            return

        # Обновление ранга если необходимо
        if points > 0:
            rank_system.update_user_rank(target_user["user_id"])

        # Формирование ответа админу
        action = "выдано" if points > 0 else "снято"
        points_str = f"+{points}" if points > 0 else str(points)

        await message.reply_text(
            f"✅ {action.capitalize()} {points_str} баллов для @{username}.\n"
            f"Причина: {reason}"
        )

        logger.info(
            f"Points manually adjusted: admin_id={user.id}, "
            f"target_user_id={target_user['user_id']}, "
            f"points={points}, reason='{reason}'"
        )

        # Отправка уведомления в топике "Основной чат"
        try:
            admin_mention = f"@{user.username}" if user.username else user.first_name
            target_mention = (
                f"@{target_user['username']}"
                if target_user["username"]
                else f"user{target_user['user_id']}"
            )

            notification_text = (
                f"🏆 <b>Административное действие</b>\n\n"
                f"Админ {admin_mention} выдал {target_mention}-у"
                f" {points_str} баллов.\n"
                f"Причина: {reason}"
            )

            await context.bot.send_message(
                chat_id=CHAT_ID,
                message_thread_id=TOPIC_ID,  # Основной чат
                text=notification_text,
                parse_mode="HTML",
            )

        except Exception as e:
            logger.error(f"Failed to send admin notification to main chat: {e}")

    except Exception as e:
        logger.error(f"Error in /add command: {e}")
        await message.reply_text(
            "❌ Произошла ошибка при выполнении команды. Обратитесь к владельцу."
        )


async def handle_legend_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку команды `/legend`.
    Доступно только владельцу. Присваивает ранг "Легенда".
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message

    # Проверка что команда в ЛС
    if message.chat.type != "private":
        return

    # Проверка прав (только владелец)
    if user.id != OWNER_ID:
        await message.reply_text("❌ Эта команда доступна только владельцу сообщества.")
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db
    rank_system = bot_instance.rank_system

    # Проверка аргументов
    if len(context.args) < 1:
        await message.reply_text("❌ Укажите пользователя: /legend @username")
        return

    # Парсинг username
    username_arg = context.args[0]
    username = username_arg.lstrip("@")

    # Поиск пользователя
    target_user = db.get_user_by_username(username)

    if not target_user:
        await message.reply_text(f"❌ Пользователь @{username} не найден.")
        return

    # Присвоение ранга "Легенда"
    try:
        success = await rank_system.set_legend_rank(
            target_user["user_id"], OWNER_ID, context
        )
        if not success:
            await message.reply_text("❌ Ошибка при присвоении ранга 'Легенда'.")
            return

        # Ответ владельцу
        await message.reply_text(
            f"✅ Ранг 'Легенда' успешно присвоен пользователю @{username}."
        )

        logger.info(
            f"Legend rank assigned: owner_id={OWNER_ID}, "
            f"target_user_id={target_user['user_id']}, username={username}"
        )

    except Exception as e:
        logger.error(f"Error in /legend command: {e}")
        await message.reply_text("❌ Произошла ошибка при выполнении команды.")


async def handle_unlegend_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку команды `/unlegend`.
    Доступно только владельцу. Снимает ранг "Легенда".
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message

    # Проверка что команда в ЛС
    if message.chat.type != "private":
        return

    # Проверка прав (только владелец)
    if user.id != OWNER_ID:
        await message.reply_text("❌ Эта команда доступна только владельцу сообщества.")
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db
    rank_system = bot_instance.rank_system

    # Проверка аргументов
    if len(context.args) < 1:
        await message.reply_text("❌ Укажите пользователя: /unlegend @username")
        return

    # Парсинг username
    username_arg = context.args[0]
    username = username_arg.lstrip("@")

    # Поиск пользователя
    target_user = db.get_user_by_username(username)

    if not target_user:
        await message.reply_text(f"❌ Пользователь @{username} не найден.")
        return

    # Проверка текущего ранга
    if target_user["rank"] != "Легенда":
        await message.reply_text(
            f"❌ Пользователь @{username} не имеет ранга 'Легенда'."
        )
        return

    # Снятие ранга "Легенда"
    try:
        success = await rank_system.unset_legend_rank(
            target_user["user_id"], OWNER_ID, context
        )
        if not success:
            await message.reply_text("❌ Ошибка при снятии ранга 'Легенда'.")
            return

        # Ответ владельцу
        await message.reply_text(
            f"✅ Ранг 'Легенда' успешно снят с пользователя @{username}."
        )

        logger.info(
            f"Legend rank removed: owner_id={OWNER_ID}, "
            f"target_user_id={target_user['user_id']}, username={username}"
        )

    except Exception as e:
        logger.error(f"Error in /unlegend command: {e}")
        await message.reply_text("❌ Произошла ошибка при выполнении команды.")


async def handle_setadmin_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку команды `/setadmin`.
    Доступно только владельцу. Назначает пользователя администратором бота.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message

    # Проверка что команда в ЛС
    if message.chat.type != "private":
        return

    # Проверка прав (только владелец)
    if user.id != OWNER_ID:
        await message.reply_text("❌ Эта команда доступна только владельцу сообщества.")
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db

    # Проверка аргументов
    if len(context.args) < 1:
        await message.reply_text("❌ Укажите пользователя: /setadmin @username")
        return

    # Парсинг username
    username_arg = context.args[0]
    username = username_arg.lstrip("@")

    # Поиск пользователя
    target_user = db.get_user_by_username(username)

    if not target_user:
        await message.reply_text(f"❌ Пользователь @{username} не найден.")
        return

    # Проверка, не является ли пользователь уже админом
    if db.is_admin(target_user["user_id"]):
        await message.reply_text(
            f"❌ Пользователь @{username} уже является администратором."
        )
        return

    # Назначение администратора
    try:
        success = db.add_admin(target_user["user_id"], username)
        if not success:
            await message.reply_text("❌ Ошибка при назначении администратора.")
            return

        # Ответ владельцу
        await message.reply_text(
            f"✅ Пользователь @{username} успешно назначен администратором."
        )

        # Отправка уведомления в топике "ВАЖНОЕ"
        try:
            notification_text = (
                f"🚀 @{username} стал администратором! "
                "Обращайтесь к нему за помощью и идеями в ЛС!"
            )

            await context.bot.send_message(
                chat_id=CHAT_ID,
                message_thread_id=TOPIC_IMPORTANT_ID,
                text=notification_text,
                parse_mode="HTML",
            )

            logger.info(
                f"Admin assigned: owner_id={OWNER_ID}, "
                f"new_admin_id={target_user['user_id']}, username={username}"
            )

        except Exception as e:
            logger.error(f"Failed to send admin notification to IMPORTANT topic: {e}")

    except Exception as e:
        logger.error(f"Error in /setadmin command: {e}")
        await message.reply_text("❌ Произошла ошибка при выполнении команды.")


async def handle_unsetadmin_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку команды `/unsetadmin`.
    Доступно только владельцу. Снимает админ-права.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message

    # Проверка что команда в ЛС
    if message.chat.type != "private":
        return

    # Проверка прав (только владелец)
    if user.id != OWNER_ID:
        await message.reply_text("❌ Эта команда доступна только владельцу сообщества.")
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db

    # Проверка аргументов
    if len(context.args) < 1:
        await message.reply_text("❌ Укажите пользователя: /unsetadmin @username")
        return

    # Парсинг username
    username_arg = context.args[0]
    username = username_arg.lstrip("@")

    # Поиск пользователя
    target_user = db.get_user_by_username(username)

    if not target_user:
        await message.reply_text(f"❌ Пользователь @{username} не найден.")
        return

    # Проверка, является ли пользователь админом
    if not db.is_admin(target_user["user_id"]):
        await message.reply_text(
            f"❌ Пользователь @{username} не является администратором."
        )
        return

    # Проверка, не является ли пользователь владельцем
    if target_user["user_id"] == OWNER_ID:
        await message.reply_text("❌ Нельзя снять права с владельца сообщества.")
        return

    # Снятие админ-прав
    try:
        success = db.remove_admin(target_user["user_id"], username)
        if not success:
            await message.reply_text("❌ Ошибка при снятии прав администратора.")
            return

        # Ответ владельцу
        await message.reply_text(
            f"✅ Права администратора успешно сняты с пользователя @{username}."
        )

        # Отправка уведомления в топике "ВАЖНОЕ"
        try:
            notification_text = (
                f"📢 @{username} больше не администратор. Спасибо за их вклад!"
            )

            await context.bot.send_message(
                chat_id=CHAT_ID,
                message_thread_id=TOPIC_IMPORTANT_ID,
                text=notification_text,
                parse_mode="HTML",
            )

            logger.info(
                f"Admin rights removed: owner_id={OWNER_ID}, "
                f"former_admin_id={target_user['user_id']}, "
                f"username={username}"
            )

        except Exception as e:
            logger.error(
                f"Failed to send unset admin notification to IMPORTANT topic: {e}"
            )

    except Exception as e:
        logger.error(f"Error in /unsetadmin command: {e}")
        await message.reply_text("❌ Произошла ошибка при выполнении команды.")


async def handle_admins_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку команды `/admins`.
    Показывает список администраторов бота (включая владельца).
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message

    # Проверка что команда в ЛС
    if message.chat.type != "private":
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db

    # Проверка прав (админы и владелец)
    if user.id != OWNER_ID and not db.is_admin(user.id):
        await message.reply_text(
            "❌ У вас нет прав для просмотра списка администраторов."
        )
        return

    try:
        admins = db.get_all_admins()
        owner_info = db.get_user(OWNER_ID)

        if not admins and not owner_info:
            await message.reply_text("👥 Администраторы не найдены.")
            return

        # Формирование списка админов
        admin_list = []

        # Добавление владельца
        if owner_info:
            owner_username = owner_info["username"] or "ViceMGMT"
            admin_list.append(f"👑 @{owner_username} (владелец)")

        # Добавление админов
        for admin in admins:
            admin_username = admin["username"] or f"user{admin['user_id']}"
            if (
                admin["user_id"] != OWNER_ID
            ):  # Исключаем владельца если он в таблице admins
                admin_list.append(f"👮 @{admin_username}")

        if not admin_list:
            admin_list.append("Нет администраторов")

        # Формирование ответа
        response_text = "👥 <b>Администраторы:</b>\n" + "\n".join(admin_list)

        await message.reply_text(response_text, parse_mode="HTML")

        logger.info(f"Admins list shown to user_id={user.id}")

    except Exception as e:
        logger.error(f"Error in /admins command: {e}")
        await message.reply_text(
            "❌ Произошла ошибка при получении списка администраторов."
        )


async def handle_reset_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку команды `/reset`.
    Сбрасывает таймер неактивности для пользователя.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message

    # Проверка что команда в ЛС
    if message.chat.type != "private":
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db

    # Проверка прав (админы и владелец)
    if user.id != OWNER_ID and not db.is_admin(user.id):
        await message.reply_text("❌ У вас нет прав для использования этой команды.")
        return

    # Проверка аргументов
    if len(context.args) < 1:
        await message.reply_text("❌ Укажите пользователя: /reset @username")
        return

    # Парсинг username
    username_arg = context.args[0]
    username = username_arg.lstrip("@")

    # Поиск пользователя
    target_user = db.get_user_by_username(username)

    if not target_user:
        await message.reply_text(f"❌ Пользователь @{username} не найден.")
        return

    # Сброс таймера неактивности
    try:
        # Обновление времени последней активности
        success = db.reset_inactivity_timer(target_user["user_id"])
        if not success:
            await message.reply_text("❌ Ошибка при сбросе таймера неактивности.")
            return

        # Ответ админу
        await message.reply_text(
            f"✅ Таймер неактивности для @{username} успешно сброшен."
        )

        logger.info(
            f"Inactivity timer reset: admin_id={user.id}, "
            f"target_user_id={target_user['user_id']}, "
            f"username={username}"
        )

    except Exception as e:
        logger.error(f"Error in /reset command: {e}")
        await message.reply_text("❌ Произошла ошибка при выполнении команды.")


async def handle_user_profile_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку команды `/@{username}`.
    Показывает профиль указанного пользователя (аналог `/profile`).
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message

    # Проверка что команда в ЛС
    if message.chat.type != "private":
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db

    # Проверка прав (админы и владелец)
    if user.id != OWNER_ID and not db.is_admin(user.id):
        await message.reply_text("❌ У вас нет прав для просмотра чужих профилей.")
        return

    # Извлечение username из команды
    command = update.message.text
    username_match = re.match(r"^/@(\w+)$", command)

    if not username_match:
        await message.reply_text(
            "❌ Неверный формат команды.\n"
            "Используйте: /@username (например, /@ViceMGMT)"
        )
        return

    username = username_match.group(1)

    # Поиск пользователя
    target_user = db.get_user_by_username(username)

    if not target_user:
        await message.reply_text(f"❌ Пользователь @{username} не найден.")
        return

    # Формирование профиля
    try:
        rank = target_user["rank"]
        points = target_user["points"]
        last_activity = datetime.strptime(
            target_user["last_activity"], "%Y-%m-%d %H:%M:%S"
        )

        profile_text = (
            f"👤 <b>@{username}</b>\n"
            f"🏆 <b>Ранг:</b> {rank}\n"
            f"⭐ <b>Баллы:</b> {points:.1f}\n"
            "🕒 <b>Последняя активность:</b> "
            f"{last_activity.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"📊 <b>Сегодня:</b>\n"
            f"   📝 Сообщений: {target_user['messages_today']}\n"
            f"   🎵 Музыки: {target_user['music_today']}\n"
            f"   ❤️ Реакций: {target_user['reactions_given_today']}"
        )

        await message.reply_text(profile_text, parse_mode="HTML")

        logger.info(
            f"User profile shown: requested_by={user.id}, "
            f"target_user={target_user['user_id']}"
        )

    except Exception as e:
        logger.error(f"Error showing user profile: {e}")
        await message.reply_text(
            "❌ Произошла ошибка при получении профиля пользователя."
        )


def register_handlers(application: Application, bot_instance: BD) -> None:
    """
    Эта функция осуществляет регистрацию административных команд.
    Все команды доступны только в ЛС бота.
    Args:
        application (Application): Экземпляр приложения.
        bot_instance (BD): Экземпляр бота.
    """
    application.bot_data["bot_instance"] = bot_instance

    # Регистрация команд
    application.add_handler(CommandHandler("add", handle_add_command))
    application.add_handler(CommandHandler("legend", handle_legend_command))
    application.add_handler(CommandHandler("unlegend", handle_unlegend_command))
    application.add_handler(CommandHandler("setadmin", handle_setadmin_command))
    application.add_handler(CommandHandler("unsetadmin", handle_unsetadmin_command))
    application.add_handler(CommandHandler("admins", handle_admins_command))
    application.add_handler(CommandHandler("reset", handle_reset_command))

    # Регистрация команды /@{username} через обработчик текста
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.Regex(r"^/@\w+$"),
            handle_user_profile_command,
        )
    )

    logger.info("Admin handlers registered successfully")
