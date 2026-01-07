import logging
from datetime import datetime
from typing import Optional

from telegram import (
    ChatMember,
    Message,
    MessageReactionUpdated,
    ReactionType,
    ReactionTypeCustomEmoji,
    ReactionTypeEmoji,
    Update,
    User,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ChatMemberHandler,
    ContextTypes,
    MessageHandler,
    MessageReactionHandler,
    filters,
)
from telegram.ext._utils.types import BD

from config import (
    BOT_USERNAME,
    CHAT_ID,
    LOG_ENCODING,
    LOG_FORMAT,
    LOG_LEVEL,
    OWNER_ID,
    POINTS_CONFIG,
    TOPIC_ID,
)
from database import Database

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/activity.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "🎉 Добро пожаловать в наше сообщество, {username}!\n"
    "Ты теперь часть пространства, где активность открывает новые возможности! 🚀\n"
    "Чтобы начать свой путь и получить доступ ко всем фишкам:\n"
    "    1. Напиши /start в личные сообщения боту "
    f"@{BOT_USERNAME} (это займёт 5 секунд!).\n"
    "    2. Узнай свой ранг, привилегии и возможности, будучи участником чата. 💎\n"
    "⚠️ Важно: Если не отправишь /start в течение 24 часов "
    "или заблокируешь бота и не активируешь его заново, бот удалит тебя из чата, "
    "даже не смотря на активность. Не упусти свой шанс!\n"
    "📩 Ждём тебя в ЛС бота! Будь активным и уважай участников сообщества. 🌟"
)


async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Эта функция осуществляет обработку новых участников чата.
    Отправляет приветственное сообщение в топике "Основной чат"
    для пользователей без `/start`.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    chat_member = update.chat_member
    new_member = chat_member.new_chat_member

    # Проверка того, что это новый участник
    if new_member.status != ChatMember.MEMBER or new_member.user.id == OWNER_ID:
        return

    # Проверка чата
    if chat_member.chat.id != CHAT_ID:
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db

    user = db.get_user(new_member.user.id)

    if user:
        bot_messages = db.get_user_bot_messages(new_member.user.id)
        if bot_messages:
            logger.debug(f"Existing verified user joined: {new_member.user.id}")
            return

    try:
        username = (
            f"@{new_member.user.username}"
            if new_member.user.username
            else new_member.user.first_name
        )
        welcome_text = WELCOME_MESSAGE.format(username=username)

        await context.bot.send_message(
            chat_id=CHAT_ID, message_thread_id=TOPIC_ID, text=welcome_text
        )
        logger.info(
            "Welcome message sent to new member: "
            f"{new_member.user.id}, username={username}"
        )
    except Exception as e:
        logger.error(
            f"Failed to send welcome message to new member {new_member.user.id}: {e}"
        )


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку активностей в виде текстовых сообщений.
    0.1 балла за сообщение длиной не менее 5 символов.
    Максимум за день — 3.6 баллов (или 36 сообщений).
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    message = update.effective_message
    user = update.effective_user

    if message.chat.id != CHAT_ID:
        return

    if hasattr(message, "message_thread_id") and message.message_thread_id != TOPIC_ID:
        return

    if user.id == OWNER_ID:
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db

    # Сравнение длины сообщения с минимальным (< 5)
    text = message.text.strip()
    if len(text) < POINTS_CONFIG["text_message"]["min_length"]:
        return

    user_data = db.get_user(user.id)
    if not user_data:
        db.create_user(user.id, user.username)
        user_data = db.get_user(user.id)

    # Проверка дневного лимита
    today = datetime.now().date()
    last_reset = (
        datetime.strptime(user_data["last_reset"], "%Y-%m-%d").date()
        if user_data["last_reset"]
        else today
    )

    if last_reset < today:
        db.reset_daily_counters()

    if (
        user_data["messages_today"]
        >= POINTS_CONFIG["text_message"]["max_messages_per_day"]
    ):
        return

    # Начисление баллов
    points_to_add = POINTS_CONFIG["text_message"]["points_per_message"]
    db.update_user_points(user.id, points_to_add)
    db.increment_counter(user.id, "messages")

    logger.debug(
        "Points awarded for text message: "
        f"user_id={user.id}, username={user.username}, points={points_to_add}"
    )


