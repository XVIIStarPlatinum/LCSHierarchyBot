from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest import approx

from config import CHAT_ID, OWNER_ID, TOPIC_ID


def create_text_message_mock(user_id: int, text: str) -> MagicMock:
    """
    Вспомогательная функция для создания и настройки замоканного сообщения.
    Args:
        user_id (int): ID пользователя.
        text (str): Само сообщение.
    Returns:
         MagicMock: Замоканное сообщение с параметрами.
    """
    mock_update = MagicMock()
    mock_update.effective_user.id = user_id
    mock_update.effective_message.chat.id = CHAT_ID
    mock_update.effective_message.message_thread_id = TOPIC_ID
    mock_update.effective_message.text = text

    # Обнуляем медиа атрибутов, а то тест ругается
    mock_update.effective_message.photo = None
    mock_update.effective_message.video = None
    mock_update.effective_message.video_note = None
    mock_update.effective_message.document = None
    mock_update.effective_message.voice = None
    mock_update.effective_message.animation = None
    mock_update.effective_message.sticker = None

    mock_update.effective_message.delete = AsyncMock()
    return mock_update


def create_media_message_mock(user_id: int, media_type: str = "photo") -> MagicMock:
    """
    Вспомогательная функция для создания и настройки замоканного медиа-сообщения.
    Args:
        user_id (int): ID пользователя.
        media_type (str): Тип медиа-сообщения.
    Returns:
         MagicMock: Замоканное медиа-сообщение с параметрами.
    """
    mock_update = MagicMock()
    mock_update.effective_user.id = user_id

    mock_message = MagicMock()
    mock_message.chat.id = CHAT_ID
    mock_message.message_thread_id = TOPIC_ID
    mock_message.text = None
    mock_message.delete = AsyncMock()

    # Обнуляем медиа атрибутов, а то тест ругается
    mock_message.photo = None
    mock_message.video = None
    mock_message.video_note = None
    mock_message.document = None
    mock_message.voice = None
    mock_message.animation = None
    mock_message.sticker = None

    if media_type == "photo":
        mock_message.photo = [MagicMock()]
    elif media_type == "video":
        mock_message.video = [MagicMock()]
    elif media_type == "video_note":
        mock_message.video_note = [MagicMock()]

    mock_update.effective_message = mock_message

    return mock_update


@pytest.fixture(scope="function")
def integrated_activity_system(tmp_path):
    """
    Фикстура для интеграционных тестов активности и антиспама.
    """
    from database import Database
    from handlers.antispam import AntiSpamSystem

    db_path = str(tmp_path / f"test_{id(tmp_path)}.db")
    db = Database(db_path)

    # Создаем mock bot
    mock_bot = MagicMock()
    mock_bot.db = db
    antispam_system = AntiSpamSystem(mock_bot)

    yield {"db": db, "antispam": antispam_system, "bot": mock_bot}

    try:
        db.conn.close()
    except Exception:
        pass


