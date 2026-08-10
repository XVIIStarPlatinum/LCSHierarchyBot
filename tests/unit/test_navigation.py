"""
Тесты диспетчера инлайн-навигации (handlers/navigation.py).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import OWNER_ID
from handlers.navigation import handle_navigation_callback


def make_update(user_id, callback_data, username="testuser"):
    user = MagicMock()
    user.id = user_id
    user.username = username

    query = MagicMock()
    query.data = callback_data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update = MagicMock()
    update.callback_query = query
    update.effective_user = user
    return update


def make_context(db, rank_system=None):
    bot_instance = MagicMock()
    bot_instance.db = db
    bot_instance.rank_system = rank_system or MagicMock()

    context = MagicMock()
    context.bot_data = {"bot_instance": bot_instance}
    return context


@pytest.mark.asyncio
async def test_nav_home_edits_message_with_hall_screen():
    update = make_update(555, "nav:home")
    db = MagicMock()
    db.is_admin.return_value = False
    context = make_context(db)

    await handle_navigation_callback(update, context)

    update.callback_query.answer.assert_called_once()
    update.callback_query.edit_message_text.assert_called_once()
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "Добро пожаловать в сообщество!" in text


@pytest.mark.asyncio
async def test_nav_home_shows_owner_text_for_owner():
    update = make_update(OWNER_ID, "nav:home")
    db = MagicMock()
    db.is_admin.return_value = True
    context = make_context(db)

    await handle_navigation_callback(update, context)

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "создатель сообщества" in text


@pytest.mark.asyncio
async def test_nav_profile_edits_message_with_profile_screen():
    update = make_update(555, "nav:profile")
    db = MagicMock()
    db.is_admin.return_value = False
    db.get_user.return_value = {
        "user_id": 555,
        "username": "testuser",
        "rank": "Новичок",
        "points": 3.0,
        "messages_today": 1,
        "music_today": 0,
        "reactions_given_today": 0,
        "last_activity": "2026-01-01 00:00:00",
    }
    db.get_user_rank_position.return_value = 42
    context = make_context(db)

    await handle_navigation_callback(update, context)

    update.callback_query.answer.assert_called_once()
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "@testuser" in text
    assert "42" in text


@pytest.mark.asyncio
async def test_nav_profile_not_found_answers_error_without_editing():
    update = make_update(999, "nav:profile")
    db = MagicMock()
    db.is_admin.return_value = False
    db.get_user.return_value = None
    context = make_context(db)

    await handle_navigation_callback(update, context)

    update.callback_query.answer.assert_called_once()
    error_text = update.callback_query.answer.call_args.args[0]
    assert "не найден" in error_text.lower()
    update.callback_query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_nav_top_edits_message_with_top_screen():
    update = make_update(555, "nav:top")
    db = MagicMock()
    db.is_admin.return_value = False
    context = make_context(db)

    with patch(
        "handlers.navigation.get_cached_top_users", new_callable=AsyncMock
    ) as mock_get_top:
        mock_get_top.return_value = [
            {"user_id": 1, "username": "alice", "points": 500.0},
        ]
        await handle_navigation_callback(update, context)

    update.callback_query.answer.assert_called_once()
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "@alice" in text
    mock_get_top.assert_awaited_once_with(db, False)


@pytest.mark.asyncio
async def test_nav_top_empty_list_still_renders_without_crashing():
    update = make_update(555, "nav:top")
    db = MagicMock()
    db.is_admin.return_value = False
    context = make_context(db)

    with patch(
        "handlers.navigation.get_cached_top_users", new_callable=AsyncMock
    ) as mock_get_top:
        mock_get_top.return_value = []
        await handle_navigation_callback(update, context)

    update.callback_query.answer.assert_called_once()
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "пока пуст" in text


@pytest.mark.asyncio
async def test_nav_admins_edits_message_for_admin():
    update = make_update(555, "nav:admins")
    db = MagicMock()
    db.is_admin.return_value = True
    context = make_context(db)

    with patch("handlers.navigation.get_admin_list_lines") as mock_get_lines:
        mock_get_lines.return_value = ["👑 @owner (владелец)", "👮 @somemod"]
        await handle_navigation_callback(update, context)

    update.callback_query.answer.assert_called_once()
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "@somemod" in text
    mock_get_lines.assert_called_once_with(db)


@pytest.mark.asyncio
async def test_nav_admins_edits_message_for_owner():
    update = make_update(OWNER_ID, "nav:admins")
    db = MagicMock()
    db.is_admin.return_value = False
    context = make_context(db)

    with patch("handlers.navigation.get_admin_list_lines") as mock_get_lines:
        mock_get_lines.return_value = ["👑 @owner (владелец)"]
        await handle_navigation_callback(update, context)

    update.callback_query.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_nav_admins_rejects_regular_user_with_alert_and_no_edit():
    """
    Регрессия ровно на тот сценарий, который описывает
    test_forged_callback_data_still_gets_real_role_check: даже если
    кнопка "👮 Админы" никому кроме админов/владельца не показывается,
    подделанный callback_data не должен давать доступ к списку
    администраторов.
    """
    update = make_update(555, "nav:admins")
    db = MagicMock()
    db.is_admin.return_value = False
    context = make_context(db)

    with patch("handlers.navigation.get_admin_list_lines") as mock_get_lines:
        await handle_navigation_callback(update, context)

    update.callback_query.answer.assert_called_once()
    alert_kwargs = update.callback_query.answer.call_args.kwargs
    alert_text = update.callback_query.answer.call_args.args[0]
    assert "нет прав" in alert_text.lower()
    assert alert_kwargs.get("show_alert") is True
    update.callback_query.edit_message_text.assert_not_called()
    mock_get_lines.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_action_answers_without_editing():
    update = make_update(555, "nav:something_that_does_not_exist")
    db = MagicMock()
    db.is_admin.return_value = False
    context = make_context(db)

    await handle_navigation_callback(update, context)

    update.callback_query.answer.assert_called_once()
    update.callback_query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_missing_bot_instance_answers_gracefully_without_crashing():
    update = make_update(555, "nav:home")
    context = MagicMock()
    context.bot_data = {}

    await handle_navigation_callback(update, context)

    update.callback_query.answer.assert_called_once()
    update.callback_query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_exception_during_render_is_caught_and_answered():
    update = make_update(555, "nav:home")
    db = MagicMock()
    db.is_admin.side_effect = RuntimeError("boom")
    context = make_context(db)

    # Не должно бросать исключение наружу — обработчик сам его ловит.
    await handle_navigation_callback(update, context)

    update.callback_query.answer.assert_called_once()
    update.callback_query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_forged_callback_data_still_gets_real_role_check():
    """
    Даже если кнопка админ-раздела никогда не была показана
    обычному пользователю, обработчик всё равно должен сам
    перепроверять права, а не доверять тому, что callback_data
    пришёл именно с показанной кнопки.
    """
    update = make_update(555, "nav:home")
    db = MagicMock()
    db.is_admin.return_value = False
    context = make_context(db)

    await handle_navigation_callback(update, context)

    db.is_admin.assert_called_once_with(555)