async def handle_audio_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку активностей в виде загрузки аудиофайлов.
    За загрузки аудиофайла из опознанных форматов
    пользователю будет начисляться 1 балл, максимум за день — 3.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    message = update.effective_message
    user = update.effective_user

    # Фильтрация по чату и топику
    if message.chat.id != CHAT_ID:
        return

    if hasattr(message, "message_thread_id") and message.message_thread_id != TOPIC_ID:
        return

    # Исключение владельца
    if user.id == OWNER_ID:
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db

    # wav или mp3
    mime_type = None
    if message.audio:
        mime_type = message.audio.mime_type
    elif (
        message.document
        and message.document.mime_type
        in POINTS_CONFIG["audio_upload"]["allowed_mime_types"]
    ):
        mime_type = message.document.mime_type

    if not mime_type:
        return

    user_data = db.get_user(user.id)
    if not user_data:
        db.create_user(user.id, user.username)
        user_data = db.get_user(user.id)

    today = datetime.now().date()
    last_reset = (
        datetime.strptime(user_data["last_reset"], "%Y-%m-%d").date()
        if user_data["last_reset"]
        else today
    )

    if last_reset < today:
        db.reset_daily_counters()

    if user_data["music_today"] >= POINTS_CONFIG["audio_upload"]["max_files_per_day"]:
        return

    points_to_add = POINTS_CONFIG["audio_upload"]["points_per_file"]
    db.update_user_points(user.id, points_to_add)
    db.increment_counter(user.id, "music")

    logger.debug(
        f"Points awarded for audio upload: user_id={user.id}, "
        f"username={user.username}, points={points_to_add}, mime_type={mime_type}"
    )


