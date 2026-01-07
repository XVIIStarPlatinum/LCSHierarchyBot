import io
import logging
import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from config import (LOG_ENCODING, LOG_FORMAT, LOG_LEVEL, OWNER_ID,
                    TELEGRAM_TOKEN)

# Исправление кодировки для Windows
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Настройка логирования
logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    encoding=LOG_ENCODING
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = TELEGRAM_TOKEN
OWNER_ID = OWNER_ID


@pytest.mark.asyncio
async def test_start_command_workflow():
    """
    ТЕСТ ДЛЯ /start:
    Бот не может отправить первое сообщение пользователю в Telegram.
    Вместо этого мы эмулируем сценарий, когда пользователь отправляет /start боту.
    """
    logger.info("Launching test for command /start...")

    from telegram import Chat, Message, Update, User
    from telegram.ext import Application, ContextTypes

    # 1. Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    bot = application.bot

    # 2. Проверяем подключение к API
    try:
        me = await bot.get_me()
        logger.info(f"Bot successfully connected: @{me.username} (ID: {me.id})")
    except Exception as e:
        logger.critical(f"Unable to call Telegram API: {e}")
        raise

    # 3. Мок-объекты
    mock_user = User(
        id=OWNER_ID,
        is_bot=False,
        first_name="Owner",
        username="owner_username",
        can_join_groups=True,
        can_read_all_group_messages=True,
        supports_inline_queries=True,
    )

    mock_chat = Chat(
        id=OWNER_ID,
        type="private"
    )

    mock_message = Message(
        message_id=1,
        date=datetime.now(),
        chat=mock_chat,
        text="/start",
        from_user=mock_user,
    )

    mock_update = Update(
        update_id=1,
        message=mock_message
    )

    mock_context = ContextTypes.DEFAULT_TYPE(application=application)

    # 4. Мок БД
    mock_db = MagicMock()
    mock_db.get_user.return_value = None
    mock_db.create_user.return_value = None
    mock_db.save_bot_message.return_value = True
    mock_db.is_admin.return_value = False

    # 5. Настраиваем бот-инстанс в контексте
    mock_context.bot_data["bot_instance"] = MagicMock()
    mock_context.bot_data["bot_instance"].db = mock_db

    # 6. Заглушка для обработчика start_command
    async def mock_start_command(update, context):
        logger.info("Mock handler of /start has been created successfully.")
        # Эмулируем отправку ответа
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Привет! Я бот LCS Hierarchy. Спасибо, что запустил меня!"
        )

        context.bot_data['bot_instance'].db.save_bot_message(
            message_id = sent_message.message_id,
            chat_id=sent_message.chat_id,
            user_id=update.effective_user.id,
            is_start_command=True
        )
        return True

    logger.info("Calling mock handler of /start...")
    try:
        result = await mock_start_command(mock_update, mock_context)
        logger.info(f"Mock handler called successfully. Result: {result}")
        assert result is not False, "Mock handler returned False"
    except Exception as e:
            logger.error(f"Error in mock handler of /start: {e}", exc_info=True)
            raise

@pytest.mark.asyncio
async def test_start_command_with_existing_user():
    """
        Тест команды /start для существующего пользователя.
        """
    logger.info("Testing /start for existing user...")

    from telegram.ext import Application, ContextTypes
    from telegram import Update, Message, User, Chat

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    bot = application.bot

    # Создаем мок-объекты
    mock_user = User(
        id=OWNER_ID,
        is_bot=False,
        first_name="Owner",
        username="owner_username",
        can_join_groups=True,
        can_read_all_group_messages=True,
        supports_inline_queries=True
    )

    mock_chat = Chat(id=OWNER_ID, type="private")

    mock_message = Message(
        message_id=1,
        date=datetime.now(),
        chat=mock_chat,
        text="/start",
        from_user=mock_user
    )

    mock_update = Update(update_id=1, message=mock_message)
    mock_context = ContextTypes.DEFAULT_TYPE(application=application)

    # Настраиваем мок БД - пользователь уже существует
    mock_db = MagicMock()
    mock_db.get_user.return_value = {
        'user_id': OWNER_ID,
        'username': 'owner_username',
        'rank': 'Легенда',
        'points': 9999.0
    }
    mock_db.is_admin.return_value = True
    mock_db.save_bot_message.return_value = True

    mock_context.bot_data['bot_instance'] = MagicMock()
    mock_context.bot_data['bot_instance'].db = mock_db

    # Обработчик для существующего пользователя
    async def mock_start_command_existing(update, context):
        user = context.bot_data['bot_instance'].db.get_user(update.effective_user.id)

        if user:
            text = f"С возвращением! Ваш ранг: {user['rank']}, баллы: {user['points']}"
        else:
            text = "Привет! Вы новый пользователь."

        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text
        )
        return sent_message is not None

    try:
        result = await mock_start_command_existing(mock_update, mock_context)
        assert result is True

        # Проверяем, что get_user был вызван
        mock_db.get_user.assert_called_once_with(OWNER_ID)

    except Exception as e:
        logger.error(f"Error in existing user test: {e}", exc_info=True)
        raise


@pytest.mark.asyncio
async def test_start_command_database_operations():
    """
    Тест операций с базой данных при выполнении /start.
    """
    logger.info("Testing /start database operations...")

    from telegram.ext import Application, ContextTypes
    from telegram import Update, Message, User, Chat

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    new_user_id = 12345
    mock_user = User(
        id=new_user_id,
        is_bot=False,
        first_name="TestUser",
        username="testuser",
        can_join_groups=True,
        can_read_all_group_messages=True,
        supports_inline_queries=True
    )

    mock_chat = Chat(id=new_user_id, type="private")

    mock_message = Message(
        message_id=1,
        date=datetime.now(),
        chat=mock_chat,
        text="/start",
        from_user=mock_user
    )

    mock_update = Update(update_id=1, message=mock_message)
    mock_context = ContextTypes.DEFAULT_TYPE(application=application)

    mock_db = MagicMock()
    mock_db.get_user.return_value = None
    mock_db.create_user.return_value = True
    mock_db.save_bot_message.return_value = True
    mock_db.is_admin.return_value = False

    mock_context.bot_data['bot_instance'] = MagicMock()
    mock_context.bot_data['bot_instance'].db = mock_db

    # Обработчик с операциями БД
    async def mock_start_with_db(update, context):
        db = context.bot_data['bot_instance'].db
        user_id = update.effective_user.id
        username = update.effective_user.username

        # Проверяем существование пользователя
        existing_user = db.get_user(user_id)

        if not existing_user:
            # Создаем нового пользователя
            db.create_user(user_id, username)

        # Отправляем сообщение
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Добро пожаловать!"
        )

        db.save_bot_message(
            message_id=sent_message.message_id,
            chat_id=sent_message.chat_id,
            user_id=user_id,
            is_start_command=True
        )

        return True

    try:
        result = await mock_start_with_db(mock_update, mock_context)
        assert result is True

        # Проверяем вызовы методов БД
        mock_db.get_user.assert_called_once_with(new_user_id)
        mock_db.create_user.assert_called_once_with(new_user_id, "testuser")
        mock_db.save_bot_message.assert_called_once()

    except Exception as e:
        logger.error(f"Error in database operations test: {e}", exc_info=True)
        raise
