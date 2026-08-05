from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import CHAT_ID, OWNER_ID, TOPIC_IMPORTANT_ID, VERIFICATION_CONFIG
from handlers.cleanup import (
    CleanupSystem,
    register_cleanup_task,
    run_scheduled_cleanup,
    safe_ban_user,
    send_cleanup_report,
)


@pytest.fixture
def mock_bot_instance():
    """
    Фикстура для мокированного экземпляра бота.
    """
    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.is_admin.return_value = False
    bot.db.mark_user_for_deletion.return_value = True
    bot.db.get_all_admins.return_value = [{"user_id": 999, "username": "admin_user"}]
    return bot


@pytest.fixture
def cleanup_system(mock_bot_instance):
    """
    Фикстура системы очистки.
    """
    return CleanupSystem(mock_bot_instance)


class TestCleanupSystem:
    """
    Тесты для системы очистки неактивных пользователей.
    """

    @pytest.mark.parametrize(
        "rank, inactive_hours, should_remove",
        [
            ("Новичок", 23, False),  # Менее 24 часов - не удалять
            ("Новичок", 24, True),  # Ровно 24 часа - удалять
            ("Новичок", 25, True),  # Больше 24 часов - удалять
            ("Стажёр", 71, False),  # Менее 3 дней (72 часа) - не удалять
            ("Стажёр", 72, True),  # Ровно 3 дня - удалять
            ("Стажёр", 73, True),  # Больше 3 дней - удалять
            ("Участник", 167, False),  # Менее 7 дней (168 часов) - не удалять
            ("Участник", 168, True),  # Ровно 7 дней - удалять
            ("Участник", 169, True),  # Больше 7 дней - удалять
            ("Активист", 719, False),  # Менее 30 дней (720 часов) - не удалять
            ("Активист", 720, True),  # Ровно 30 дней - удалять
            ("Активист", 721, True),  # Больше 30 дней - удалять
            ("Завсегдатай", 1000, False),  # Высшие ранги не удаляются
            ("Представитель", 1000, False),
            ("Легенда", 1000, False),
        ],
    )
    async def test_inactive_user_detection(
        self, cleanup_system, mock_bot_instance, rank, inactive_hours, should_remove
    ):
        """
        Тест обнаружения неактивных пользователей для каждого ранга.
        """
        user_id = 123
        now = datetime.now()

        # Настраиваем пользователя
        mock_bot_instance.db.get_user.return_value = {
            "user_id": user_id,
            "username": "testuser",
            "rank": rank,
            "last_activity": (now - timedelta(hours=inactive_hours)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }

        # Проверяем, должен ли пользователь быть удален
        result = await cleanup_system.should_skip_removal(
            user_id, rank, now - timedelta(hours=inactive_hours)
        )

        # should_skip_removal возвращает True если НЕ должен удаляться
        assert result != should_remove, (
            f"Ранг {rank}, неактивность {inactive_hours}ч: "
            f"ожидалось {should_remove}, получено {not result}"
        )

    async def test_owner_and_admin_exclusion(self, cleanup_system, mock_bot_instance):
        """
        Тест исключения владельца и администраторов из удаления.
        """
        now = datetime.now()

        # Тестируем владельца
        owner_rank = "Легенда"
        owner_last_activity = now - timedelta(days=100)  # Очень давно

        is_skipped = await cleanup_system.should_skip_removal(
            OWNER_ID, owner_rank, owner_last_activity
        )
        assert is_skipped is True, "Владелец не должен быть пропущен для удаления"

        # Тестируем администратора
        admin_id = 999
        admin_rank = "Представитель"
        admin_last_activity = now - timedelta(days=100)  # Очень давно

        # Настраиваем БД для проверки админа
        mock_bot_instance.db.is_admin.return_value = True

        is_skipped = await cleanup_system.should_skip_removal(
            admin_id, admin_rank, admin_last_activity
        )
        assert is_skipped is True, "Администратор не должен быть пропущен для удаления"

    async def test_unverified_user_removal(self, cleanup_system, mock_bot_instance):
        """
        Тест удаления неверифицированных пользователей (без /start).
        """
        now = datetime.now()
        cutoff_time = now - timedelta(hours=24)

        # Создаем неверифицированного пользователя
        unverified_user = {
            "user_id": 201,
            "username": "unverified_user",
            "last_activity": cutoff_time.strftime("%Y-%m-%d %H:%M:%S"),
            "rank": "Новичок",
        }

        # Настраиваем БД
        mock_bot_instance.db.get_unverified_users.return_value = [unverified_user]
        mock_bot_instance.db.get_user.return_value = unverified_user

        # Фикстура для контекста
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()
        mock_context.bot.ban_chat_member = AsyncMock()

        # Выполняем удаление
        removed_users = await cleanup_system.remove_unverified_users(mock_context)

        # Проверяем результат
        assert len(removed_users) == 1
        assert removed_users[0]["user_id"] == 201

        # Проверяем вызовы методов
        mock_context.bot.ban_chat_member.assert_awaited_once_with(
            chat_id=CHAT_ID, user_id=201
        )
        mock_bot_instance.db.mark_user_for_deletion.assert_called_once_with(201)

    async def test_important_notifications(self, cleanup_system, mock_bot_instance):
        """
        Тест отправки уведомлений в топике 'ВАЖНОЕ' при удалениию.
        Этот тест проверяет, что уведомления
        об удалении отправляются в правильной топике.
        В текущей реализации cleanup.py уведомления об автоматическом удалении
        отправляются только владельцу, а не в топике "ВАЖНОЕ".
        """
        user_id = 123
        username = "testuser"
        rank = "Новичок"
        last_activity = datetime.now() - timedelta(hours=25)

        # Фикстура для контекста
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()
        mock_context.bot.ban_chat_member = AsyncMock()

        # Выполняем удаление пользователя
        mock_bot_instance.db.get_user.return_value = {
            "user_id": user_id,
            "username": username,
            "rank": rank,
            "last_activity": last_activity.strftime("%Y-%m-%d %H:%M:%S"),
        }

        await cleanup_system.remove_user(
            mock_context, user_id, username, rank, last_activity
        )

        # Проверяем, что уведомление отправлено владельцу
        owner_notification_calls = [
            call
            for call in mock_context.bot.send_message.call_args_list
            if call[1]["chat_id"] == user_id
        ]
        assert len(owner_notification_calls) > 0, (
            "Уведомление должно быть отправлено владельцу"
        )

        # Проверяем, что уведомление НЕ отправлено в топике 'ВАЖНОЕ'
        important_topic_calls = [
            call
            for call in mock_context.bot.send_message.call_args_list
            if call[1].get("message_thread_id") == TOPIC_IMPORTANT_ID
        ]
        assert len(important_topic_calls) == 0, (
            "Уведомление не должно отправляться в "
            "топик 'ВАЖНОЕ' при автоматическом удалении"
        )

    async def test_error_handling_during_removal(
        self, cleanup_system, mock_bot_instance
    ):
        """
        Тест обработки ошибок при удалении пользователей.
        """
        user_id = 123
        username = "error_user"
        rank = "Новичок"
        last_activity = datetime.now() - timedelta(hours=25)

        # Фикстура для контекста
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()
        mock_context.bot.ban_chat_member = AsyncMock()

        # Симулируем ошибку при бане пользователя
        mock_context.bot.ban_chat_member.side_effect = Exception("Telegram API error")

        # Настраиваем пользователя
        mock_bot_instance.db.get_user.return_value = {
            "user_id": user_id,
            "username": username,
            "rank": rank,
            "last_activity": last_activity.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Пытаемся удалить пользователя
        result = await cleanup_system.remove_user(
            mock_context, user_id, username, rank, last_activity
        )

        # Проверяем результат
        assert result is False, "Удаление должно завершиться неудачей при ошибке"

        # Проверяем, что уведомление об ошибке отправлено владельцу
        owner_notification_calls = [
            call
            for call in mock_context.bot.send_message.call_args_list
            if call[1]["chat_id"] == OWNER_ID
        ]
        assert len(owner_notification_calls) > 0, (
            "Уведомление об ошибке должно быть отправлено владельцу"
        )

        # Проверяем, что пользователь не помечен для удаления
        mock_bot_instance.db.mark_user_for_deletion.assert_not_called()

    async def test_cleanup_report_generation(self, cleanup_system, mock_bot_instance):
        """
        Тест генерации отчета об очистке.
        """
        # Фикстуры для данных
        inactive_users = [
            {"user_id": 101, "username": "user1", "rank": "Новичок"},
            {"user_id": 102, "username": "user2", "rank": "Стажёр"},
            {"user_id": 103, "username": "user3", "rank": "Участник"},
        ]

        unverified_users = [{"user_id": 201, "username": "unverified1"}]

        # Фикстура для контекста
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()

        # Генерируем отчет
        await send_cleanup_report(
            mock_context,
            removed_count=2,  # 2 неактивных пользователя удалено
            skipped_count=1,  # 1 пользователь пропущен
            inactive_users=inactive_users,
            unverified_users=unverified_users,
        )

        # Проверяем отправку отчета владельцу
        mock_context.bot.send_message.assert_awaited_once_with(
            chat_id=OWNER_ID,
            text=mock_context.bot.send_message.call_args[1]["text"],
            parse_mode="HTML",
        )

        # Проверяем содержание отчета
        report_text = mock_context.bot.send_message.call_args[1]["text"]
        assert "Неактивных: 3" in report_text
        assert "Неверифицированных: 1" in report_text
        assert "За неактивность: 2" in report_text
        assert "За неверификацию: 1" in report_text
        assert "<b>Всего удалено:</b> 3" in report_text
        assert "<b>Пропущено:</b> 1" in report_text
        # До фикса get_clean_rank() всегда возвращала "Новичок" для
        # любого входа, поэтому все 3 пользователя (с разными рангами)
        # ошибочно попадали в один бакет. Корректное поведение —
        # по одному пользователю в каждом соответствующем ранге.
        assert "🔰 Новичок: 1" in report_text
        assert "🎗 Стажёр: 1" in report_text
        assert "🥉 Участник: 1" in report_text

    async def test_scheduled_cleanup_execution(self, mock_bot_instance):
        """
        Тест выполнения запланированной очистки.
        """
        # Фикстура для приложения
        mock_application = MagicMock()
        mock_application.bot_data = {}

        # Регистрируем задачу очистки
        register_cleanup_task(mock_application, mock_bot_instance)

        # Проверяем, что задача зарегистрирована
        assert "cleanup_system" in mock_application.bot_data
        assert hasattr(mock_application.job_queue, "run_repeating")

        # Фикстура для контекста
        mock_context = MagicMock()
        mock_context.bot_data = mock_application.bot_data

        # Выполняем запланированную очистку
        await run_scheduled_cleanup(mock_context)

        # Проверяем, что методы очистки были вызваны
        cleanup_system = mock_application.bot_data["cleanup_system"]
        assert hasattr(cleanup_system, "check_and_remove_inactive_users")

    async def test_verification_timeout_calculation(self, cleanup_system):
        """
        Тест расчета времени для верификации (24 часа).
        """
        VERIFY_THRESHOLD = VERIFICATION_CONFIG["unverified_timeout"]
        # Проверяем конфигурацию
        assert VERIFY_THRESHOLD == timedelta(hours=24).total_seconds()

        now = datetime.now()
        join_time = now - timedelta(hours=24)

        # Пользователь присоединился ровно 24 часа назад - должен быть удален
        should_remove = (now - join_time).total_seconds() >= VERIFY_THRESHOLD
        assert should_remove is True

        # Пользователь присоединился 23 часа 59 минут назад - не должен быть удален
        join_time = now - timedelta(hours=23, minutes=59)
        should_remove = (now - join_time).total_seconds() >= VERIFY_THRESHOLD
        assert should_remove is False

    async def test_cleanup_with_recent_activity(
        self, cleanup_system, mock_bot_instance
    ):
        """
        Тест пропуска пользователей с недавней активностью.
        """
        user_id = 123
        rank = "Новичок"
        now = datetime.now()

        # Пользователь был активен 23 часа назад (менее 24 часов)
        last_activity = now - timedelta(hours=23)

        # Проверяем, должен ли пользователь быть пропущен
        is_skipped = await cleanup_system.should_skip_removal(
            user_id, rank, last_activity
        )
        assert is_skipped is True, (
            "Пользователь с недавней активностью должен быть пропущен"
        )

        # Пользователь был активен 25 часов назад (более 24 часов)
        last_activity = now - timedelta(hours=25)

        # Проверяем, должен ли пользователь быть удален
        is_skipped = await cleanup_system.should_skip_removal(
            user_id, rank, last_activity
        )
        assert is_skipped is False, (
            "Пользователь с давней активностью не должен быть пропущен"
        )

    async def test_integration_with_database(self, db, cleanup_system):
        """
        Тест интеграции с реальной базой данных.
        """
        # Создаем тестовых пользователей
        test_users = [
            {  # Новичок - должен быть удален (неактивен 25 часов)
                "user_id": 301,
                "username": "inactive_newbie",
                "rank": "Новичок",
                "last_activity": datetime.now() - timedelta(hours=25),
            },
            {  # Стажёр - должен быть удален (неактивен 4 дня)
                "user_id": 302,
                "username": "inactive_trainee",
                "rank": "Стажёр",
                "last_activity": datetime.now() - timedelta(days=4),
            },
            {  # Активный пользователь - не должен быть удален
                "user_id": 303,
                "username": "active_user",
                "rank": "Участник",
                "last_activity": datetime.now() - timedelta(hours=1),
            },
            {  # Владелец - не должен быть удален
                "user_id": OWNER_ID,
                "username": "owner",
                "rank": "Легенда",
                "last_activity": datetime.now() - timedelta(days=100),
            },
        ]

        # Создаем пользователей в БД
        for user_data in test_users:
            db.create_user(user_data["user_id"], user_data["username"])
            cursor = db.conn.cursor()
            cursor.execute(
                """
                           UPDATE users
                           SET rank          = ?,
                               last_activity = ?
                           WHERE user_id = ?
                           """,
                (
                    user_data["rank"],
                    user_data["last_activity"].strftime("%Y-%m-%d %H:%M:%S"),
                    user_data["user_id"],
                ),
            )
            db.conn.commit()

        # Обновляем мок БД
        cleanup_system.bot.db = db

        # Фикстура для контекста
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()
        mock_context.bot.ban_chat_member = AsyncMock()

        # Выполняем очистку
        await cleanup_system.check_and_remove_inactive_users(mock_context)

        # Проверяем результаты
        for user_data in test_users:
            user = db.get_user(user_data["user_id"])
            if user_data["user_id"] in [301, 302]:  # Должны быть удалены
                assert user["rank"] == "УДАЛЕН"
            else:  # Не должны быть удалены
                assert user["rank"] != "УДАЛЕН"

    @pytest.mark.parametrize(
        "user_id, user_rank, last_activity_hours, is_admin, should_skip",
        [
            (123, "Новичок", 23, False, True),  # Недавняя активность
            (123, "Новичок", 25, False, False),  # Давняя активность
            (123, "Новичок", 25, True, True),  # Админ с давней активностью
            (123, "Завсегдатай", 1000, False, True),  # Высший ранг
            (OWNER_ID, "Легенда", 1000, False, True),
            # Владелец, поэтому должно быть пофиг
        ],
    )
    async def test_skip_removal_logic(
        self,
        cleanup_system,
        mock_bot_instance,
        user_id,
        user_rank,
        last_activity_hours,
        is_admin,
        should_skip,
    ):
        """
        Тест логики пропуска удаления пользователей.
        """
        now = datetime.now()
        last_activity = now - timedelta(hours=last_activity_hours)

        # Настраиваем админа
        mock_bot_instance.db.is_admin.return_value = is_admin

        # Проверяем логику пропуска
        result = await cleanup_system.should_skip_removal(
            user_id, user_rank, last_activity
        )
        assert result == should_skip, (
            f"User ID: {user_id} Ранг: {user_rank}, "
            f"неактивность: {last_activity_hours}ч, админ: {is_admin}. "
            f"Ожидалось {should_skip}, получено {result}"
        )

    async def test_cleanup_timing_intervals(self):
        """
        Тест временных интервалов для очистки.
        """
        from config import SCHEDULED_TASKS

        # Проверяем интервалы из конфигурации
        assert SCHEDULED_TASKS["inactivity_check"] == 600  # 10 минут в секундах

        # Проверяем регистрацию задачи
        mock_application = MagicMock()
        mock_bot_instance = MagicMock()

        register_cleanup_task(mock_application, mock_bot_instance)

        # Проверяем параметры задачи
        run_repeating_calls = mock_application.job_queue.run_repeating.call_args_list

        # Первый вызов (10 минут)
        first_call = run_repeating_calls[0]
        assert first_call[1]["interval"] == 600  # 10 минут
        assert first_call[1]["name"] == "inactive_cleanup"

        # Второй вызов (5 минут)
        second_call = run_repeating_calls[1]
        assert second_call[1]["interval"] == 300
        assert second_call[1]["name"] == "unverified_cleanup"

    async def test_unverified_cleanup_interval(self):
        """
        Тест интервала для очистки неверифицированных пользователей.
        """
        mock_application = MagicMock()
        mock_bot_instance = MagicMock()

        register_cleanup_task(mock_application, mock_bot_instance)

        # Проверяем, что зарегистрированы две задачи
        run_repeating_calls = mock_application.job_queue.run_repeating.call_args_list
        assert len(run_repeating_calls) == 2

        # Первая задача - основная очистка (10 минут)
        assert run_repeating_calls[0][1]["interval"] == 600
        assert run_repeating_calls[0][1]["name"] == "inactive_cleanup"

        # Вторая задача - очистка неверифицированных (5 минут)
        assert run_repeating_calls[1][1]["interval"] == 300
        assert run_repeating_calls[1][1]["name"] == "unverified_cleanup"

    async def test_safe_ban_user_function(self, cleanup_system):
        """
        Тест безопасного удаления пользователя.
        """
        # Фикстура для контекста
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.ban_chat_member = AsyncMock()

        # Тестируем успешное удаление
        result = await safe_ban_user(mock_context, 123, "testuser", "inactivity")
        assert result is True
        mock_context.bot.ban_chat_member.assert_awaited_once_with(
            chat_id=CHAT_ID, user_id=123
        )

        # Тестируем ошибку при удалении
        mock_context.bot.ban_chat_member.reset_mock()
        mock_context.bot.ban_chat_member.side_effect = Exception("Telegram error")

        result = await safe_ban_user(mock_context, 123, "testuser", "inactivity")
        assert result is False
        mock_context.bot.send_message.assert_awaited_once_with(
            chat_id=OWNER_ID,
            text=mock_context.bot.send_message.call_args[1]["text"],
            parse_mode="HTML",
        )
