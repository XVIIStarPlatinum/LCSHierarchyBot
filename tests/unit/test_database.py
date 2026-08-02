import sqlite3
from datetime import datetime, timedelta

from config import OWNER_ID, OWNER_USERNAME


class TestDatabase:
    """
    Тесты для базы данных.
    """

    def test_table_creation(self, db):
        """
        Тест создания всех таблиц.
        """
        cursor = db.conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        assert cursor.fetchone() is not None

        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        required_columns = [
            "user_id",
            "username",
            "points",
            "rank",
            "last_activity",
            "messages_today",
            "music_today",
            "reactions_given_today",
            "last_reset",
        ]
        assert all(col in columns for col in required_columns)

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_messages'"
        )
        assert cursor.fetchone() is not None

        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(bot_messages)")
        columns = [col[1] for col in cursor.fetchall()]
        required_columns = ["message_id", "chat_id", "user_id", "timestamp"]
        assert all(col in columns for col in required_columns)

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='admins'"
        )
        assert cursor.fetchone() is not None

        cursor.execute("PRAGMA table_info(admins)")
        columns = [col[1] for col in cursor.fetchall()]
        required_columns = ["user_id", "username"]
        assert all(col in columns for col in required_columns)

    def test_user_creation_and_retrieval(self, db, sample_user):
        """
        Тест создания и получения пользователя.
        """
        user_id = sample_user["user_id"]
        username = sample_user["username"]

        user = db.get_user(user_id)
        assert user is not None
        assert user["user_id"] == user_id
        assert user["username"] == username
        assert user["points"] == 0.0
        assert user["rank"] == "Новичок"
        assert user["messages_today"] == 0
        assert user["music_today"] == 0
        assert user["reactions_given_today"] == 0

    def test_owner_initialization(self, db):
        """
        Тест автоматического добавления владельца в БД.
        """
        owner = db.get_user(OWNER_ID)
        assert owner is not None
        assert owner["username"] == OWNER_USERNAME
        assert owner["rank"] == "Легенда"
        assert owner["points"] == 9999

        # Владелец должен быть в таблице админов
        cursor = db.conn.cursor()
        cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (OWNER_ID,))
        assert cursor.fetchone() is not None

    def test_points_update(self, db, sample_user):
        """
        Тест обновления баллов для пользователей при определенных действиях.
        """
        user_id = sample_user["user_id"]
        initial_points = 10.0
        db.update_user_points(user_id, initial_points)

        user = db.get_user(user_id)
        assert user["points"] == initial_points
        additional_points = 5.5
        db.update_user_points(user_id, additional_points)

        user = db.get_user(user_id)
        assert user["points"] == initial_points + additional_points

    def test_daily_counters(self, db, sample_user):
        """
        Тест сброса дневных счетчиков.
        """
        user_id = sample_user["user_id"]

        cursor = db.conn.cursor()
        cursor.execute(
            """
                       UPDATE users
                       SET messages_today        = 10,
                           music_today           = 2,
                           reactions_given_today = 5
                       WHERE user_id = ?
                       """,
            (user_id,),
        )
        db.conn.commit()

        user = db.get_user(user_id)
        assert user["messages_today"] == 10
        assert user["music_today"] == 2
        assert user["reactions_given_today"] == 5

        db.reset_daily_counters()
        user = db.get_user(user_id)
        assert user["messages_today"] == 0
        assert user["music_today"] == 0
        assert user["reactions_given_today"] == 0

    def test_rank_update_by_points(self, db, sample_user):
        """
        Тест автоматического обновления ранга по баллам.
        """
        user_id = sample_user["user_id"]

        # Граничные кейсы е-баллов
        test_cases = [
            (0, "Новичок"),
            (9.9, "Новичок"),
            (10, "Стажёр"),
            (99.9, "Стажёр"),
            (100, "Участник"),
            (199.9, "Участник"),
            (200, "Активист"),
            (299.9, "Активист"),
            (300, "Завсегдатай"),
            (499.9, "Завсегдатай"),
            (500, "Представитель"),
            (999.9, "Представитель"),
            (1000, "Представитель"),
        ]

        for points, expected_rank in test_cases:
            # Обновляем баллы
            db.update_user_points(user_id, points - db.get_user(user_id)["points"])

            # Проверяем ранг
            user = db.get_user(user_id)
            assert user["rank"] == expected_rank, (
                f"Failed for points={points}, expected={expected_rank},"
                f" got={user['rank']}"
            )

    def test_admin_management(self, db, sample_user):
        """
        Тест управления администраторами.
        """
        user_id = sample_user["user_id"]
        username = sample_user["username"]

        # Проверка, что пользователь не админ
        assert not db.is_admin(user_id)

        # Добавление админа
        result = db.add_admin(user_id, username)
        assert result is True

        # Проверка, что пользователь стал админом
        assert db.is_admin(user_id)

        # Получение всех админов
        admins = db.get_all_admins()
        assert len(admins) >= 1  # Владелец + новый админ
        assert any(admin["user_id"] == user_id for admin in admins)

        # Удаление админа
        result = db.remove_admin(user_id, username)
        assert result is True

        # Проверка, что пользователь больше не админ
        assert not db.is_admin(user_id)

    def test_bot_messages_management(self, db, sample_user):
        """
        Тест работы с сообщениями бота в ЛС.
        """
        user_id = sample_user["user_id"]

        import time

        messages = []
        for i in range(1, 4):
            db.save_bot_message(i, user_id, user_id)
            messages.append({"message_id": i, "chat_id": user_id})
            time.sleep(0.01)  # Чтобы были разные времени

        # Получение сообщений
        user_messages = db.get_user_bot_messages(user_id)
        assert len(user_messages) == len(messages)

        # Проверка порядка (новые первыми)
        assert user_messages[0]["message_id"] == 3
        assert user_messages[1]["message_id"] == 2
        assert user_messages[2]["message_id"] == 1

        # Удаление одного сообщения
        db.delete_bot_message(2, user_id)

        # Проверка после удаления
        user_messages = db.get_user_bot_messages(user_id)
        assert len(user_messages) == 2
        assert all(msg["message_id"] != 2 for msg in user_messages)

    def test_inactive_users_retrieval(self, db):
        """
        Тест получения неактивных пользователей.
        """
        # Создаем пользователей с разными рангами и временем активности
        now = datetime.now()
        test_users = [
            {  # Новичок - должен быть в списке (активность 25 часов назад)
                "user_id": 101,
                "username": "inactive_newbie",
                "rank": "Новичок",
                "last_activity": now - timedelta(hours=25),
                "points": 5.0,
            },
            {  # Стажёр - должен быть в списке (активность 4 дня назад)
                "user_id": 102,
                "username": "inactive_trainee",
                "rank": "Стажёр",
                "last_activity": now - timedelta(days=4),
                "points": 15.0,
            },
            {  # Участник - должен быть в списке (активность 8 дней назад)
                "user_id": 103,
                "username": "inactive_member",
                "rank": "Участник",
                "last_activity": now - timedelta(days=8),
                "points": 105.0,
            },
            {  # Активист - должен быть в списке (активность 31 день назад)
                "user_id": 104,
                "username": "inactive_activist",
                "rank": "Активист",
                "last_activity": now - timedelta(days=31),
                "points": 205.0,
            },
            {  # Завсегдатай - НЕ должен быть в списке (даже при неактивности)
                "user_id": 105,
                "username": "inactive_regular",
                "rank": "Завсегдатай",
                "last_activity": now - timedelta(days=100),
                "points": 305.0,
            },
            {  # Админ - НЕ должен быть в списке
                "user_id": 106,
                "username": "inactive_admin",
                "rank": "Участник",
                "last_activity": now - timedelta(days=10),
                "points": 105.0,
            },
            {  # Владелец - НЕ должен быть в списке
                "user_id": OWNER_ID,
                "username": OWNER_USERNAME,
                "rank": "Легенда",
                "last_activity": now - timedelta(days=100),
                "points": 9999.0,
            },
            {  # Активный новичок - НЕ должен быть в списке
                "user_id": 108,
                "username": "active_newbie",
                "rank": "Новичок",
                "last_activity": now - timedelta(hours=1),
                "points": 5.0,
            },
        ]

        # Создаем тестовых пользователей
        for user_data in test_users:
            if user_data["user_id"] == OWNER_ID:
                continue  # Владелец уже создан автоматически

            db.create_user(user_data["user_id"], user_data["username"])
            cursor = db.conn.cursor()
            cursor.execute(
                """
                           UPDATE users
                           SET rank          = ?,
                               points        = ?,
                               last_activity = ?
                           WHERE user_id = ?
                           """,
                (
                    user_data["rank"],
                    user_data["points"],
                    user_data["last_activity"].strftime("%Y-%m-%d %H:%M:%S"),
                    user_data["user_id"],
                ),
            )
            db.conn.commit()

            # Если это админ, добавляем в таблицу админов
            if user_data["user_id"] == 106:
                db.add_admin(user_data["user_id"], user_data["username"])

        # Получаем неактивных пользователей
        inactive_users = db.get_inactive_users()

        # Проверяем результат
        inactive_ids = [user["user_id"] for user in inactive_users]

        # Должны быть в списке
        assert 101 in inactive_ids  # Новичок
        assert 102 in inactive_ids  # Стажёр
        assert 103 in inactive_ids  # Участник
        assert 104 in inactive_ids  # Активист

        # Не должны быть в списке
        assert 105 not in inactive_ids  # Завсегдатай
        assert 106 not in inactive_ids  # Админ
        assert OWNER_ID not in inactive_ids  # Владелец
        assert 108 not in inactive_ids  # Активный пользователь

    def test_mark_user_for_deletion(self, db, sample_user):
        """
        Тест пометки пользователя для удаления.
        """
        user_id = sample_user["user_id"]

        # Помечаем пользователя для удаления
        db.mark_user_for_deletion(user_id)

        # Проверяем изменение ранга
        user = db.get_user(user_id)
        assert user["rank"] == "УДАЛЕН"

        # Проверяем обновление времени активности
        last_activity = datetime.strptime(user["last_activity"], "%Y-%m-%d %H:%M:%S")
        # Менее минуты назад
        assert (datetime.now() - last_activity).total_seconds() < 60

    def test_unverified_users(self, db):
        """
        Тест получения неверифицированных пользователей.
        """
        now = datetime.now()
        cutoff_time = now - timedelta(hours=24)

        # Создаем верифицированного пользователя (есть сообщения бота)
        verified_user_id = 201
        db.create_user(verified_user_id, "verified_user")
        db.save_bot_message(1, verified_user_id, verified_user_id)

        # Создаем неверифицированного пользователя (нет сообщений бота)
        unverified_user_id = 202
        db.create_user(unverified_user_id, "unverified_user")
        cursor = db.conn.cursor()
        cursor.execute(
            """
                       UPDATE users
                       SET last_activity = ?
                       WHERE user_id = ?
                       """,
            (cutoff_time.strftime("%Y-%m-%d %H:%M:%S"), unverified_user_id),
        )
        db.conn.commit()

        # Создаем неверифицированного админа (не должен попадать в список)
        admin_user_id = 203
        db.create_user(admin_user_id, "admin_user")
        cursor.execute(
            """
                       UPDATE users
                       SET last_activity = ?
                       WHERE user_id = ?
                       """,
            (cutoff_time.strftime("%Y-%m-%d %H:%M:%S"), admin_user_id),
        )
        db.conn.commit()
        db.add_admin(admin_user_id, "admin_user")

        # Получаем неверифицированных пользователей
        unverified_users = db.get_unverified_users()

        # Проверяем результат
        unverified_ids = [user["user_id"] for user in unverified_users]
        assert unverified_user_id in unverified_ids
        assert verified_user_id not in unverified_ids
        assert admin_user_id not in unverified_ids

    def test_decrease_points_for_inactive(self, db):
        """
        Тест уменьшения баллов для неактивных Новичков (новая логика:
        только Новичок, триггер — last_self_activity старше 24ч,
        плоское -1 за вызов).
        """
        now = datetime.now()
        inactive_time = now - timedelta(hours=25)

        # Создаем пользователей с разными рангами
        test_users = [
            {  # Новичок - должен потерять 1 балл
                "user_id": 301,
                "username": "newbie",
                "rank": "Новичок",
                "points": 10.0,
                "last_self_activity": inactive_time,
            },
            {  # Стажёр - больше не теряет баллы (решение клиента)
                "user_id": 302,
                "username": "trainee",
                "rank": "Стажёр",
                "points": 20.0,
                "last_self_activity": inactive_time,
            },
            {  # Участник - не должен потерять баллы
                "user_id": 303,
                "username": "member",
                "rank": "Участник",
                "points": 100.0,
                "last_self_activity": inactive_time,
            },
            {  # Владелец - не должен потерять баллы
                "user_id": OWNER_ID,
                "username": OWNER_USERNAME,
                "rank": "Легенда",
                "points": 9999.0,
                "last_self_activity": inactive_time,
            },
        ]

        # Создаем тестовых пользователей
        for user_data in test_users:
            if user_data["user_id"] == OWNER_ID:
                continue  # Владелец уже создан

            db.create_user(user_data["user_id"], user_data["username"])
            cursor = db.conn.cursor()
            cursor.execute(
                """
                           UPDATE users
                           SET rank = ?,
                               points = ?,
                               last_self_activity = ?
                           WHERE user_id = ?
                           """,
                (
                    user_data["rank"],
                    user_data["points"],
                    user_data["last_self_activity"].strftime("%Y-%m-%d %H:%M:%S"),
                    user_data["user_id"],
                ),
            )
            db.conn.commit()

        # Уменьшаем баллы для неактивных
        affected_count = db.decrease_points_for_inactive()
        # Проверяем результат
        assert affected_count == 1  # Только Новичок

        # Проверяем баллы Новичка
        newbie = db.get_user(301)
        assert abs(newbie["points"] - 9.0) < 0.01  # 10.0 - 1

        # Проверяем баллы Стажёра (больше не уменьшаются)
        trainee = db.get_user(302)
        assert trainee["points"] == 20.0

        # Проверяем баллы Участника (не должны измениться)
        member = db.get_user(303)
        assert member["points"] == 100.0

        # Владелец не должен потерять баллы
        owner = db.get_user(OWNER_ID)
        assert owner["points"] == 9999.0

        # Второй забег (ещё одни "сутки" без активности) — компаундится
        affected_count_2 = db.decrease_points_for_inactive()
        assert affected_count_2 == 1

        newbie = db.get_user(301)
        assert abs(newbie["points"] - 8.0) < 0.01

        # Могут ли баллы уменьшиться ниже 0? Нет конечно
        low_points_user_id = 305
        db.create_user(low_points_user_id, "low_points")
        cursor = db.conn.cursor()
        cursor.execute(
            """
            UPDATE users
            SET rank = 'Новичок',
                points = 0.5,
                last_self_activity = ?
            WHERE user_id = ?
        """,
            (inactive_time.strftime("%Y-%m-%d %H:%M:%S"), low_points_user_id),
        )
        db.conn.commit()

        db.decrease_points_for_inactive()
        low_points = db.get_user(low_points_user_id)
        assert low_points["points"] == 0.0  # max(0, 0.5 - 1) -> 0

        # Новичок, который недавно писал/реагировал сам (last_self_activity
        # свежий), не должен терять баллы, даже если last_activity (который
        # также обновляется при ПОЛУЧЕНИИ реакции) старый — это и есть
        # ключевое отличие новой логики.
        recently_self_active_id = 306
        db.create_user(recently_self_active_id, "recently_active")
        cursor.execute(
            """
            UPDATE users
            SET rank = 'Новичок',
                points = 5.0,
                last_activity = ?,
                last_self_activity = ?
            WHERE user_id = ?
        """,
            (
                inactive_time.strftime("%Y-%m-%d %H:%M:%S"),  # старый last_activity
                now.strftime("%Y-%m-%d %H:%M:%S"),  # свежий last_self_activity
                recently_self_active_id,
            ),
        )
        db.conn.commit()

        db.decrease_points_for_inactive()
        recently_active = db.get_user(recently_self_active_id)
        assert recently_active["points"] == 5.0  # не должно уменьшиться

    def test_transaction_rollback(self, db, sample_user):
        """
        Тест отката транзакций при ошибках.
        """
        user_id = sample_user["user_id"]

        # Начальное состояние
        initial_points = 50.0
        db.update_user_points(user_id, initial_points)

        # Симулируем ошибку в середине транзакции
        try:
            cursor = db.conn.cursor()
            # Начинаем транзакцию
            cursor.execute("BEGIN TRANSACTION")

            # Обновляем баллы
            cursor.execute(
                """
                           UPDATE users
                           SET points = points + 10
                           WHERE user_id = ?
                           """,
                (user_id,),
            )

            # Симулируем ошибку
            raise Exception("Simulated database error")

            # Коммитим транзакцию (никогда не выполнится)
            cursor.execute("COMMIT")

        except Exception:
            # Откатываем транзакцию
            cursor.execute("ROLLBACK")

        # Проверяем, что данные не изменились
        user = db.get_user(user_id)
        assert user["points"] == initial_points

    def test_database_backup_and_restore(self, db, tmp_path):
        """
        Тест резервного копирования и восстановления базы данных.
        """
        # Создаем тестовые данные
        test_users = [
            {"user_id": 501, "username": "user1", "points": 10.0, "rank": "Новичок"},
            {"user_id": 502, "username": "user2", "points": 20.0, "rank": "Стажёр"},
            {"user_id": 503, "username": "user3", "points": 100.0, "rank": "Участник"},
        ]

        for user_data in test_users:
            db.create_user(user_data["user_id"], user_data["username"])
            cursor = db.conn.cursor()
            cursor.execute(
                """
                           UPDATE users
                           SET points = ?,
                               rank   = ?
                           WHERE user_id = ?
                           """,
                (user_data["points"], user_data["rank"], user_data["user_id"]),
            )
            db.conn.commit()

        # Создаем резервную копию
        backup_path = tmp_path / "backup.db"
        with open(db.DATABASE_PATH, "rb") as src, open(backup_path, "wb") as dst:
            dst.write(src.read())

        # Повреждаем оригинальную базу
        db.conn.close()
        with open(db.DATABASE_PATH, "w") as f:
            f.write("CORRUPTED DATABASE")

        # Восстанавливаем из резервной копии
        with open(backup_path, "rb") as src, open(db.DATABASE_PATH, "wb") as dst:
            dst.write(src.read())

        # Пересоздаем соединение
        db.conn = sqlite3.connect(db.DATABASE_PATH, check_same_thread=False)
        db.conn.row_factory = sqlite3.Row

        # Проверяем восстановленные данные
        for user_data in test_users:
            user = db.get_user(user_data["user_id"])
            assert user is not None
            assert user["username"] == user_data["username"]
            assert user["points"] == user_data["points"]
            assert user["rank"] == user_data["rank"]

    def test_cleanup_old_bot_messages(self, db, sample_user):
        """
        Тест очистки старых сообщений бота.
        """
        user_id = sample_user["user_id"]

        # Сохраняем несколько сообщений
        for i in range(5):
            is_start = i == 0
            db.save_bot_message(i + 1, user_id, user_id, is_start_command=is_start)

        # Проверяем, что все сообщения сохранены
        messages = db.get_user_bot_messages(user_id)
        assert len(messages) == 5

        # БД не отвечает за очистку, только хранение.
        # Поэтому будем имитировать логику cleanup_handler
        messages_to_keep = []
        if messages:
            messages_to_keep.append(messages[0])

        for msg in messages:
            msg_dict = dict(msg)
            if msg_dict.get("is_start_command"):
                already_kept = any(
                    kept["message_id"] == msg["message_id"] for kept in messages_to_keep
                )
                if not already_kept:
                    messages_to_keep.append(msg)

        messages_to_delete = [
            m
            for m in messages
            if not any(
                kept["message_id"] == m["message_id"] for kept in messages_to_keep
            )
        ]
        for msg in messages_to_delete:
            db.delete_bot_message(msg["message_id"], user_id)

        messages = db.get_user_bot_messages(user_id)
        assert len(messages) == 2

    def test_get_top_users(self, db):
        """
        Тест получения топ пользователей.
        """
        # Создаем пользователей с разными баллами.
        # Владелец должен быть исключен
        test_users = [
            {
                "user_id": 601,
                "username": "top1",
                "points": 1000.0,
                "rank": "Представитель",
            },
            {
                "user_id": 602,
                "username": "top2",
                "points": 500.0,
                "rank": "Представитель",
            },
            {
                "user_id": 603,
                "username": "top3",
                "points": 300.0,
                "rank": "Завсегдатай",
            },
            {"user_id": 604, "username": "top4", "points": 200.0, "rank": "Активист"},
        ]

        for user_data in test_users:
            db.create_user(user_data["user_id"], user_data["username"])
            cursor = db.conn.cursor()
            cursor.execute(
                """
                UPDATE users
                SET points = ?, rank = ?
                WHERE user_id = ?
            """,
                (user_data["points"], user_data["rank"], user_data["user_id"]),
            )
            db.conn.commit()

        # Получаем топ-3 пользователей
        top_users = db.get_top_users(3)

        # Проверяем результат
        assert len(top_users) == 3
        assert top_users[0]["points"] >= top_users[1]["points"]
        assert top_users[1]["points"] >= top_users[2]["points"]

        assert top_users[0]["user_id"] == 601

        # Владелец исключен?
        assert all(user["user_id"] != OWNER_ID for user in top_users)

    def test_reset_inactivity_timer(self, db, sample_user):
        """
        Тест сброса таймера неактивности.
        """
        user_id = sample_user["user_id"]

        # Устанавливаем старое время активности
        old_activity = datetime.now() - timedelta(days=10)
        cursor = db.conn.cursor()
        cursor.execute(
            """
                       UPDATE users
                       SET last_activity = ?
                       WHERE user_id = ?
                       """,
            (old_activity.strftime("%Y-%m-%d %H:%M:%S"), user_id),
        )
        db.conn.commit()

        # Проверяем старое время
        user = db.get_user(user_id)
        old_last_activity = datetime.strptime(
            user["last_activity"], "%Y-%m-%d %H:%M:%S"
        )
        assert old_last_activity < datetime.now() - timedelta(days=1)

        # Сбрасываем таймер
        db.reset_inactivity_timer(user_id)

        # Проверяем новое время
        user = db.get_user(user_id)
        new_last_activity = datetime.strptime(
            user["last_activity"], "%Y-%m-%d %H:%M:%S"
        )
        assert (datetime.now() - new_last_activity).total_seconds() < 60
