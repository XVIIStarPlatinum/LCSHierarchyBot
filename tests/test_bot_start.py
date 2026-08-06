"""
Тесты команды /start.

Ранее эти тесты не проверяли реальный обработчик — каждый тест
переопределял собственную упрощённую заглушку (`mock_start_command`,
`mock_start_command_existing`, `mock_start_with_db`) вместо вызова
`handlers.profile.handle_start_command`, а `test_start_command_workflow`
дополнительно строил настоящее `Application` и стучался в реальный
Telegram API (`bot.get_me()`), что не работает в песочнице без доступа
в сеть и не должно быть частью юнит-теста в принципе.

Переписано так, чтобы тестировать реальный обработчик с полностью
замоканными update/context/db — без создания настоящего Application,
Bot или JobQueue и без сетевых обращений.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from config import OWNER_ID, OWNER_USERNAME
from handlers.profile import handle_start_command


def make_user(user_id, username="testuser", first_name="Test"):
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.first_name = first_name
    return user


def make_update(user, chat_type="private"):
    update = MagicMock()
    update.effective_user = user
    update.effective_chat = MagicMock(type=chat_type)
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    sent_message = MagicMock(message_id=555, chat_id=user.id)
    update.message.reply_text.return_value = sent_message
    return update


def make_context(db):
    bot_instance = MagicMock()
    bot_instance.db = db
    context = MagicMock()
    context.bot_data = {"bot_instance": bot_instance}
    context.bot = MagicMock()
    context.bot.username = "HierarchyBot"
    return context


@pytest.mark.asyncio
async def test_start_command_new_user():
    """
    Новый пользователь (не владелец, не админ) отправляет /start:
    должна создаться запись в БД и уйти приветственное сообщение
    с обычным (не владелец/не админ) текстом.
    """
    user = make_user(12345, username="testuser")
    update = make_update(user)

    db = MagicMock()
    db.get_user.return_value = None
    db.is_admin.return_value = False
    context = make_context(db)

    await handle_start_command(update, context)

    db.create_user.assert_called_once_with(12345, "testuser")
    update.message.reply_text.assert_called_once()
    welcome_text = update.message.reply_text.call_args.args[0]
    assert "владелец" not in welcome_text.lower()
    assert "админ" not in welcome_text.lower()

    db.save_bot_message.assert_called_once_with(
        message_id=555, chat_id=12345, user_id=12345, is_start_command=True
    )


@pytest.mark.asyncio
async def test_start_command_existing_owner():
    """
    Владелец, уже существующий в БД, отправляет /start: не должен
    создаваться заново, и текст приветствия должен быть
    владелец-специфичным.
    """
    user = make_user(OWNER_ID, username=OWNER_USERNAME)
    update = make_update(user)

    db = MagicMock()
    db.get_user.return_value = {
        "user_id": OWNER_ID,
        "username": OWNER_USERNAME,
        "rank": "Легенда",
        "points": 9999.0,
    }
    db.is_admin.return_value = True
    context = make_context(db)

    await handle_start_command(update, context)

    db.get_user.assert_called_once_with(OWNER_ID)
    db.create_user.assert_not_called()

    welcome_text = update.message.reply_text.call_args.args[0]
    assert "создатель сообщества" in welcome_text


@pytest.mark.asyncio
async def test_start_command_existing_admin():
    """
    Существующий администратор (не владелец) отправляет /start:
    текст приветствия должен быть админским, а не обычным.
    """
    user = make_user(777, username="some_admin")
    update = make_update(user)

    db = MagicMock()
    db.get_user.return_value = {
        "user_id": 777,
        "username": "some_admin",
        "rank": "Активист",
        "points": 250.0,
    }
    db.is_admin.return_value = True
    context = make_context(db)

    await handle_start_command(update, context)

    welcome_text = update.message.reply_text.call_args.args[0]
    assert "Привет, админ!" in welcome_text
    assert "создатель сообщества" not in welcome_text


@pytest.mark.asyncio
async def test_start_command_in_group_chat():
    """
    /start в групповом чате (не ЛС) должен только предложить
    написать в личные сообщения — без обращений к БД.
    """
    user = make_user(555)
    update = make_update(user, chat_type="supergroup")

    db = MagicMock()
    context = make_context(db)

    await handle_start_command(update, context)

    db.get_user.assert_not_called()
    db.create_user.assert_not_called()
    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args.args[0]
    assert "личные сообщения" in reply_text
