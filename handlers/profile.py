import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Union

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext._utils.types import BD

from config import CACHE_CONFIG, LOG_ENCODING, LOG_FORMAT, LOG_LEVEL, OWNER_ID
from database import Database
from handlers.screens import (
    render_entrance_hall,
    render_profile_screen,
    render_top_screen,
)

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/profile.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Глобальные переменные для кэширования.
# PROFILE_CACHE держит по одной записи на КАЖДОГО когда-либо запросившего
# /profile пользователя — без ограничения это неограниченно растущий
# словарь на весь срок жизни процесса. Используем OrderedDict как простой
# LRU: при превышении лимита вытесняется давнее всего использованная
# запись. TOP_CACHE, наоборот, всегда хранит ровно одну запись
# ("top_users"), так что ограничивать нечего.
PROFILE_CACHE: "OrderedDict[str, dict]" = OrderedDict()
TOP_CACHE = {}
LAST_CACHE_UPDATE = datetime.now()


async def handle_start_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция отвечает за обработку команды
    `/start` — точка входа для новых пользователей.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    user = update.effective_user
    chat = update.effective_chat

    if not user:
        logger.warning("Получена команда /start без информации о пользователе")
        return

    if chat.type != "private":
        await update.message.reply_text(
            "🌟 Для начала работы с ботом, "
            "пожалуйста, напиши мне в личные сообщения команду /start",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Написать в личные сообщения",
                            url=f"t.me/{context.bot.username}",
                        )
                    ]
                ]
            ),
        )
        return

    bot_instance = context.bot_data.get("bot_instance")
    if not bot_instance or not bot_instance.db:
        logger.error("Бот или база данных не инициализированы")
        await update.message.reply_text(
            "Критическая ошибка сервера. Пожалуйста, обратитесь к администратору."
        )
        return

    db = bot_instance.db

    try:
        existing_user = db.get_user(user.id)
        if not existing_user:
            db.create_user(user.id, user.username or user.first_name)
            logger.info(
                "✅ Новый пользователь зарегистрирован: "
                f"user_id={user.id}, username={user.username}"
            )
        else:
            current_username = existing_user["username"]
            new_username = user.username or user.first_name
            if current_username != new_username:
                logger.info(
                    "🔄 Имя пользователя обновлено: "
                    f"{current_username} -> {new_username}"
                )

        is_owner = user.id == OWNER_ID
        is_admin = db.is_admin(user.id)

        welcome_message, keyboard = render_entrance_hall(is_owner, is_admin)

        sent_message = await update.message.reply_text(
            welcome_message,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        bot_instance = context.bot_data["bot_instance"]
        bot_instance.db.save_bot_message(
            message_id=sent_message.message_id,
            chat_id=sent_message.chat_id,
            user_id=user.id,
            is_start_command=True,
        )

        logger.info(
            "Команда /start обработана успешно для пользователя: "
            f"{user.id} (@{user.username})"
        )

    except Exception as e:
        logger.error(
            f"Ошибка при обработке /start для пользователя {user.id}: {str(e)}",
            exc_info=True,
        )
        await update.message.reply_text(
            "Произошла ошибка при инициализации вашего профиля. "
            "Пожалуйста, попробуйте снова через минуту или обратитесь к администратору."
        )


async def get_cached_profile(
    user_id: int, db: Database, is_admin: bool = False, is_owner: bool = False
) -> Union[dict | None]:
    """Эта функция получает профиль с учетом кэширования.
    Args:
        user_id (int): ID пользователя.
        db (Database): Класс работы с базой данных.
        is_admin (bool, optional): Является ли пользователь админом?
        Дефолтное значение — `False`.
        is_owner (bool, optional): Является ли пользователь владельцем?
        Дефолтное значение — `False`.
    Returns:
        Union[dict | None]:
            - dict: Словарь, который представляет собой данные пользователя.
            - None: Если пользователя с таким ID нет.
    """
    cache_key = f"profile_{user_id}"
    now = datetime.now()

    # Проверка кэша
    if cache_key in PROFILE_CACHE:
        cached = PROFILE_CACHE[cache_key]
        cache_duration = get_cache_duration(is_admin, is_owner)
        if now - cached["timestamp"] < cache_duration:
            PROFILE_CACHE.move_to_end(cache_key)  # отмечаем как недавно использованный
            return cached["data"]

    # Получение свежих данных
    user = db.get_user(user_id)
    if not user:
        return None

    # Формирование данных профиля
    profile_data = {
        "user_id": user_id,
        "username": user["username"],
        "points": user["points"],
        "rank": user["rank"],
        "last_activity": user["last_activity"],
        "messages_today": user["messages_today"],
        "music_today": user["music_today"],
        "reactions_given_today": user["reactions_given_today"],
        "position": db.get_user_rank_position(user_id),
    }

    # Сохранение в кэш (с вытеснением давнего по LRU при превышении лимита)
    PROFILE_CACHE[cache_key] = {"data": profile_data, "timestamp": now}
    PROFILE_CACHE.move_to_end(cache_key)
    max_size = CACHE_CONFIG["profile_cache_max_size"]
    while len(PROFILE_CACHE) > max_size:
        PROFILE_CACHE.popitem(last=False)

    return profile_data


async def get_cached_top_users(db: Database, is_admin: bool = False) -> list:
    """
    Эта функция получает топ-100 с учетом кэширования.
    Args:
        db (Database): Класс работы с базой данных.
        is_admin (bool, optional): Является ли пользователь админом?
        Дефолтное значение — `False`.
    """
    now = datetime.now()
    cache_duration = get_cache_duration(is_admin, is_owner=True)

    # Проверка кэша
    if "top_users" in TOP_CACHE:
        cached = TOP_CACHE["top_users"]
        if now - cached["timestamp"] < cache_duration:
            return cached["data"]

    # Получение свежих данных
    top_users = db.get_top_users(100)  # Исключает владельца по умолчанию

    # Сохранение в кэш
    TOP_CACHE["top_users"] = {"data": top_users, "timestamp": now}

    return top_users


async def handle_profile_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку команды `/profile`.
    Доступна только в ЛС бота. Показывает полный профиль пользователя.
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

    # Проверка прав для определения времени кэширования
    is_admin = db.is_admin(user.id)
    is_owner = user.id == OWNER_ID
    use_cache = not (is_admin or is_owner)

    # Получение данных профиля
    profile = await get_cached_profile(user.id, db, is_owner=is_admin or is_owner)

    if not profile:
        await message.reply_text(
            "❌ Профиль не найден. Напишите /start для регистрации."
        )
        return

    # Форматирование профиля через общий экран (используется и командой,
    # и кнопкой "Мой профиль" — см. handlers/navigation.py)
    profile_text, keyboard = render_profile_screen(profile, rank_system)

    # Отправка ответа
    await message.reply_text(profile_text, parse_mode="HTML", reply_markup=keyboard)

    # Логирование
    logger.info(f"Profile shown for user_id={user.id}, cached={use_cache}")


async def handle_top_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку команды `/top`.
    Доступна только в ЛС бота. Показывает топ-100 участников.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message

    # Проверка, что команда в ЛС
    if message.chat.type != "private":
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db

    is_admin = db.is_admin(user.id)
    is_owner = user.id == OWNER_ID
    use_cache = not (is_admin or is_owner)

    # Получение топ-100
    top_users = await get_cached_top_users(db, is_admin or is_owner)

    # Форматирование топа через общий экран (используется и командой,
    # и кнопкой "🏆 Топ" — см. handlers/navigation.py). render_top_screen
    # сам обрабатывает пустой список.
    top_text, keyboard = render_top_screen(top_users)

    await message.reply_text(top_text, parse_mode="HTML", reply_markup=keyboard)

    logger.info(f"Top shown for user_id={user.id}, cached={use_cache}")


def get_cache_duration(is_admin: bool = False, is_owner: bool = False) -> timedelta:
    """
    Эта функция возвращает время кэширования в зависимости от пользователя.
    Args:
        is_admin (bool, optional): Является ли пользователь админом?
        Дефолтное значение — `False`.
        is_owner (bool, optional): Является ли пользователь владельцем?
        Дефолтное значение — `False`.
    Returns:
        timedelta: Срок кеширования в зависимости от указанных значений в `config.py`.
    """
    if is_owner:
        cache_duration = timedelta(seconds=CACHE_CONFIG["owner_cache_duration"])
    elif is_admin:
        cache_duration = timedelta(seconds=CACHE_CONFIG["admin_cache_duration"])
    else:
        cache_duration = timedelta(seconds=CACHE_CONFIG["user_cache_duration"])

    return cache_duration


def register_handlers(application: Application, bot_instance: BD) -> None:
    """
    Эта функция осуществляет регистрацию обработчиков профиля и топа.
    Все команды доступны только в ЛС бота и интегрируются с системой кэширования.
    Args:
        application (Application): Экземпляр приложения.
        bot_instance (BD): Экземпляр бота.
    """
    application.bot_data["bot_instance"] = bot_instance

    # Регистрация команд
    application.add_handler(CommandHandler("profile", handle_profile_command))
    application.add_handler(CommandHandler("top", handle_top_command))
    application.add_handler(CommandHandler("start", handle_start_command))

    logger.info("Profile handlers registered successfully")
