import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import OWNER_ID


@pytest.fixture(scope="function")
def integrated_admin_cleanup(tmp_path):
    """
    Фикстура для интеграционных тестов администрирования и очистки.
    """
    from database import Database
    from handlers.cleanup import CleanupSystem

    db_path = str(tmp_path / f"test_{id(tmp_path)}.db")

    db = Database(db_path)

    # Создаем mock bot instance
    mock_bot = MagicMock()
    mock_bot.db = db
    cleanup_system = CleanupSystem(mock_bot)

    yield {"db": db, "cleanup": cleanup_system, "bot": mock_bot}

    try:
        if hasattr(db, "conn") and db.conn:
            db.conn.close()
    except Exception:
        pass

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass


class TestAdminCleanupIntegration:
    """
    Интеграционные тесты для систем администрирования и очистки.
    """

    def test_admin_lifecycle(self, integrated_admin_cleanup):
        """
        Тест полного жизненного цикла администратора.
        """
        db = integrated_admin_cleanup["db"]

        # Создаем обычного пользователя
        admin_id = 6001
        admin_username = "new_admin"
        db.create_user(admin_id, admin_username)

        # Проверяем, что пользователь не админ
        assert not db.is_admin(admin_id)

        # Назначаем администратором
        result = db.add_admin(admin_id, admin_username)
        assert result is True
        assert db.is_admin(admin_id)

        # Проверяем список админов
        admins = db.get_all_admins()
        admin_ids = [admin["user_id"] for admin in admins]
        assert admin_id in admin_ids
        assert OWNER_ID in admin_ids  # Владелец тоже должен быть

        # Снимаем админ-права
        result = db.remove_admin(admin_id, admin_username)
        assert result is True
        assert not db.is_admin(admin_id)

    def test_admin_privileges_protection(self, integrated_admin_cleanup):
        """
        Тест защиты прав администраторов от удаления.
        """
        db = integrated_admin_cleanup["db"]

        admin_id = 6002
        db.create_user(admin_id, "protected_admin")
        db.add_admin(admin_id, "protected_admin")

        old_time = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE users SET last_activity = ? WHERE user_id = ?", (old_time, admin_id)
        )
        db.conn.commit()

        # Проверяем, что админ не попадает в список неактивных
        inactive_users = db.get_inactive_users()
        inactive_ids = [user["user_id"] for user in inactive_users]
        assert admin_id not in inactive_ids

        # Пытаемся пометить админа для удаления
        result = db.mark_user_for_deletion(admin_id)
        assert result is False  # Админа нельзя удалить

    async def test_cleanup_by_rank(self, integrated_admin_cleanup):
        """
        Тест очистки неактивных пользователей по рангам.
        """
        db = integrated_admin_cleanup["db"]

        now = datetime.now()

        # Создаем пользователей с разными рангами и неактивностью
        test_users = [
            # Новичок - должен быть удален (25 часов)
            (7001, "newbie_inactive", "Новичок", 5.0, now - timedelta(hours=25)),
            # Стажёр - должен быть удален (4 дня)
            (7002, "trainee_inactive", "Стажёр", 15.0, now - timedelta(days=4)),
            # Участник - должен быть удален (8 дней)
            (7003, "member_inactive", "Участник", 105.0, now - timedelta(days=8)),
            # Активист - должен быть удален (31 день)
            (7004, "activist_inactive", "Активист", 205.0, now - timedelta(days=31)),
            # Завсегдатай - НЕ должен быть удален (даже при долгой неактивности)
            (7005, "regular_inactive", "Завсегдатай", 305.0, now - timedelta(days=100)),
            # Новичок активный - НЕ должен быть удален
            (7006, "newbie_active", "Новичок", 5.0, now - timedelta(hours=1)),
        ]

        for user_id, username, rank, points, last_activity in test_users:
            db.create_user(user_id, username)
            db.update_user_points(user_id, points)
            cursor = db.conn.cursor()
            cursor.execute(
                """
                UPDATE users
                SET last_activity = ?
                WHERE user_id = ?
            """,
                (last_activity.strftime("%Y-%m-%d %H:%M:%S"), user_id),
            )
            db.conn.commit()

        # Получаем неактивных пользователей
        inactive_users = db.get_inactive_users()
        inactive_ids = [user["user_id"] for user in inactive_users]

        # Проверяем, что правильные пользователи в списке
        assert 7001 in inactive_ids  # Новичок
        assert 7002 in inactive_ids  # Стажёр
        assert 7003 in inactive_ids  # Участник
        assert 7004 in inactive_ids  # Активист
        assert 7005 not in inactive_ids  # Завсегдатай - защищен
        assert 7006 not in inactive_ids  # Новичок активный

    async def test_unverified_users_cleanup(self, integrated_admin_cleanup):
        """
        Тест очистки неверифицированных пользователей.
        """
        db = integrated_admin_cleanup["db"]

        now = datetime.now()
        cutoff_time = now - timedelta(hours=25)

        # Верифицированный пользователь (есть запись bot_messages)
        verified_id = 8001
        db.create_user(verified_id, "verified_user")
        db.save_bot_message(1, verified_id, verified_id)

        # Неверифицированный пользователь (нет записи bot_messages)
        unverified_id = 8002
        db.create_user(unverified_id, "unverified_user")
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE users SET last_activity = ? WHERE user_id = ?",
            (cutoff_time.strftime("%Y-%m-%d %H:%M:%S"), unverified_id),
        )
        db.conn.commit()

        # Получаем неверифицированных пользователей
        unverified_users = db.get_unverified_users()
        unverified_ids = [user["user_id"] for user in unverified_users]

        assert verified_id not in unverified_ids
        assert unverified_id in unverified_ids

    def test_manual_points_adjustment(self, integrated_admin_cleanup):
        """
        Тест ручного изменения баллов администратором.
        """
        db = integrated_admin_cleanup["db"]

        # Создаем пользователя и админа
        user_id = 9001
        admin_id = 9002
        db.create_user(user_id, "points_user")
        db.create_user(admin_id, "admin_user")
        db.add_admin(admin_id, "admin_user")

        # Начальные баллы
        initial_points = 50.0
        db.update_user_points(user_id, initial_points)

        # Админ добавляет баллы
        db.add_points_manually(user_id, 25.0, admin_id, "За активную помощь сообществу")
        user = db.get_user(user_id)
        assert user["points"] == 75.0

        # Админ убавляет баллы
        db.add_points_manually(user_id, -10.0, admin_id, "Нарушение правил")
        user = db.get_user(user_id)
        assert user["points"] == 65.0

    def test_inactivity_timer_reset(self, integrated_admin_cleanup):
        """
        Тест сброса таймера неактивности администратором.
        """
        db = integrated_admin_cleanup["db"]

        user_id = 10001
        db.create_user(user_id, "timer_user")

        old_time = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE users SET last_activity = ? WHERE user_id = ?", (old_time, user_id)
        )
        db.conn.commit()

        user = db.get_user(user_id)
        old_last_activity = datetime.strptime(
            user["last_activity"], "%Y-%m-%d %H:%M:%S"
        )
        assert old_last_activity < datetime.now() - timedelta(days=1)

        db.reset_inactivity_timer(user_id)

        user = db.get_user(user_id)
        new_last_activity = datetime.strptime(
            user["last_activity"], "%Y-%m-%d %H:%M:%S"
        )
        assert (datetime.now() - new_last_activity).total_seconds() < 60

    async def test_legend_rank_persistence(self, integrated_admin_cleanup):
        """
        Тест постоянства ранга "Легенда" при неактивности.
        """
        db = integrated_admin_cleanup["db"]

        legend_id = 11001
        db.create_user(legend_id, "legend_user")
        db.update_user_points(legend_id, 1500.0)
        db.update_user_rank(legend_id, "Легенда")

        old_time = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE users SET last_activity = ? WHERE user_id = ?",
            (old_time, legend_id),
        )
        db.conn.commit()

        # Проверяем, что легенда не попадает в список неактивных
        inactive_users = db.get_inactive_users()
        inactive_ids = [user["user_id"] for user in inactive_users]
        assert legend_id not in inactive_ids

        # Проверяем, что ранг сохраняется
        user = db.get_user(legend_id)
        assert user["rank"] == "Легенда"

    async def test_cleanup_notifications(self, integrated_admin_cleanup):
        """
        Тест отправки уведомлений при очистке.
        """
        db = integrated_admin_cleanup["db"]
        cleanup = integrated_admin_cleanup["cleanup"]

        # Создаем пользователя для удаления
        user_id = 12001
        username = "notification_user"
        db.create_user(user_id, username)

        # Делаем неактивным
        old_time = (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE users SET last_activity = ? WHERE user_id = ?", (old_time, user_id)
        )
        db.conn.commit()

        # Создаем mock context
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()
        mock_context.bot.ban_chat_member = AsyncMock()

        # Выполняем удаление
        last_activity = datetime.strptime(old_time, "%Y-%m-%d %H:%M:%S")
        result = await cleanup.remove_user(
            mock_context, user_id, username, "Новичок", last_activity
        )

        assert result is True

        # Проверяем, что уведомление отправлено
        assert mock_context.bot.send_message.await_count > 0
        assert mock_context.bot.ban_chat_member.await_count > 0

    def test_concurrent_admin_operations(self, integrated_admin_cleanup):
        """
        Тест одновременных операций от нескольких администраторов.
        """
        db = integrated_admin_cleanup["db"]

        # Создаем трёх админов
        admin_ids = [13001, 13002, 13003]
        for admin_id in admin_ids:
            db.create_user(admin_id, f"admin_{admin_id}")
            db.add_admin(admin_id, f"admin_{admin_id}")

        # Создаем пользователя
        target_user = 14001
        db.create_user(target_user, "target_user")
        db.update_user_points(target_user, 50.0)

        # Каждый админ добавляет баллы
        for admin_id in admin_ids:
            db.add_points_manually(target_user, 10.0, admin_id, "Поощрение от админа")

        # Проверяем итоговые баллы
        user = db.get_user(target_user)
        assert user["points"] == 80.0  # 50 + 30 (3 админа по 10)

    async def test_full_cleanup_cycle(self, integrated_admin_cleanup):
        """
        Тест полного цикла очистки с отчетом.
        """
        db = integrated_admin_cleanup["db"]
        cleanup = integrated_admin_cleanup["cleanup"]

        now = datetime.now()

        # Создаем разных пользователей
        # Неактивные для удаления
        for i in range(5):
            user_id = 15001 + i
            db.create_user(user_id, f"inactive_{i}")
            db.update_user_points(user_id, 5.0)  # Новичок
            cursor = db.conn.cursor()
            old_time = (now - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "UPDATE users SET last_activity = ? WHERE user_id = ?",
                (old_time, user_id),
            )
            db.conn.commit()

        # Активные пользователи
        for i in range(3):
            user_id = 16001 + i
            db.create_user(user_id, f"active_{i}")
            db.update_user_points(user_id, 100.0)  # Участник

        # Создаем mock context
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_message = AsyncMock()
        mock_context.bot.ban_chat_member = AsyncMock()

        # Выполняем полную очистку
        await cleanup.check_and_remove_inactive_users(mock_context)

        # Проверяем, что неактивные пользователи помечены
        for i in range(5):
            user_id = 15001 + i
            user = db.get_user(user_id)
            assert user["rank"] == "УДАЛЕН"

        # Проверяем, что активные пользователи не затронуты
        for i in range(3):
            user_id = 16001 + i
            user = db.get_user(user_id)
            assert user["rank"] != "УДАЛЕН"

        # Проверяем, что отчет отправлен владельцу
        owner_calls = [
            call
            for call in mock_context.bot.send_message.await_args_list
            if call[1]["chat_id"] == OWNER_ID
        ]
        assert len(owner_calls) > 0
