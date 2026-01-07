import logging
from datetime import datetime, timedelta
from typing import Union

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext._utils.types import BD

from config import CACHE_CONFIG, LOG_ENCODING, LOG_FORMAT, LOG_LEVEL, OWNER_ID
from database import Database
from utils.helpers import format_rank_with_emoji

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/profile.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Глобальные переменные для кэширования
PROFILE_CACHE = {}
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
        is_admin = await db.is_admin(user.id)

        if is_owner:
            welcome_prefix = (
                "🎉 <b>Добро пожаловать, создатель сообщества! "
                "Доступны команды: /profile, /top, /add, /legend, "
                "/unlegend, /setadmin, /unsetadmin, /admins, /reset, "
                "/@username.</b>"
            )
        elif is_admin:
            welcome_prefix = (
                "🎉 <b>Привет, админ! Управляй сообществом с помощью "
                "команд: /profile, /top, /add, "
                "/admins, /reset, /@username.</b>"
            )
        else:
            welcome_prefix = (
                "🎉 <b>Добро пожаловать в сообщество! Используй /profile"
                " для просмотра статуса, /top для рейтинга. Будь активным"
                " и повышай свой ранг!</b>"
            )
        welcome_message = welcome_prefix + (
            "\n\n"
            "🤖 Я - бот-калькулятор, который помогает отслеживать "
            "вашу активность и ранг в сообществе.\n\n"
            "📊 <b>Как это работает:</b>\n"
            "• За каждое сообщение вы получаете 0.1 балла\n"
            "• За загрузку музыки (MP3/WAV) - 1.0 балл\n"
            "• За реакции - 0.1 балла (макс. 33 в день)\n"
            "• За полученные реакции - 0.2 балла (без лимита)\n\n"
            "🏆 <b>Ранги в сообществе:</b>\n"
            "• 🔰 Новичок: 0+ баллов\n"
            "• 🎗 Стажёр: 10+ баллов\n"
            "• 🥉 Участник: 100+ баллов\n"
            "• 🥈 Активист: 200+ баллов\n"
            "• 🥇 Завсегдатай: 300+ баллов\n"
            "• 🏆 Представитель: 500+ баллов\n"
            "• 💎 Легенда: 1000+ баллов\n\n"
            "💡 <b>Полезные команды:</b>\n"
            "/profile - посмотреть свой профиль и статистику\n"
            "/top - топ-100 участников сообщества\n\n"
            "⚠️ <b>Важно:</b> Если вы не будете активны 24 часа в "
            "ранге «Новичок», вы будете удалены из чата. "
            "Регулярная активность поможет вам улучшить "
            "ранг и получить больше привилегий!\n\n"
            "🚀 <b>Начните общаться в основном чате, "
            "чтобы набирать баллы и повышать свой ранг!</b>"
        )

        sent_message = await update.message.reply_text(
            welcome_message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "👀 Посмотреть мой профиль", callback_data="view_profile"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📊 Топ участников", callback_data="view_top"
                        )
                    ],
                ]
            ),
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

    # Сохранение в кэш
    PROFILE_CACHE[cache_key] = {"data": profile_data, "timestamp": now}

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
    is_admin = await db.is_admin(user.id)
    is_owner = user.id == OWNER_ID
    use_cache = not (is_admin or is_owner)

    # Получение данных профиля
    profile = await get_cached_profile(user.id, db, is_owner=is_admin or is_owner)

    if not profile:
        await message.reply_text(
            "❌ Профиль не найден. Напишите /start для регистрации."
        )
        return

    # Форматирование профиля
    username = profile["username"] or f"user{user.id}"
    rank_with_emoji = format_rank_with_emoji(profile["rank"])

    # Получение привилегий и ограничений
    privileges = rank_system.get_user_privileges(profile["rank"])
    restrictions = rank_system.get_user_restrictions(profile["rank"])

    profile_text = (
        f"👤 <b>Профиль: @{username}</b>\n"
        f"🏆 <b>Ранг:</b> {rank_with_emoji}\n"
        f"💡 <b>Баллы:</b> {profile['points']:.1f}\n"
        f"📊 <b>Место:</b> {profile['position']}\n\n"
        f"🔓 <b>Привилегии:</b>\n"
    )

    # Формирование списка привилегий
    if privileges:
        for i, privilege in enumerate(privileges, 1):
            profile_text += f"   {i}. {privilege}\n"
    else:
        profile_text += "   Нет особых привилегий\n"

    profile_text += "\n🔒 <b>Ограничения:</b>\n"

    # Формирование списка ограничений
    if restrictions:
        for i, restriction in enumerate(restrictions, 1):
            profile_text += f"   {i}. {restriction}\n"
    else:
        profile_text += "   Нет ограничений\n"

    # Добавление пояснения
    profile_text += "\n📝 <b>Будь активным в жизни сообщества и повышай свой ранг!</b>"

    # Отправка ответа
    await message.reply_text(profile_text, parse_mode="HTML")

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

    # Проверка что команда в ЛС
    if message.chat.type != "private":
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db

    is_admin = await db.is_admin(user.id)
    is_owner = user.id == OWNER_ID
    use_cache = not (is_admin or is_owner)

    # Получение топ-100
    top_users = await get_cached_top_users(db, is_admin or is_owner)

    if not top_users:
        await message.reply_text("📊 Топ участников пока пуст.")
        return

    top_text = "🏆 <b>Топ-100 участников:</b>\n\n"

    for i, user_data in enumerate(top_users, 1):
        username = user_data["username"] or f"user{user_data['user_id']}"
        points = user_data["points"]

        medal = ""
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"

        top_text += f"{medal}{i}. @{username} - {points:.1f} баллов\n"

    cache_info = (
        "\n<i>Обновление: каждые 10 минут для участников, "
        "мгновенно для админов и владельца</i>"
    )
    top_text += cache_info

    await message.reply_text(top_text, parse_mode="HTML")

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
