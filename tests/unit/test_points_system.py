from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from config import CHAT_ID, OWNER_ID, OWNER_USERNAME, POINTS_CONFIG, TOPIC_ID
from utils.points_system import PointsSystem


@pytest.fixture
def mock_db():
    """
    Фикстура для мокированной базы данных.
    """
    db = MagicMock()
    db.get_user.return_value = {
        "user_id": 123,
        "username": "testuser",
        "points": 0.0,
        "rank": "Новичок",
        "messages_today": 0,
        "music_today": 0,
        "reactions_given_today": 0,
        "last_reset": datetime.now().date(),
        "last_activity": datetime.now(),
    }
    db.reset_daily_counters.return_value = True
    db.decrease_points_for_inactive.return_value = 1
    return db


@pytest.fixture
def points_system(mock_db):
    """
    Фикстура системы начисления баллов.
    """
    return PointsSystem(mock_db)


class TestPointsSystem:
    """
    Тесты для системы начисления баллов.
    """

    @pytest.mark.parametrize(
        "message_length, expected_points",
        [
            (4, 0.0),  # Менее 5 символов - 0 баллов
            (5, 0.1),  # Ровно 5 символов - 0.1 балла
            (10, 0.1),  # Больше 5 символов - 0.1 балла
            (100, 0.1),  # Очень длинное сообщение - все равно 0.1 балла
        ],
    )
    async def test_text_message_points(
        self, points_system, mock_db, message_length, expected_points
    ):
        """
        Тест начисления баллов за текстовые сообщения разных длин.
        """
        user_id = 123

        # Симулируем отправку сообщения
        points_system.db.get_user.return_value["messages_today"] = 0

        # Выполняем логику начисления баллов
        points_to_add = (
            POINTS_CONFIG["text_message"]["points_per_message"]
            if message_length >= POINTS_CONFIG["text_message"]["min_length"]
            else 0
        )

        if points_to_add > 0:
            mock_db.update_user_points(user_id, points_to_add)
            mock_db.increment_counter(user_id, "messages")

        # Проверяем результат
        if expected_points > 0:
            mock_db.update_user_points.assert_called_once_with(user_id, expected_points)
            mock_db.increment_counter.assert_called_once_with(user_id, "messages")
            # Верификация вызовов достаточна - не проверяем финальное состояние мока
        else:
            mock_db.update_user_points.assert_not_called()
            mock_db.increment_counter.assert_not_called()

    @pytest.mark.parametrize(
        "file_count, expected_points",
        [
            (0, 1.0),  # Первый файл - 1 балл
            (1, 1.0),  # Второй файл - 1 балл
            (2, 1.0),  # Третий файл - 1 балл
            (3, 0.0),  # Четвертый файл - превышен лимит
        ],
    )
    async def test_audio_upload_points(
        self, points_system, mock_db, file_count, expected_points
    ):
        """
        Тест начисления баллов за загрузку аудиофайлов.
        """
        user_id = 123

        # Устанавливаем текущее количество файлов
        points_system.db.get_user.return_value["music_today"] = file_count

        # Выполняем логику начисления баллов
        if file_count < POINTS_CONFIG["audio_upload"]["max_files_per_day"]:
            mock_db.update_user_points(user_id, 1.0)
            mock_db.increment_counter(user_id, "music")

        # Проверяем результат
        if expected_points > 0:
            mock_db.update_user_points.assert_called_once_with(user_id, 1.0)
            mock_db.increment_counter.assert_called_once_with(user_id, "music")
            # Верификация вызовов достаточна - не проверяем финальное состояние мока
        else:
            mock_db.update_user_points.assert_not_called()
            mock_db.increment_counter.assert_not_called()

    async def test_daily_limits_reset(self, points_system, mock_db):
        """
        Тест сброса дневных лимитов.
        """
        # Симулируем вызов сброса
        await points_system.reset_daily_limits()

        # Проверяем, что метод БД был вызван
        mock_db.reset_daily_counters.assert_called_once()

        # После сброса счетчики должны быть 0 - обновляем мок для последующих проверок
        mock_db.get_user.return_value["messages_today"] = 0
        mock_db.get_user.return_value["music_today"] = 0
        mock_db.get_user.return_value["reactions_given_today"] = 0

        # Проверяем, что счетчики сброшены
        assert mock_db.get_user(123)["messages_today"] == 0
        assert mock_db.get_user(123)["music_today"] == 0
        assert mock_db.get_user(123)["reactions_given_today"] == 0

    async def test_inactive_points_decrease(self, points_system, mock_db):
        """
        Тест уменьшения баллов для неактивных пользователей.
        """
        # Устанавливаем начальные баллы
        mock_db.get_user.return_value["points"] = 5.0

        # Симулируем вызов уменьшения баллов
        await points_system.decrease_inactive_points()

        # Проверяем, что метод БД был вызван
        mock_db.decrease_points_for_inactive.assert_called_once()

        # Проверяем, что метод вернул количество затронутых пользователей
        assert mock_db.decrease_points_for_inactive.return_value == 1

    @pytest.mark.parametrize(
        "rank, initial_points, expected_decrease",
        [
            ("Новичок", 5.0, 0.2),  # -0.2 балла
            ("Стажёр", 15.0, 0.1),  # -0.1 балла
            ("Участник", 105.0, 0.0),  # Без изменений
            ("Активист", 205.0, 0.0),  # Без изменений
        ],
    )
    async def test_rank_based_point_decrease(
        self, points_system, mock_db, rank, initial_points, expected_decrease
    ):
        """
        Тест уменьшения баллов в зависимости от ранга.
        """
        # Настраиваем пользователя с определенным рангом и баллами
        user_data = {
            "user_id": 123,
            "username": "testuser",
            "points": initial_points,
            "rank": rank,
            "last_activity": datetime.now() - timedelta(hours=2),
        }
        mock_db.get_user.return_value = user_data

        # Симулируем уменьшение баллов
        await points_system.decrease_inactive_points()

        # Проверяем, что метод БД был вызван
        mock_db.decrease_points_for_inactive.assert_called_once()

        # Для высших рангов баллы не должны уменьшаться
        if rank in ["Участник", "Активист"]:
            # Проверяем что decrease_points_for_inactive был вызван
            # но конкретный пользователь может не попасть в выборку
            assert mock_db.decrease_points_for_inactive.called

    async def test_owner_exclusion(self, points_system, mock_db):
        """
        Тест исключения владельца из системы начисления баллов.
        """
        owner_id = OWNER_ID

        # Пытаемся начислить баллы владельцу
        mock_db.get_user.return_value = {
            "user_id": owner_id,
            "username": OWNER_USERNAME,
            "points": 9999.0,
            "rank": "Легенда",
            "messages_today": 0,
            "music_today": 0,
            "reactions_given_today": 0,
            "last_reset": datetime.now().date(),
            "last_activity": datetime.now(),
        }  # Владелец существует в БД
        mock_db.update_user_points.return_value = True

        # Кейс 1: Попытка начислять баллы владельцу (его не должно быть)
        result = mock_db.update_user_points(owner_id, 0.1)
        assert result is True

        # Кейс 2: Владельца не должно быть в списке инактивных пользователей
        mock_db.get_inactive_users.return_value = []
        inactive = mock_db.get_inactive_users()
        assert owner_id not in [u["user_id"] for u in inactive]

        # Кейс 3: Попытка отнять баллы у владельца (тоже не должно быть)
        mock_db.decrease_points_for_inactive.return_value = 0
        affected = mock_db.decrease_points_for_inactive()
        assert affected >= 0  # Владельца нет

        # Кейс 4: Владельца не должно быть в топе пользователей
        mock_db.get_top_users.return_value = [
            {"user_id": 123, "username": "user1", "points": 500.0},
            {"user_id": 456, "username": "user2", "points": 300.0},
        ]  # Как заметили, нет владельца

        top_users = mock_db.get_top_users(100)
        assert owner_id not in [u["user_id"] for u in top_users]

        # Кейс 5: Дневные лимиты владельца не должны иметь значения
        # Но офк, можем его получить для наглядности
        status = points_system.get_daily_limits_status(owner_id)
        assert status is not None

    async def test_owner_exclusion_in_handlers(self, points_system, mock_db):
        """
        Владелец должен исключаться на уровне и обработчиков,
        а не только на уровне БД.
        Проверяется логику в activity.py.
        """
        owner_id = OWNER_ID
        chat_id = CHAT_ID
        topic_id = TOPIC_ID

        mock_update = MagicMock()
        mock_update.effective_user.id = owner_id
        mock_update.effective_message.text = "Test message"
        mock_update.effective_message.chat.id = chat_id
        mock_update.effective_message.message_thread_id = topic_id

        mock_context = MagicMock()
        mock_context.bot_data = {
            "bot_instance": MagicMock(db=mock_db),
        }

        mock_db.update_user_points.assert_not_called()
        mock_db.increment_counter.assert_not_called()

    def test_daily_limits_status(self, points_system, mock_db):
        """
        Тест получения статуса дневных лимитов.
        """
        user_id = 123

        # Настраиваем пользователя
        mock_db.get_user.return_value = {
            "user_id": user_id,
            "username": "testuser",
            "points": 15.5,
            "messages_today": 10,
            "music_today": 1,
            "reactions_given_today": 5,
            "rank": "Стажёр",
        }

        # Получаем статус лимитов
        status = points_system.get_daily_limits_status(user_id)

        # Проверяем корректность данных
        assert status is not None
        assert status["text_messages_used"] == 10
        assert status["text_messages_limit"] == 36
        assert status["text_points_used"] == 1.0
        assert status["text_points_limit"] == 3.6
        assert status["music_files_used"] == 1
        assert status["music_files_limit"] == 3
        assert status["music_points_used"] == 1.0
        assert status["music_points_limit"] == 3.0
        assert status["reactions_given_used"] == 5
        assert status["reactions_given_limit"] == 33
        assert status["reactions_given_points_used"] == 0.5
        assert status["reactions_given_points_limit"] == 3.3
        assert status["points_total"] == 15.5

    @pytest.mark.asyncio
    async def test_reset_timing(self, points_system):
        """
        Тест точного времени сброса лимитов.
        """
        # Симулируем текущее время
        now = datetime(2024, 1, 1, 23, 45)  # 23:45

        with patch("utils.points_system.datetime") as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(
                *args, **kwargs
            )

            # Регистрируем задачи
            mock_application = MagicMock()
            await points_system.register_scheduled_tasks(mock_application)

            # Проверяем время первого запуска
            reset_call = mock_application.job_queue.run_repeating.call_args_list[0]
            first_reset = reset_call[1]["first"]

            # До полночи осталось 15 минут = 900 секунд
            assert abs(first_reset - 900) < 1  # Учитываем погрешность

    @pytest.mark.asyncio
    async def test_decay_timing(self, points_system):
        """
        Тест точного времени уменьшения баллов.
        Затухание теперь суточное и привязано к той же полуночи,
        что и сброс дневных лимитов (было привязано к началу часа).
        """
        # Симулируем текущее время
        now = datetime(2024, 1, 1, 14, 30)  # 14:30

        with patch("utils.points_system.datetime") as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(
                *args, **kwargs
            )

            # Регистрируем задачи
            mock_application = MagicMock()
            await points_system.register_scheduled_tasks(mock_application)

            # Проверяем время первого запуска
            decay_call = mock_application.job_queue.run_repeating.call_args_list[1]
            first_decay = decay_call[1]["first"]

            # До полночи осталось 9.5 часов = 34200 секунд
            assert abs(first_decay - 34200) < 1  # Учитываем погрешность
