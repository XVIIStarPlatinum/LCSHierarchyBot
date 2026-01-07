import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from config import LOG_ENCODING, LOG_FORMAT, LOG_LEVEL, OWNER_ID

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/private_chat.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


async def cleanup_private_chat(
    context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    """
    Эта функция реализует очистку ЛС от старых сообщений.
    Оставляет только:
    - Последнее ответа бота
    - Сообщения /start пользователя
    Args:
        context (ContextTypes): Контекст приложения.
        user_id (int): ID пользователя.
    """
    try:
        bot = context.bot
        db = context.bot_data["bot_instance"].db

        bot_messages = db.get_user_bot_messages(user_id)
        if not bot_messages:
            return

        bot_messages.sort(key=lambda x: x["timestamp"])

        messages_to_keep = [bot_messages[-1]]

        for msg in bot_messages:
            if msg.get("is_start_command") == 1:
                if msg not in messages_to_keep:
                    messages_to_keep.append(msg)

        messages_to_delete = [
            msg for msg in bot_messages if msg not in messages_to_keep
        ]

        for msg in messages_to_delete:
            try:
                await bot.delete_message(chat_id=user_id, message_id=msg["message_id"])
                db.delete_bot_message(msg["message_id"], user_id)
                logger.debug(
                    f"Deleted old bot message: user_id={user_id}, "
                    f"message_id={msg['message_id']}"
                )
            except Exception as e:
                logger.debug(
                    f"Failed to delete message {msg['message_id']} "
                    f"for user {user_id}: {e}"
                )
                db.delete_bot_message(msg["message_id"], user_id)

    except Exception as e:
        logger.error(f"Error in private chat cleanup for user {user_id}: {e}")


async def handle_pre_command_cleanup(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция служит обработчиком для очистки ЛС перед выполнением любой команды.
    Параметр context обязателен для соответствия API python-telegram-bot.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message

    if message.chat.type != "private":
        return

    if user.id == OWNER_ID:
        return

    await cleanup_private_chat(context, user.id)


async def handle_post_command_cleanup(
    update: Update, context: ContextTypes.DEFAULT_TYPE = None
):
    """
    Обработчик для очистки ЛС после выполнения команды.
    Параметр `context` обязателен для соответствия API
    python-telegram-bot, но не используется в данной функции.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes, optional): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message
    _ = context

    if message.chat.type != "private":
        return

    if user.id == OWNER_ID:
        return

    if message.text and not message.text.lower().startswith("/start"):
        try:
            await message.delete()
            logger.debug(
                "Deleted user command message: "
                f"user_id={user.id}, message_id={message.message_id}"
            )
        except Exception as e:
            logger.debug(
                f"Failed to delete user command message for user {user.id}: {e}"
            )


async def save_bot_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE = None
) -> None:
    """
    Сохранение сообщений бота в БД для последующей очистки.
    Параметр context обязателен для соответствия API
    python-telegram-bot, но не используется в данной функции.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes, optional): Контекст приложения.
    """
    user = update.effective_user
    message = update.effective_message

    if message.chat.type != "private":
        return

    bot_instance = context.bot_data["bot_instance"]
    db = bot_instance.db

    db.save_bot_message(message.message_id, message.chat.id, user.id)


def register_handlers(application, bot_instance):
    """
    Эта функция осуществляет регистрацию обработчиков для ЛС.
    Все обработчики имеют сигнатуру с параметром context по конвенции.
    Args:
        application (Application): Экземпляр приложения.
        bot_instance (BD): Экземпляр бота.
    """
    application.bot_data["bot_instance"] = bot_instance

    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.COMMAND, handle_pre_command_cleanup
        ),
        group=1,
    )

    application.add_handler(
        MessageHandler(filters.ChatType.PRIVATE, save_bot_message), group=10
    )

    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.COMMAND | filters.TEXT),
            handle_post_command_cleanup,
        ),
        group=5,
    )

    logger.info("Private chat cleanup handlers registered successfully")
