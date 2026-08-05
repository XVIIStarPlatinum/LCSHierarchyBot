import os
import sys
from datetime import datetime, timedelta

import pytest

from utils.points_system import PointsSystem
from utils.rank_system import RankSystem, get_user_restrictions


@pytest.fixture(scope="function")
def integrated_db(tmp_path, monkeypatch):
    """
    Фикстура для интеграционных тестов с реальной базой данных.
    """
    # Test databases try not to cause a collision challenge (impossible)
    db_path = str(tmp_path / f"test_{id(tmp_path)}.db")
    monkeypatch.setattr("config.DATABASE_PATH", db_path)

    if "database" in sys.modules:
        del sys.modules["database"]
    if "utils.points_system" in sys.modules:
        del sys.modules["utils.points_system"]
    if "utils.rank_system" in sys.modules:
        del sys.modules["utils.rank_system"]

    from database import Database
    from utils.points_system import PointsSystem
    from utils.rank_system import RankSystem

    # Очищаем до теста
    if os.path.exists(db_path):
        os.remove(db_path)

    # Инициализируем базу данных
    db = Database(db_path)

    db._PointsSystem = PointsSystem
    db._RankSystem = RankSystem

    yield db

    try:
        db.conn.close()
    except Exception:
        pass

    # Очищаем после теста
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass


def test_full_user_lifecycle(integrated_db):
    """
    Демонстрационный тест: полный жизненный цикл пользователя
    Этот тест показывает, как система работает в реальном сценарии
    """
    # 1. Создание нового пользователя
    user_id = 12345
    username = "new_user"
    integrated_db.create_user(user_id, username)

    # Проверяем, что пользователь создан
    user = integrated_db.get_user(user_id)
    assert user is not None
    assert user["username"] == username
    assert user["rank"] == "Новичок"
    assert user["points"] == 0.0
    assert user["messages_today"] == 0

    print(f"Пользователь {username} успешно создан")

    # 2. Начисление баллов за активность
    points_system = PointsSystem(integrated_db)

    # Текстовые сообщения
    for i in range(5):  # 5 сообщений по 0.1 балла = 0.5 баллов
        points_system.db.update_user_points(user_id, 0.1)
        points_system.db.increment_counter(user_id, "messages")

    # Загрузка аудиофайла
    points_system.db.update_user_points(user_id, 1.0)
    points_system.db.increment_counter(user_id, "music")

    # Проверяем баллы
    user = integrated_db.get_user(user_id)
    assert user["points"] == 1.5  # 0.5 за сообщения + 1.0 за музыку
    assert user["messages_today"] == 5
    assert user["music_today"] == 1

    print(f"Баллы начислены: {user['points']} баллов всего")

    # 3. Автоматическое обновление ранга
    rank_system = RankSystem(integrated_db)
    rank_system.update_user_rank(user_id)

    user = integrated_db.get_user(user_id)
    assert user["rank"] == "Новичок"  # Все еще Новичок (нужно 10+ баллов для Стажёра)

    print(f"Ранг обновлен: пользователь теперь '{user['rank']}'")

    # 4. Достижение следующего ранга
    # Добавляем еще 9 баллов для перехода в Стажёры
    for _ in range(18):  # 18 * 0.5 = 9 баллов
        points_system.db.update_user_points(user_id, 0.5)

    rank_system.update_user_rank(user_id)
    user = integrated_db.get_user(user_id)
    assert user["rank"] == "Стажёр"

    print(f"Пользователь достиг ранга '{user['rank']}'")

    # 5. Проверка привилегий и ограничений
    privileges = rank_system.get_user_privileges(user["rank"])
    restrictions = get_user_restrictions(user["rank"])

    print("\nПривилегии пользователя:")
    for i, privilege in enumerate(privileges, 1):
        print(f"   {i}. {privilege}")

    print("\nОграничения пользователя:")
    if restrictions:
        for i, restriction in enumerate(restrictions, 1):
            print(f"   {i}. {restriction}")
    else:
        print("   Нет ограничений")

    # 6. Создание и сохранение сообщения бота в ЛС
    message_id = 1001
    chat_id = user_id  # ЛС с пользователем

    integrated_db.save_bot_message(message_id, chat_id, user_id)
    messages = integrated_db.get_user_bot_messages(user_id)

    assert len(messages) == 1
    assert messages[0]["message_id"] == message_id

    print("\nСообщение бота сохранено в ЛС пользователя")

    # 7. Имитация неактивности и проверка системы очистки
    old_activity = datetime.now() - timedelta(hours=25)  # 25 часов назад

    cursor = integrated_db.conn.cursor()
    cursor.execute(
        """
                   UPDATE users
                   SET last_activity = ?
                   WHERE user_id = ?
                   """,
        (old_activity.strftime("%Y-%m-%d %H:%M:%S"), user_id),
    )
    integrated_db.conn.commit()

    # Проверяем, что пользователь будет удален как неактивный Новичок
    inactive_users = integrated_db.get_inactive_users()
    user_ids = [u["user_id"] for u in inactive_users]
    assert user_id not in user_ids  # Стажёр + 25ч -> False

    # 7.5. А что если достаточно инактивил?
    really_old_activity = datetime.now() - timedelta(days=4)
    cursor.execute(
        """
                    UPDATE users
                    SET last_activity = ?
                    WHERE user_id = ?
                    """,
        (really_old_activity.strftime("%Y-%m-%d %H:%M:%S"), user_id),
    )
    integrated_db.conn.commit()

    inactive_users = integrated_db.get_inactive_users()
    user_ids = [u["user_id"] for u in inactive_users]
    assert user_id in user_ids  # Ну камон, 4 дня

    print(
        "Пользователь обнаружен как неактивный "
        f"(последняя активность: {old_activity.strftime('%H:%M:%S')})"
    )

    # 8. Имитация очистки - помечаем пользователя для удаления
    integrated_db.mark_user_for_deletion(user_id)
    user = integrated_db.get_user(user_id)
    assert user["rank"] == "УДАЛЕН"

    print(f"Пользователь помечен для удаления. Ранг изменен на '{user['rank']}'")

    # 9. Проверка статистики и отчетов
    top_users = integrated_db.get_top_users(10)
    assert len(top_users) <= 10  # Может быть меньше, если пользователь удален

    print(f"Топ пользователей обновлен. Всего в топе: {len(top_users)} пользователей")

    # 10. Финальная проверка целостности данных
    cursor.execute("PRAGMA integrity_check")
    integrity_result = cursor.fetchone()[0]
    assert integrity_result == "ok"