async def handle_reaction_update(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция осуществляет обработку обновлений реакций.
    0.1 балла за поставленную реакцию другому участнику.
    Максимум 3.3 балла в день (33 реакции).
    0.2 балла за полученную реакцию (без дневного лимита). Максимума здесь нет.

    Всего: максимум 9.9 баллов в день (3.6 + 3 + 3.3)
    + неограниченные баллы за полученные реакции.

    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    reaction_update: Optional[MessageReactionUpdated] = update.message_reaction
    if not reaction_update:
        logger.debug("No reaction update found in update")
        return

    try:
        if reaction_update.chat.id != CHAT_ID:
            logger.debug(
                "Reaction in wrong chat: "
                f"{reaction_update.chat.id}, expected: {CHAT_ID}"
            )
            return

        try:
            messages = await context.bot.get_messages(
                chat_id=reaction_update.chat.id,
                message_ids=[reaction_update.message_id],
            )
            message = messages[0] if messages else None
        except TelegramError as e:
            logger.warning(f"Could not fetch message {reaction_update.message_id}: {e}")
            return

        if not message:
            logger.debug(f"No message found with ID {reaction_update.message_id}")
            return

        message_thread_id = getattr(message, "message_thread_id", None)
        if message_thread_id is not None and message_thread_id != TOPIC_ID:
            logger.debug(
                f"Reaction in wrong topic: {message_thread_id}, expected: {TOPIC_ID}"
            )
            return

        user = reaction_update.user
        if not user or user.id == OWNER_ID:
            logger.debug("Skipping owner or missing user in reaction update")
            return

        bot_instance = context.bot_data.get("bot_instance")
        if not bot_instance:
            logger.error("Bot instance not found in context.bot_data")
            return

        db = bot_instance.db
        await _process_reaction_changes(reaction_update, message, user, db, context)

        logger.debug(
            f"✅ Reaction processed: chat_id={reaction_update.chat.id}, "
            f"message_id={reaction_update.message_id}, user_id={user.id}, "
            f"topic_id={message_thread_id}"
        )

    except Exception as e:
        logger.critical(
            f"🔥 CRITICAL FAILURE in reaction handler: {str(e)}",
            exc_info=True,
            extra={
                "chat_id": getattr(reaction_update, "chat_id", "unknown"),
                "message_id": getattr(reaction_update, "message_id", "unknown"),
                "user_id": getattr(
                    getattr(reaction_update, "user", None), "id", "unknown"
                ),
            },
        )
        await _notify_owner_critical_error(context, e, "reaction_handler")


async def _process_reaction_changes(
    reaction_update: MessageReactionUpdated,
    message: Message,
    user: User,
    db: Database,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Эта функция осуществляет обработку изменений
    реакций с корректной фильтрацией по топикам.
    Args:
        reaction_update (MessageReactionUpdated): Изменение реакции.
        message (Message): Сообщение, на которую ставили реакцию.
        user (User): Пользователь.
        db (Database): Класс работы с базой данных.
        context (ContextTypes): Контекст приложения.
    """
    old_reactions = reaction_update.old_reaction or []
    new_reactions = reaction_update.new_reaction or []

    # 1. Обработка убранных реакций
    removed_reactions = [r for r in old_reactions if r not in new_reactions]
    for reaction_type in removed_reactions:
        await _process_removed_reaction(
            reaction_update, user, reaction_type, db, context
        )

    # 2. Обработка поставленных реакций
    added_reactions = [r for r in new_reactions if r not in old_reactions]
    for reaction_type in added_reactions:
        await _process_given_reaction(reaction_update, user, reaction_type, db, context)

    # 3. Обработка полученных реакций (для автора сообщения)
    if added_reactions:
        await _process_received_reaction(
            db, context, reaction_update.message_id, message
        )


async def _process_given_reaction(
    reaction_update: MessageReactionUpdated,
    user: User,
    reaction_type: ReactionType,
    db: Database,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Эта функция осуществляет обработку поставленной реакции.
    Args:
        reaction_update (MessageReactionUpdated): Изменение реакции.
        user (User): Пользователь.
        reaction_type (ReactionType): Тип поставленной реакции.
        db (Database): Класс работы с базой данных.
        context (ContextTypes): Контекст приложения.
    """
    user_id = user.id
    username = user.username or user.first_name

    try:
        user_data = db.get_user(user_id)
        if not user_data:
            db.create_user(user_id, username)
            user_data = db.get_user(user_id)

        # Проверка дневного лимита
        today = datetime.now().date()
        last_reset_str = user_data["last_reset"]
        last_reset = (
            datetime.strptime(last_reset_str, "%Y-%m-%d").date()
            if last_reset_str
            else today
        )

        if last_reset < today:
            db.reset_daily_counters()

        # Начисление баллов (если не превышен лимит)
        if (
            user_data["reactions_given_today"]
            < POINTS_CONFIG["reaction_given"]["max_reactions_per_day"]
        ):
            points_to_add = POINTS_CONFIG["reaction_given"]["points_per_reaction"]
            db.update_user_points(user_id, points_to_add, None, "Reaction given")
            db.increment_counter(user_id, "reactions")

            reaction_emoji = await _get_reaction_emoji(reaction_type, context)

            logger.info(
                f"✅ Reaction given: user_id={user_id}, username={username}, "
                f"points=+{points_to_add}, reaction={reaction_emoji}, "
                f"message_id={reaction_update.message_id}"
            )

    except Exception as e:
        logger.error(
            f"Error processing given reaction for user_id={user_id}: {str(e)}",
            exc_info=True,
        )
        await _notify_owner_error(context, e, f"given_reaction_user_{user_id}")


async def _process_removed_reaction(
    reaction_update: MessageReactionUpdated,
    user: User,
    reaction_type: ReactionType,
    db: Database,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Эта функция осуществляет обработку убранной реакции (т.е. снятие баллов).
    Args:
        reaction_update (MessageReactionUpdated): Изменение реакции.
        user (User): Пользователь.
        reaction_type (ReactionType): Тип поставленной реакции.
        db (Database): Класс работы с базой данных.
        context (ContextTypes): Контекст приложения.
    """
    user_id = user.id

    try:
        user_data = db.get_user(user_id)
        if not user_data:
            return

        # Снятие баллов за убранную реакцию
        points_to_remove = -POINTS_CONFIG["reaction_given"]["points_per_reaction"]
        db.update_user_points(user_id, points_to_remove)

        reaction_emoji = await _get_reaction_emoji(reaction_type, context)

        logger.info(
            f"🔄 Reaction removed: user_id={user_id}, points={points_to_remove}, "
            f"reaction={reaction_emoji}, message_id={reaction_update.message_id}"
        )

    except Exception as e:
        logger.warning(
            "Non-critical error processing removed "
            f"reaction for user_id={user_id}: {str(e)}"
        )


async def _process_received_reaction(
    db: Database, context: ContextTypes.DEFAULT_TYPE, message_id: int, message: Message
) -> None:
    """
    Эта функция осуществляет обработку полученной реакции (для автора сообщения).
    Args:
        db (Database): Класс работы с базой данных.
        context (ContextTypes): Контекст приложения.
        message_id (int): ID сообщения.
        message (Message): Сообщение, которое получало реакций.
    """
    try:
        if not message or not hasattr(message, "from_user") or not message.from_user:
            logger.debug(f"No author found for message_id={message_id}")
            return

        target_user = message.from_user

        # Исключение владельца
        if target_user.id == OWNER_ID:
            logger.debug(f"Skipping received reaction for owner: user_id={OWNER_ID}")
            return

        # Начисление баллов
        target_user_data = db.get_user(target_user.id)
        if not target_user_data:
            db.create_user(
                target_user.id, target_user.username or target_user.first_name
            )

        points_to_add = POINTS_CONFIG["reaction_received"]["points_per_reaction"]
        db.update_user_points(target_user.id, points_to_add)

        username = target_user.username or target_user.first_name
        logger.info(
            "⭐ Reaction received: "
            f"target_user_id={target_user.id}, username={username}, "
            f"points=+{points_to_add}, message_id={message_id}"
        )

    except Exception as e:
        logger.error(
            f"Error processing received reaction for message_id={message_id}: {str(e)}",
            exc_info=True,
        )
        await _notify_owner_error(context, e, f"received_reaction_message_{message_id}")


async def _get_reaction_emoji(
    reaction_type: ReactionType, context: ContextTypes.DEFAULT_TYPE = None
) -> str:
    """Эта функция осуществляет безопасного получения эмодзи из типа реакции.
    Args:
        reaction_type (ReactionType): Тип реакции.
        context (ContextTypes): Контекст приложения.
    Returns:
        str: Эмодзи.
    """
    _ = context
    try:
        if isinstance(reaction_type, ReactionTypeEmoji):
            return reaction_type.emoji
        elif isinstance(reaction_type, ReactionTypeCustomEmoji):
            return f"🎨:{reaction_type.custom_emoji_id[:6]}"
        return f"❓:{type(reaction_type).__name__}"
    except Exception as e:
        logger.warning(f"Error getting reaction emoji: {e}")
        return "❓"


async def _notify_owner_error(
    context: ContextTypes.DEFAULT_TYPE, error: Exception, context_name: str
) -> None:
    """
    Эта функция отвечает за уведомления владельца о некритичной ошибке.
    Args:
        context (ContextTypes): Контекст приложения.
        error (Exception): Само исключение.
        context_name (str): Название контекста приложения (обычно это функция).
    """
    try:
        error_text = (
            f"⚠️ <b>Ошибка в обработке</b>\n\n"
            f"🔧 <b>Контекст:</b> {context_name}\n"
            f"❌ <b>Ошибка:</b> {str(error)[:200]}\n"
            f"⏰ <b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await context.bot.send_message(
            chat_id=OWNER_ID, text=error_text, parse_mode="HTML"
        )
    except Exception as notify_error:
        logger.error(f"Failed to notify owner about error: {notify_error}")


async def _notify_owner_critical_error(
    context: ContextTypes.DEFAULT_TYPE, error: Exception, module: str
) -> None:
    """
        Уведомление владельца о критической ошибке.
    Args:
            context (ContextTypes): Контекст приложения.
            error (Exception): Само исключение.
            module (str): Название модули, где возникло исключение.
    """
    try:
        error_text = (
            f"🚨 <b>КРИТИЧЕСКАЯ ОШИБКА</b>\n\n"
            f"🔧 <b>Модуль:</b> {module}\n"
            f"❌ <b>Ошибка:</b> {str(error)[:500]}\n"
            f"⏰ <b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"🛑 <b>Действие:</b> Требуется немедленное вмешательство!"
        )
        await context.bot.send_message(
            chat_id=OWNER_ID, text=error_text, parse_mode="HTML"
        )
    except Exception:
        pass


def register_handlers(application: Application, bot_instance: BD) -> None:
    """
    Эта функция осуществляет регистрацию обработчиков активности.
    Args:
        application (Application): Экземпляр приложения.
        bot_instance (BD): Экземпляр бота.
    """
    application.bot_data["bot_instance"] = bot_instance

    application.add_handler(
        ChatMemberHandler(handle_new_member, ChatMemberHandler.CHAT_MEMBER), group=0
    )

    application.add_handler(
        MessageHandler(
            filters.Chat(CHAT_ID) & filters.TEXT & ~filters.COMMAND, handle_text_message
        ),
        group=1,
    )

    application.add_handler(
        MessageHandler(
            filters.Chat(CHAT_ID) & (filters.AUDIO | filters.Document.AUDIO),
            handle_audio_message,
        ),
        group=1,
    )

    application.add_handler(MessageReactionHandler(handle_reaction_update), group=1)

    logger.info("Activity handlers registered successfully")
