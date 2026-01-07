from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import CHAT_ID, OWNER_ID, TOPIC_IMPORTANT_ID
from utils.rank_system import RankSystem, get_rank_by_points, get_user_restrictions


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
        "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    db.update_user_rank.return_value = True
    db.get_top_users.return_value = [
        {"user_id": 123, "username": "testuser", "points": 0.0}
    ]
    db.get_user_bot_messages.return_value = [{"message_id": 1}]
    db.add_points_manually.return_value = True
    return db


@pytest.fixture
def rank_system(mock_db):
    """
    Фикстура системы рангов.
    """
    return RankSystem(mock_db)


class TestRankSystem:
    """
    Тесты для системы рангов.
    """

    @pytest.mark.parametrize(
        "points, expected_rank",
        [
            (0, "Новичок"),
            (5, "Новичок"),
            (9.9, "Новичок"),
            (10, "Стажёр"),
            (50, "Стажёр"),
            (99.9, "Стажёр"),
            (100, "Участник"),
            (150, "Участник"),
            (199.9, "Участник"),
            (200, "Активист"),
            (250, "Активист"),
            (299.9, "Активист"),
            (300, "Завсегдатай"),
            (400, "Завсегдатай"),
            (499.9, "Завсегдатай"),
            (500, "Представитель"),
            (750, "Представитель"),
            (999.9, "Представитель"),
            (1000, "Представитель"),
            (1500, "Представитель"),
        ],
    )
    def test_rank_by_points(self, rank_system, points, expected_rank):
        """
        Тест определения ранга по баллам для всех диапазонов.
        """
        rank = get_rank_by_points(points)
        assert rank == expected_rank

    @pytest.mark.parametrize(
        "rank_name, expected_privileges",
        [
            ("Новичок", ["Писать текстовые сообщения", "Загружать музыку (mp3/wav)"]),
            (
                "Стажёр",
                [
                    "Писать текстовые сообщения",
                    "Загружать музыку (mp3/wav)",
                    "Предпросмотр ссылок в чате",
                ],
            ),
            (
                "Участник",
                [
                    "Писать текстовые сообщения",
                    "Загружать музыку (mp3/wav)",
                    "Предпросмотр ссылок в чате",
                    "Голосовые сообщения",
                    "Отправка фотографий",
                    "Скачивание файлов из сообщества",
                ],
            ),
            (
                "Активист",
                [
                    "Писать текстовые сообщения",
                    "Загружать музыку (mp3/wav)",
                    "Предпросмотр ссылок в чате",
                    "Голосовые сообщения",
                    "Отправка фотографий",
                    "Скачивание файлов из сообщества",
                    "Создание опросов",
                    "Загрузка файлов",
                    "Приглашение участников через рекомендацию @ViceMGMT",
                ],
            ),
            (
                "Завсегдатай",
                [
                    "Писать текстовые сообщения",
                    "Загружать музыку (mp3/wav)",
                    "Предпросмотр ссылок в чате",
                    "Голосовые сообщения",
                    "Отправка фотографий",
                    "Скачивание файлов из сообщества",
                    "Создание опросов",
                    "Загрузка файлов",
                    "Приглашение участников через рекомендацию @ViceMGMT",
                    "Приглашение участников без согласования",
                    "Видео-сообщения",
                    "Отправка видео",
                    "Закрепление сообщений",
                ],
            ),
            (
                "Представитель",
                [
                    "Писать текстовые сообщения",
                    "Загружать музыку (mp3/wav)",
                    "Предпросмотр ссылок в чате",
                    "Голосовые сообщения",
                    "Отправка фотографий",
                    "Скачивание файлов из сообщества",
                    "Создание опросов",
                    "Загрузка файлов",
                    "Приглашение участников через рекомендацию @ViceMGMT",
                    "Приглашение участников без согласования",
                    "Видео-сообщения",
                    "Отправка видео",
                    "Закрепление сообщений",
                    "Отправка стикеров и гифок",
                    "Создание временных топиков для проектов",
                    "Участие в обсуждении нововведений сообщества",
                ],
            ),
            (
                "Легенда",
                [
                    "Писать текстовые сообщения",
                    "Загружать музыку (mp3/wav)",
                    "Предпросмотр ссылок в чате",
                    "Голосовые сообщения",
                    "Отправка фотографий",
                    "Скачивание файлов из сообщества",
                    "Создание опросов",
                    "Загрузка файлов",
                    "Приглашение участников через рекомендацию @ViceMGMT",
                    "Приглашение участников без согласования",
                    "Видео-сообщения",
                    "Отправка видео",
                    "Закрепление сообщений",
                    "Отправка стикеров и гифок",
                    "Создание временных топиков для проектов",
                    "Участие в обсуждении нововведений сообщества",
                    "Кандидат на роль администратора",
                    "Доступ к элитному чату с ресурсами и плейсментами",
                    "Возможность стать амбассадором сообщества",
                    'Бесплатная реклама в топике "ВАЖНОЕ"',
                ],
            ),
        ],
    )
    def test_rank_privileges(self, rank_system, rank_name, expected_privileges):
        """
        Тест привилегий для каждого ранга.
        """
        privileges = rank_system.get_user_privileges(rank_name)
        assert privileges == expected_privileges

    @pytest.mark.parametrize(
        "rank_name, expected_restrictions",
        [
            (
                "Новичок",
                [
                    "Нельзя скачивать файлы",
                    "Нельзя приглашать участников",
                    "Нельзя публиковать медиа (фото, видео, кружочки)",
                    "Удаление ботом за 24 часа бездействия",
                    "Баллы уменьшаются на 0.2 каждый час",
                    "Нельзя рекламироваться в сообществе",
                ],
            ),
            (
                "Стажёр",
                [
                    "Удаление ботом за 3 дня бездействия",
                    "Баллы уменьшаются на 0.1 каждый час",
                ],
            ),
            ("Участник", ["Удаление за 7 дней бездействия"]),
            ("Активист", ["Удаление за 1 месяц бездействия"]),
            ("Завсегдатай", []),
            ("Представитель", []),
            ("Легенда", []),
        ],
    )
    def test_rank_restrictions(self, rank_system, rank_name, expected_restrictions):
        """
        Тест ограничений для каждого ранга.
        """
        restrictions = get_user_restrictions(rank_name)
        assert restrictions == expected_restrictions

    def test_auto_rank_update_prevents_legend(self, rank_system, mock_db):
        """
        Тест автоматического обновления ранга
        (ранг "Легенда" не присваивается автоматически).
        """
        # Настраиваем пользователя с 1000+ баллами
        mock_db.get_user.return_value = {
            "user_id": 123,
            "username": "testuser",
            "points": 1000.0,
            "rank": "Представитель",
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Пытаемся обновить ранг автоматически
        result = rank_system.update_user_rank(123)

        # Проверяем, что ранг не стал "Легендой"
        assert result is False
        mock_db.update_user_rank.assert_not_called()

        # Проверяем, что пользователь остался "Представителем"
        assert mock_db.get_user(123)["rank"] == "Представитель"

    async def test_manual_legend_assignment(self, rank_system, mock_db):
        """
        Тест ручного присвоения ранга "Легенда".
        """
        # Настраиваем контекст
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()

        # Настраиваем пользователя
        mock_db.get_user.return_value = {
            "user_id": 123,
            "username": "testuser",
            "points": 500.0,
            "rank": "Представитель",
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Присваиваем ранг "Легенда" вручную
        result = await rank_system.set_legend_rank(123, OWNER_ID, mock_context)

        # Проверяем результат
        assert result is True
        mock_db.update_user_rank.assert_called_once_with(123, "Легенда")
        (
            mock_db.add_points_manually.assert_called_once_with(
                123, 0, OWNER_ID, "SET_LEGEND"
            )
        )

        # Проверяем уведомление в топике "ВАЖНОЕ"
        mock_context.bot.send_message.assert_awaited_once_with(
            chat_id=CHAT_ID,
            message_thread_id=TOPIC_IMPORTANT_ID,
            text="🎉 @testuser теперь легенда сообщества!",
            parse_mode="HTML",
        )

    async def test_manual_legend_removal(self, rank_system, mock_db):
        """
        Тест ручного снятия ранга "Легенда".
        """
        # Настраиваем контекст
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()

        # Настраиваем пользователя с рангом "Легенда"
        mock_db.get_user.return_value = {
            "user_id": 123,
            "username": "testuser",
            "points": 1000.0,
            "rank": "Легенда",
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Снимаем ранг "Легенда"
        result = await rank_system.unset_legend_rank(123, OWNER_ID, mock_context)

        # Проверяем результат
        assert result is True
        # Возвращаем ранг по баллам
        mock_db.update_user_rank.assert_called_once_with(123, "Представитель")
        (
            mock_db.add_points_manually.assert_called_once_with(
                123, 0, OWNER_ID, "UNSET_LEGEND"
            )
        )

        # Проверяем уведомление в топике "ВАЖНОЕ"
        mock_context.bot.send_message.assert_awaited_once_with(
            chat_id=CHAT_ID,
            message_thread_id=TOPIC_IMPORTANT_ID,
            text="🔔 @testuser больше не носит звание Легенды.",
            parse_mode="HTML",
        )

    async def test_owner_exclusion_from_rank_updates(self, rank_system, mock_db):
        """
        Тест исключения владельца из обновления рангов.
        """
        # Пытаемся обновить ранг владельца
        result = rank_system.update_user_rank(OWNER_ID)

        # Проверяем, что операция не выполнена
        assert result is False
        mock_db.update_user_rank.assert_not_called()
        mock_db.get_user.assert_not_called()  # Не должно быть запроса к БД

        # Пытаемся присвоить владельцу ранг "Легенда" вручную
        mock_context = MagicMock()
        result = await rank_system.set_legend_rank(OWNER_ID, OWNER_ID, mock_context)

        # Проверяем, что операция не выполнена
        assert result is False
        mock_db.update_user_rank.assert_not_called()

    @pytest.mark.asyncio
    async def test_rank_prefix_formatting(self, rank_system):
        """
        Тест форматирования префиксов рангов с эмодзи.
        """
        test_cases = [
            ("Новичок", "🔰 Новичок"),
            ("Стажёр", "🎗 Стажёр"),
            ("Участник", "🥉 Участник"),
            ("Активист", "🥈 Активист"),
            ("Завсегдатай", "🥇 Завсегдатай"),
            ("Представитель", "🏆 Представитель"),
            ("Легенда", "💎 Легенда"),
            ("Неизвестный_ранг", "Неизвестный_ранг"),  # Защита от неизвестных рангов
        ]

        for rank_name, expected_prefix in test_cases:
            prefix = rank_system.get_rank_prefix(rank_name)
            assert prefix == expected_prefix

    async def test_set_legend_rank_security(self, rank_system, mock_db):
        """
        Тест безопасности при присвоении ранга "Легенда".
        В этом тесте мы проверяем, что только
        владелец может присваивать ранг "Легенда".
        Но в текущей реализации проверка прав происходит на уровне команды /legend,
        поэтому здесь мы тестируем только логику RankSystem
        """
        # Настраиваем контекст
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()

        # Тестируем присвоение ранга несуществующему пользователю
        mock_db.get_user.return_value = None
        result = await rank_system.set_legend_rank(999, OWNER_ID, mock_context)
        assert result is False
        mock_db.update_user_rank.assert_not_called()

        # Тестируем попытку присвоения ранга админом (не владельцем)
        mock_db.get_user.return_value = {
            "user_id": 123,
            "username": "testuser",
            "points": 500.0,
            "rank": "Представитель",
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        mock_db.is_admin.return_value = True  # Симулируем админа

    def test_database_integration(self, db, sample_user):
        """
        Тест интеграции с реальной базой данных.
        """
        # Создаем экземпляр RankSystem с реальной БД
        rank_system = RankSystem(db)

        # Тестируем обновление ранга
        user_id = sample_user["user_id"]

        # Устанавливаем баллы для перехода в "Стажёры"
        # Нужно 10+ баллов для "Стажёра"
        db.update_user_points(user_id, 10.0)

        # Забыл: проверяем что ранг автоматически обновился
        user = db.get_user(user_id)
        assert user["rank"] == "Стажёр"
        assert user["points"] == 10.0

        # Обновляем ранг (не получится, так как это уже сделано)
        result = rank_system.update_user_rank(user_id)
        assert result is False

        # Проверяем автоматическое обновление при изменении баллов
        db.update_user_points(user_id, -5.0)  # Возвращаемся в "Новички"

        user = db.get_user(user_id)
        assert user["rank"] == "Новичок"
        assert user["points"] == 5.0

    async def test_error_handling_in_legend_assignment(self, rank_system, mock_db):
        """
        Тест обработки ошибок при присвоении ранга "Легенда".
        """
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()

        # Симулируем ошибку при обновлении ранга
        mock_db.update_user_rank.side_effect = Exception("Database error")

        # Настраиваем пользователя
        mock_db.get_user.return_value = {
            "user_id": 123,
            "username": "testuser",
            "points": 500.0,
            "rank": "Представитель",
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Пытаемся присвоить ранг "Легенда"
        result = await rank_system.set_legend_rank(123, OWNER_ID, mock_context)

        # Проверяем, что операция не выполнена
        assert result is False

        # Проверяем уведомление владельца об ошибке
        assert mock_context.bot.send_message.await_count >= 1

        # Проверяем, что уведомление в "ВАЖНОЕ" не отправлено
        calls = mock_context.bot.send_message.await_args_list
        important_topic_calls = [
            call
            for call in calls
            if call[1].get("message_thread_id") == TOPIC_IMPORTANT_ID
        ]
        assert len(important_topic_calls) == 0

    @pytest.mark.parametrize(
        "current_rank, points, expected_new_rank",
        [
            ("Новичок", 10.0, "Стажёр"),
            ("Стажёр", 90.0, "Стажёр"),  # Остается Стажёром
            ("Стажёр", 100.0, "Участник"),
            ("Участник", 100.0, "Участник"),  # Остается Участником
            ("Участник", 200.0, "Активист"),
            ("Активист", 300.0, "Завсегдатай"),
            ("Завсегдатай", 200.0, "Активист"),  # Деградация возможна
            # Автоматически не становится Легендой
            ("Завсегдатай", 1000.0, "Представитель"),
            # Легенда остается Легендой даже при падении баллов
            ("Легенда", 500.0, "Легенда"),
        ],
    )
    def test_rank_transitions(
        self, rank_system, mock_db, current_rank, points, expected_new_rank
    ):
        """
        Тест переходов между рангами при изменении баллов.
        """
        # Настраиваем пользователя
        mock_db.get_user.return_value = {
            "user_id": 123,
            "username": "testuser",
            "points": points,
            "rank": current_rank,
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Обновляем ранг
        result = rank_system.update_user_rank(123)

        # Проверяем результат
        if current_rank == "Легенда":
            # Легенда не может быть автоматически обновлена
            assert result is False
            assert mock_db.get_user(123)["rank"] == current_rank
        elif current_rank == expected_new_rank:
            # Если ранг не должен измениться
            assert result is False
        else:
            # Если должен
            assert result is True
            mock_db.update_user_rank.assert_called_once_with(123, expected_new_rank)

    async def test_legend_assignment_owner_protection(self, rank_system, mock_db):
        """
        Тест защиты владельца при присвоении ранга "Легенда".
        """
        mock_context = MagicMock()

        # Пытаемся присвоить ранг "Легенда" владельцу
        result = await rank_system.set_legend_rank(OWNER_ID, OWNER_ID, mock_context)

        # Проверяем, что операция не выполнена
        assert result is False
        mock_db.update_user_rank.assert_not_called()
        mock_db.add_points_manually.assert_not_called()

        # Проверяем, что уведомления не отправлены
        if hasattr(mock_context, "bot") and hasattr(mock_context.bot, "send_message"):
            assert mock_context.bot.send_message.call_count == 0

    def test_rank_details_retrieval(self, rank_system):
        """
        Тест получения детальной информации о ранге.
        """
        for rank_name in [
            "Новичок",
            "Стажёр",
            "Участник",
            "Активист",
            "Завсегдатай",
            "Представитель",
            "Легенда",
        ]:
            details = rank_system.get_rank_details(rank_name)
            assert details is not None
            assert "name" in details
            assert "min_points" in details
            assert "emoji" in details

        # Тест несуществующего ранга
        details = rank_system.get_rank_details("Несуществующий_ранг")
        assert details is None

    async def test_unset_legend_rank_no_legend_user(self, rank_system, mock_db):
        """
        Тест снятия ранга "Легенда" с пользователя, который не имеет этого ранга.
        """
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()

        # Настраиваем пользователя без ранга "Легенда"
        mock_db.get_user.return_value = {
            "user_id": 123,
            "username": "testuser",
            "points": 500.0,
            "rank": "Представитель",
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Пытаемся снять ранг "Легенда"
        result = await rank_system.unset_legend_rank(123, OWNER_ID, mock_context)

        # Проверяем, что операция не выполнена
        assert result is False
        mock_db.update_user_rank.assert_not_called()
        mock_db.add_points_manually.assert_not_called()

        # Проверяем, что уведомления не отправлены
        assert mock_context.bot.send_message.call_count == 0
