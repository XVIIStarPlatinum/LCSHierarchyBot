from datetime import datetime, timedelta

import pytest
from pytest import approx

from utils.rank_system import get_user_restrictions


@pytest.fixture(scope="function")
def integrated_systems(tmp_path):
    """
    Фикстура для интеграционных тестов систем баллов и рангов.
    """
    from database import Database
    from utils.points_system import PointsSystem
    from utils.rank_system import RankSystem

    db_path = str(tmp_path / "test_.db")
    db = Database(db_path)

    points_system = PointsSystem(db)
    rank_system = RankSystem(db)

    yield {"db": db, "points_system": points_system, "rank_system": rank_system}

    try:
        db.conn.close()
    except Exception:
        pass


class TestPointsRankIntegration:
    """
    Интеграционные тесты для систем баллов и рангов.
    """

    def test_automatic_rank_progression(self, integrated_systems):
        """
        Тест автоматического прогресса по рангам при накоплении баллов.
        """
        db = integrated_systems["db"]

        # Создаем пользователя
        user_id = 1001
        username = "progression_user"
        db.create_user(user_id, username)

        user = db.get_user(user_id)
        assert user["rank"] == "Новичок"
        assert user["points"] == 0.0

        # Прогрессия: Новичок -> Стажёр (10 баллов)
        db.update_user_points(user_id, 10.0)
        user = db.get_user(user_id)
        assert user["rank"] == "Стажёр"
        assert user["points"] == approx(10.0)

        # Прогрессия: Стажёр -> Участник (100 баллов)
        db.update_user_points(user_id, 90.0)
        user = db.get_user(user_id)
        assert user["rank"] == "Участник"
        assert user["points"] == approx(100.0)

        # Прогрессия: Участник -> Активист (200 баллов)
        db.update_user_points(user_id, 100.0)
        user = db.get_user(user_id)
        assert user["rank"] == "Активист"
        assert user["points"] == approx(200.0)

        # Прогрессия: Активист -> Завсегдатай (300 баллов)
        db.update_user_points(user_id, 100.0)
        user = db.get_user(user_id)
        assert user["rank"] == "Завсегдатай"
        assert user["points"] == approx(300.0)

        # Прогрессия: Завсегдатай -> Представитель (500 баллов)
        db.update_user_points(user_id, 200.0)
        user = db.get_user(user_id)
        assert user["rank"] == "Представитель"
        assert user["points"] == approx(500.0)

        # 1000+ баллов *не*᠊ дает Легенду автоматически
        db.update_user_points(user_id, 500.0)
        user = db.get_user(user_id)
        assert user["rank"] == "Представитель"
        assert user["points"] == approx(1000.0)

    def test_rank_degradation_with_point_loss(self, integrated_systems):
        """
        Тест деградации ранга при потере баллов.
        """
        db = integrated_systems["db"]

        # Создаем пользователя с высоким рангом
        user_id = 1002
        username = "degradation_user"
        db.create_user(user_id, username)
        db.update_user_points(user_id, 500.0)

        user = db.get_user(user_id)
        assert user["rank"] == "Представитель"

        # Теряем баллы: Представитель -> Активист
        db.update_user_points(user_id, -250.0)
        user = db.get_user(user_id)
        assert user["rank"] == "Активист"
        assert user["points"] == approx(250.0)

        # Теряем баллы: Активист -> Участник
        db.update_user_points(user_id, -100.0)
        user = db.get_user(user_id)
        assert user["rank"] == "Участник"
        assert user["points"] == approx(150.0)

        # Теряем баллы: Участник -> Стажёр
        db.update_user_points(user_id, -100.0)
        user = db.get_user(user_id)
        assert user["rank"] == "Стажёр"
        assert user["points"] == approx(50.0)

        # Теряем баллы: Стажёр -> Новичок
        db.update_user_points(user_id, -45.0)
        user = db.get_user(user_id)
        assert user["rank"] == "Новичок"
        assert user["points"] == approx(5.0)

    def test_daily_activity_cycle(self, integrated_systems):
        """
        Тест полного цикла дневной активности пользователя.
        """
        db = integrated_systems["db"]
        points_system = integrated_systems["points_system"]

        # Создаем пользователя
        user_id = 1003
        username = "daily_user"
        db.create_user(user_id, username)

        # Симулируем дневную активность
        # 10 текстовых сообщений
        for _ in range(10):
            db.update_user_points(user_id, 0.1)
            db.increment_counter(user_id, "messages")

        # 2 аудиофайла
        for _ in range(2):
            db.update_user_points(user_id, 1.0)
            db.increment_counter(user_id, "music")

        # 5 реакций
        for _ in range(5):
            db.update_user_points(user_id, 0.1)
            db.increment_counter(user_id, "reactions")

        # Проверяем статистику
        user = db.get_user(user_id)
        assert user["messages_today"] == 10
        assert user["music_today"] == 2
        assert user["reactions_given_today"] == 5
        assert user["points"] == approx(3.5)

        # Проверяем статус лимитов
        limits = points_system.get_daily_limits_status(user_id)
        assert limits["text_messages_used"] == 10
        assert limits["music_files_used"] == 2
        assert limits["reactions_given_used"] == 5
        assert limits["points_total"] == approx(3.5)

    async def test_inactive_points_decay(self, integrated_systems):
        """
        Тест уменьшения баллов для неактивных Новичков (новая логика).
        """
        db = integrated_systems["db"]
        points_system = integrated_systems["points_system"]

        # Новичок с 5 баллами, без своей активности 25 часов
        newbie_id = 1004
        db.create_user(newbie_id, "inactive_newbie")
        db.update_user_points(newbie_id, 5.0)
        cursor = db.conn.cursor()
        old_time = (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE users SET last_self_activity = ? WHERE user_id = ?",
            (old_time, newbie_id),
        )
        db.conn.commit()

        # Стажёр с 15 баллами — больше не должен терять баллы (решение клиента)
        trainee_id = 1005
        db.create_user(trainee_id, "inactive_trainee")
        db.update_user_points(trainee_id, 15.0)
        cursor.execute(
            "UPDATE users SET rank = 'Стажёр', last_self_activity = ? "
            "WHERE user_id = ?",
            (old_time, trainee_id),
        )
        db.conn.commit()

        # Выполняем уменьшение баллов
        await points_system.decrease_inactive_points()

        # Проверяем результаты
        newbie = db.get_user(newbie_id)
        assert newbie["points"] == approx(4.0)  # 5.0 - 1

        trainee = db.get_user(trainee_id)
        assert trainee["points"] == approx(15.0)  # Стажёр больше не затухает

    def test_privileges_and_restrictions_by_rank(self, integrated_systems):
        """
        Тест привилегий и ограничений для каждого ранга.
        """
        rank_system = integrated_systems["rank_system"]

        # Тестируем каждый ранг
        ranks_data = [
            ("Новичок", 2, 6),
            ("Стажёр", 3, 2),
            ("Участник", 6, 1),
            ("Активист", 9, 1),
            ("Завсегдатай", 13, 0),
            ("Представитель", 16, 0),
            ("Легенда", 20, 0),
        ]

        for rank_name, min_privileges, min_restrictions in ranks_data:
            privileges = rank_system.get_user_privileges(rank_name)
            restrictions = get_user_restrictions(rank_name)

            assert len(privileges) >= min_privileges, (
                f"Ранг {rank_name} должен иметь минимум {min_privileges} привилегий"
            )

            if min_restrictions > 0:
                assert len(restrictions) >= min_restrictions, (
                    f"Ранг {rank_name} должен иметь минимум "
                    f"{min_restrictions} ограничений"
                )
            else:
                assert len(restrictions) == 0, (
                    f"Ранг {rank_name} не должен иметь ограничений"
                )

    def test_legend_rank_manual_assignment(self, integrated_systems):
        """
        Тест ручного присвоения ранга "Легенда".
        """
        db = integrated_systems["db"]

        # Создаем пользователя с достаточными баллами
        user_id = 1006
        username = "legend_candidate"
        db.create_user(user_id, username)
        db.update_user_points(user_id, 1500.0)

        user = db.get_user(user_id)
        assert user["rank"] == "Представитель"  # Автоматически не становится Легендой

        # Присваиваем ранг "Легенда" вручную (без контекста для теста)
        db.update_user_rank(user_id, "Легенда")

        user = db.get_user(user_id)
        assert user["rank"] == "Легенда"

        # Проверяем, что ранг не деградирует при потере баллов
        db.update_user_points(user_id, -1000.0)
        user = db.get_user(user_id)
        assert user["rank"] == "Легенда"  # Остается Легендой
        assert user["points"] == approx(500.0)

    def test_concurrent_users_activity(self, integrated_systems):
        """
        Тест одновременной активности нескольких пользователей.
        """
        db = integrated_systems["db"]

        # Создаем 10 пользователей
        user_ids = range(2001, 2011)
        for user_id in user_ids:
            db.create_user(user_id, f"user_{user_id}")

        # Симулируем активность каждого пользователя
        for user_id in user_ids:
            # Разное количество баллов для каждого
            points = (user_id - 2000) * 10.0
            db.update_user_points(user_id, points)

        # Проверяем топ пользователей
        top_users = db.get_top_users(10)
        assert len(top_users) == 10

        # Проверяем сортировку по баллам
        for i in range(len(top_users) - 1):
            assert top_users[i]["points"] >= top_users[i + 1]["points"]

        # Проверяем, что у каждого правильный ранг
        for user in top_users:
            user_data = db.get_user(user["user_id"])
            if user_data["points"] >= 100:
                assert user_data["rank"] in [
                    "Участник",
                    "Активист",
                    "Завсегдатай",
                    "Представитель",
                ]

    def test_edge_cases_rank_boundaries(self, integrated_systems):
        """
        Тест граничных случаев переходов между рангами.
        """
        db = integrated_systems["db"]

        # Тестируем граничные значения баллов
        test_cases = [
            (9.9, "Новичок"),
            (10.0, "Стажёр"),
            (10.1, "Стажёр"),
            (99.9, "Стажёр"),
            (100.0, "Участник"),
            (199.9, "Участник"),
            (200.0, "Активист"),
            (299.9, "Активист"),
            (300.0, "Завсегдатай"),
            (499.9, "Завсегдатай"),
            (500.0, "Представитель"),
            (999.9, "Представитель"),
            (1000.0, "Представитель"),
        ]

        for i, (points, expected_rank) in enumerate(test_cases):
            user_id = 3000 + i
            db.create_user(user_id, f"boundary_user_{i}")
            db.update_user_points(user_id, points)

            user = db.get_user(user_id)
            assert user["rank"] == expected_rank, (
                f"При {points} баллах ранг должен быть "
                f"{expected_rank}, но получен {user['rank']}"
            )