class TestActivityAntispamIntegration:
    """
    Интеграционные тесты для систем активности и антиспама.
    """

    async def test_normal_user_activity_flow(self, integrated_activity_system):
        """
        Тест нормального потока активности пользователя без спама.
        """
        db = integrated_activity_system["db"]
        antispam = integrated_activity_system["antispam"]

        # Создаем пользователя
        user_id = 4001
        username = "normal_user"
        db.create_user(user_id, username)

        # Создаем mock для update и context
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()

        # Симулируем 10 нормальных сообщений
        for i in range(10):
            mock_update = create_text_message_mock(user_id, f"Сообщение {i}")

            is_spam = await antispam.check_spam(mock_update, mock_context)
            assert not is_spam, f"Сообщение {i} ошибочно помечено как спам"

            # Начисляем баллы
            db.update_user_points(user_id, 0.1)
            db.increment_counter(user_id, "messages")

        # Проверяем результаты
        user = db.get_user(user_id)
        assert user["messages_today"] == 10
        assert user["points"] == approx(1.0)

    async def test_spam_detection_frequency(self, integrated_activity_system):
        """
        Тест обнаружения спама по частоте сообщений.
        """
        db = integrated_activity_system["db"]
        antispam = integrated_activity_system["antispam"]

        user_id = 4002
        username = "spammer_frequency"
        db.create_user(user_id, username)

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()

        # Симулируем 46 сообщений за минуту (превышение лимита)
        for i in range(46):
            mock_update = create_text_message_mock(user_id, f"Спам сообщение {i}")

            is_spam = await antispam.check_spam(mock_update, mock_context)

            # Первые 44 сообщения не должны быть спамом
            if i < 44:
                assert not is_spam, f"Сообщение {i} ошибочно помечено как спам"
            else:
                # 45-е и далее - спам
                assert is_spam, f"Сообщение {i} должно быть помечено как спам"

    async def test_spam_detection_identical_messages(self, integrated_activity_system):
        """
        Тест обнаружения спама по одинаковым сообщениям.
        """
        db = integrated_activity_system["db"]
        antispam = integrated_activity_system["antispam"]

        user_id = 4003
        username = "spammer_identical"
        db.create_user(user_id, username)

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()

        identical_text = "Одинаковое сообщение"

        # Отправляем 4 одинаковых сообщения
        for i in range(4):
            mock_update = create_text_message_mock(user_id, identical_text)

            is_spam = await antispam.check_spam(mock_update, mock_context)

            # Первые 2 сообщения не спам
            if i < 2:
                assert not is_spam, f"Сообщение {i} ошибочно помечено как спам"
            else:
                # 3-е и 4-е - спам
                assert is_spam, f"Сообщение {i} должно быть помечено как спам"

    async def test_media_restrictions_for_newbies(self, integrated_activity_system):
        """
        Тест ограничений на медиа для новичков.
        """
        db = integrated_activity_system["db"]
        antispam = integrated_activity_system["antispam"]

        # Новичок пытается отправить фото
        newbie_id = 4004
        db.create_user(newbie_id, "newbie_media")

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()

        # Пытаемся отправить фото
        mock_update = create_media_message_mock(newbie_id, "photo")

        is_spam = await antispam.check_spam(mock_update, mock_context)
        assert is_spam, "Медиа от новичка должно быть заблокировано"

        # Проверяем, что сообщение удалено
        mock_update.effective_message.delete.assert_awaited_once()

        # Стажёр может отправлять медиа
        trainee_id = 4005
        db.create_user(trainee_id, "trainee_media")
        db.update_user_points(trainee_id, 10.0)

        mock_update = create_media_message_mock(trainee_id, "photo")

        is_spam = await antispam.check_spam(mock_update, mock_context)
        assert not is_spam, "Медиа от стажёра не должно быть заблокировано"

    async def test_owner_and_admin_bypass(self, integrated_activity_system):
        """
        Тест обхода антиспама для владельца и администраторов.
        """
        db = integrated_activity_system["db"]
        antispam = integrated_activity_system["antispam"]

        # Создаем администратора
        admin_id = 4006
        db.create_user(admin_id, "admin_user")
        db.add_admin(admin_id, "admin_user")

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()

        # Симулируем 50 сообщений от владельца (превышение лимита)
        for i in range(50):
            mock_update = create_text_message_mock(OWNER_ID, f"Сообщение владельца {i}")

            is_spam = await antispam.check_spam(mock_update, mock_context)
            assert not is_spam, "Сообщения владельца не должны быть помечены как спам"

        # Симулируем 50 сообщений от админа
        for i in range(50):
            mock_update = create_text_message_mock(admin_id, f"Сообщение админа {i}")

            is_spam = await antispam.check_spam(mock_update, mock_context)
            assert not is_spam, "Сообщения админа не должны быть помечены как спам"

    async def test_combined_activity_and_antispam(self, integrated_activity_system):
        """
        Тест комбинированной работы активности и антиспама.
        """
        db = integrated_activity_system["db"]
        antispam = integrated_activity_system["antispam"]

        user_id = 4007
        username = "combined_user"
        db.create_user(user_id, username)

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()

        # Нормальная активность: 20 сообщений
        for i in range(20):
            mock_update = create_text_message_mock(user_id, f"Нормальное сообщение {i}")

            is_spam = await antispam.check_spam(mock_update, mock_context)
            if not is_spam:
                db.update_user_points(user_id, 0.1)
                db.increment_counter(user_id, "messages")

        # Проверяем, что баллы начислены
        user = db.get_user(user_id)
        assert user["messages_today"] == 20
        assert user["points"] == approx(2.0)
        assert user["rank"] == "Новичок"

        # Попытка спама: 30 сообщений подряд быстро
        spam_blocked = 0
        for i in range(30):
            mock_update = create_text_message_mock(user_id, f"Спам сообщение {i}")

            is_spam = await antispam.check_spam(mock_update, mock_context)
            if is_spam:
                spam_blocked += 1

        # Должно быть заблокировано несколько сообщений
        assert spam_blocked > 0, "Часть быстрых сообщений должна быть заблокирована"

        # Проверяем, что пользователь не получил баллы за спам
        user = db.get_user(user_id)
        assert user["messages_today"] == 20  # Осталось 20, спам не засчитан

    async def test_points_accumulation_with_limits(self, integrated_activity_system):
        """
        Тест накопления баллов с учетом дневных лимитов.
        """
        db = integrated_activity_system["db"]

        user_id = 4008
        username = "limits_user"
        db.create_user(user_id, username)

        # Пытаемся отправить 40 сообщений (лимит 36)
        for i in range(40):
            user = db.get_user(user_id)
            if user["messages_today"] < 36:
                db.update_user_points(user_id, 0.1)
                db.increment_counter(user_id, "messages")

        user = db.get_user(user_id)
        assert user["messages_today"] == 36  # Лимит достигнут
        assert user["points"] == approx(3.6)  # Максимум за сообщения

        # Пытаемся загрузить 5 аудиофайлов (лимит 3)
        for i in range(5):
            user = db.get_user(user_id)
            if user["music_today"] < 3:
                db.update_user_points(user_id, 1.0)
                db.increment_counter(user_id, "music")

        user = db.get_user(user_id)
        assert user["music_today"] == 3
        assert user["points"] == approx(6.6)  # 3.6 + 3.0

        # Навалим 40 реакций (лимит 33)
        for i in range(40):
            user = db.get_user(user_id)
            if user["reactions_given_today"] < 33:
                db.update_user_points(user_id, 0.1)
                db.increment_counter(user_id, "reactions")

        user = db.get_user(user_id)
        assert user["reactions_given_today"] == 33  # Лимит
        assert user["points"] == approx(9.9)  # 3.6 + 3.0 + 3.3

    async def test_multiple_users_concurrent_spam_detection(
        self, integrated_activity_system
    ):
        """
        Тест одновременного обнаружения спама от нескольких пользователей.
        """
        db = integrated_activity_system["db"]
        antispam = integrated_activity_system["antispam"]

        # Создаем 5 пользователей
        user_ids = range(5001, 5006)
        for user_id in user_ids:
            db.create_user(user_id, f"user_{user_id}")

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()

        spam_detected = {}

        # Каждый пользователь отправляет 50 сообщений
        for user_id in user_ids:
            spam_count = 0
            for i in range(50):
                mock_update = create_text_message_mock(user_id, f"Сообщение {i}")

                is_spam = await antispam.check_spam(mock_update, mock_context)
                if is_spam:
                    spam_count += 1

            spam_detected[user_id] = spam_count

        # Проверяем, что у каждого пользователя обнаружен спам
        for user_id, spam_count in spam_detected.items():
            assert spam_count > 0, (
                f"Спам должен быть обнаружен для пользователя {user_id}"
            )
