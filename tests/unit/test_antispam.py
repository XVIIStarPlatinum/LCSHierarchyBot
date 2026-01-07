from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import ANTI_SPAM_CONFIG, CHAT_ID, OWNER_ID, TOPIC_ID
from handlers.antispam import AntiSpamSystem
from utils.helpers import normalize_text


@pytest.fixture
def mock_bot_instance():
    """
    Фикстура для мокированного экземпляра бота.
    """
    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.get_user.return_value = {
        "user_id": 123,
        "username": "testuser",
        "rank": "Новичок",
        "last_activity": datetime.now(),
    }
    bot.db.is_admin.return_value = False
    bot.db.get_all_admins.return_value = [{"user_id": 999, "username": "admin"}]
    bot.db.mark_user_for_deletion.return_value = True
    return bot


@pytest.fixture
def antispam_system(mock_bot_instance):
    """
    Фикстура системы антиспама.
    """
    return AntiSpamSystem(mock_bot_instance)


class TestAntiSpamSystem:
    """
    Тесты для системы антиспама.
    """

    @pytest.mark.parametrize(
        "message_count, should_detect_spam",
        [
            (43, False),  # Менее 45 сообщений за минуту - не спам (43 + 1)
            (44, True),  # Ровно 45 - спам
            (50, True),  # Больше 45 - спам
        ],
    )
    async def test_message_frequency_detection(
        self, antispam_system, message_count, should_detect_spam
    ):
        """
        Тест обнаружения спама по частоте сообщений.
        Сообщение добавляется в число отправленных до assert.
        """
        user_id = 123
        now = datetime.now()

        # Заполняем историю сообщений
        antispam_system.message_timestamps[user_id] = [
            now - timedelta(seconds=i) for i in range(message_count)
        ]

        # Проверяем обнаружение спама
        is_spam = await antispam_system.check_message_frequency(user_id)
        assert is_spam == should_detect_spam

    @pytest.mark.parametrize(
        "identical_count, should_detect_spam",
        [
            (2, False),  # Менее 3 одинаковых сообщений - не спам
            (3, True),  # Ровно 3 одинаковых сообщения - спам
            (4, True),  # Больше 3 одинаковых сообщений - спам
        ],
    )
    async def test_identical_messages_detection(
        self, antispam_system, identical_count, should_detect_spam
    ):
        """
        Тест обнаружения спама по одинаковым сообщениям.
        """
        user_id = 123
        test_text = "привет мир привет"

        # Заполняем историю сообщений
        antispam_system.last_message_texts[user_id] = {
            "text": normalize_text(test_text),
            "count": identical_count - 1,  # Предыдущие сообщения
        }

        # Симулируем новое сообщение
        mock_message = MagicMock()
        mock_message.text = test_text

        # Проверяем обнаружение спама
        is_spam = await antispam_system.check_identical_messages(user_id, mock_message)
        assert is_spam == should_detect_spam

    @pytest.mark.parametrize(
        "user_rank, has_media, should_restrict",
        [
            ("Новичок", True, True),  # Новичок с медиа - ограничение
            ("Новичок", False, False),  # Новичок без медиа - нет ограничения
            ("Стажёр", True, False),  # Стажёр с медиа - нет ограничения
            ("Участник", True, False),  # Участник с медиа - нет ограничения
            ("Активист", True, False),  # Активист с медиа - нет ограничения
        ],
    )
    async def test_media_restrictions(
        self, antispam_system, mock_bot_instance, user_rank, has_media, should_restrict
    ):
        """
        Тест ограничений на медиа для новичков.
        """
        user_id = 123

        mock_bot_instance.db.get_user.return_value["rank"] = user_rank

        mock_message = MagicMock()
        mock_message.photo = [MagicMock()] if has_media else None
        mock_message.video = None
        mock_message.video_note = None
        mock_message.document = None
        mock_message.voice = None
        mock_message.animation = None
        mock_message.sticker = None
        mock_message.text = "тестовое сообщение"

        is_restricted = await antispam_system.check_media_restrictions(
            user_id, mock_message
        )
        assert is_restricted == should_restrict

    @pytest.mark.asyncio
    async def test_owner_and_admin_exclusion(self, antispam_system, mock_bot_instance):
        """
        Тест исключения владельца и админов из проверок.
        """
        owner_id = OWNER_ID
        chat_id = CHAT_ID
        topic_id = TOPIC_ID
        admin_id = 999

        mock_owner = MagicMock()
        mock_owner.id = owner_id

        mock_message = MagicMock()
        mock_message.chat.id = chat_id
        mock_message.message_thread_id = topic_id
        mock_message.text = "testing something..."

        # Проверяем исключение владельца
        mock_update = MagicMock()
        mock_update.effective_user = mock_owner
        mock_update.effective_message = mock_message

        is_spam = await antispam_system.check_spam(mock_update, MagicMock())
        assert not is_spam  # Владелец не должен быть помечен как спамер

        # Проверяем исключение админа
        mock_bot_instance.db.is_admin.return_value = True
        mock_admin = MagicMock()
        mock_admin.id = admin_id

        mock_admin_message = MagicMock()
        mock_admin_message.chat.id = chat_id
        mock_admin_message.message_thread_id = topic_id
        mock_admin_message.text = "admin testing something..."

        mock_update2 = MagicMock()
        mock_update2.effective_user = mock_admin
        mock_update2.effective_message = mock_admin_message

        is_spam = await antispam_system.check_spam(mock_update2, MagicMock())
        assert not is_spam  # Админ не должен быть помечен как спамер

    @pytest.mark.asyncio
    async def test_spam_handling(self, antispam_system, mock_bot_instance):
        """
        Тест обработки обнаруженного спама.
        """
        user_id = 123
        chat_id = CHAT_ID
        topic_id = TOPIC_ID

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()
        mock_context.bot.delete_message = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.username = "testuser"
        mock_user.first_name = "Test"

        mock_message = MagicMock()
        mock_message.message_id = 456
        mock_message.chat.id = chat_id
        mock_message.message_thread_id = topic_id
        mock_message.text = "spam message"
        mock_message.delete = AsyncMock()

        mock_update = MagicMock()
        mock_update.effective_message = mock_message
        mock_update.effective_user = mock_user

        await antispam_system.handle_detected_spam(
            mock_update, mock_context, mock_user, "чрезмерная частота сообщений"
        )

        mock_message.delete.assert_awaited_once()

        assert mock_context.bot.send_message.await_count >= 1

    @pytest.mark.asyncio
    async def test_media_restriction_handling(self, antispam_system, mock_bot_instance):
        """
        Тест обработки нарушения медиа-ограничений.
        """
        user_id = 123
        chat_id = CHAT_ID

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.username = "testuser"
        mock_user.first_name = "Test"

        mock_message = MagicMock()
        mock_message.message_id = 789
        mock_message.chat.id = chat_id
        mock_message.delete = AsyncMock()

        mock_update = MagicMock()
        mock_update.effective_message = mock_message
        mock_update.effective_user = mock_user

        # Симулируем нарушение ограничений
        await antispam_system.handle_media_restriction(
            mock_update, mock_context, mock_user
        )

        # Проверяем удаление сообщения
        mock_message.delete.assert_awaited_once()

        # Проверяем отправку уведомления пользователю
        mock_context.bot.send_message.assert_awaited_once()
        call_args = mock_context.bot.send_message.call_args
        assert call_args[1]["chat_id"] == user_id
        assert "ограничение медиа-контента" in call_args[1]["text"].lower()

    def test_text_normalization(self, antispam_system):
        """
        Тест нормализации текста для сравнения.
        """
        test_cases = [
            ("Привет, Мир!", "приветмир"),
            ("  Много     пробелов    ", "многопробелов"),
            ("Спец!@#$%^&*()_символы", "спецсимволы"),
            ("Ёжик и ёлка", "ёжикиёлка"),
            ("Mixed CASE text", "mixedcasetext"),
        ]

        for input_text, expected_output in test_cases:
            normalized = normalize_text(input_text)
            assert normalized == expected_output, (
                f"Failed for '{input_text}': got "
                f"{normalized}', expected '{expected_output}'"
            )

    @pytest.mark.asyncio
    async def test_spam_thresholds_from_config(self, antispam_system):
        """
        Тест использования пороговых значений из конфигурации.
        """
        assert (
            antispam_system.SPAM_THRESHOLD_MESSAGES
            == ANTI_SPAM_CONFIG["max_messages_per_minute"]
        )
        assert (
            antispam_system.SPAM_THRESHOLD_IDENTICAL
            == ANTI_SPAM_CONFIG["identical_messages_threshold"]
        )
