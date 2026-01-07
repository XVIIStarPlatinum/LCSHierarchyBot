import os
import sys
from typing import Any, Generator

import pytest

from config import OWNER_ID, OWNER_USERNAME
from database import Database


def ensure_directories():
    directories = ['logs', 'database']
    for directory in directories:
        os.makedirs(directory, exist_ok=True)


ensure_directories()


@pytest.fixture(scope="function")
def test_db_path(tmp_path) -> str:
    """
    Фикстура пути к тестовой базе данных.
    """
    return str(tmp_path / "test_hierarchy.db")


@pytest.fixture(scope="function")
def db(test_db_path: str, monkeypatch) -> Generator[Database, Any, None]:
    """
    Фикстура базы данных с очисткой после каждого теста.
    """
    # Удаляем существующую базу если есть
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    monkeypatch.setattr("config.DATABASE_PATH", test_db_path)

    if "database" in sys.modules:
        del sys.modules["database"]

    from database import Database

    # Создаем новую базу
    db = Database()
    yield db

    try:
        db.conn().close()
    except Exception:
        pass
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except Exception:
            pass


@pytest.fixture
def sample_user(db):
    """
    Фикстура примера пользователя.
    """
    user_id = 123
    username = "testuser"
    db.create_user(user_id, username)
    return {"user_id": user_id, "username": username}


@pytest.fixture
def admin_user(db: Database) -> dict:
    """
    Фикстура администратора.
    """
    admin_id = 999
    admin_username = "admin"
    db.create_user(admin_id, admin_username)
    db.add_admin(admin_id, admin_username)
    return {"user_id": admin_id, "username": admin_username}


@pytest.fixture
def owner_user(db: Database) -> dict:
    """
    Фикстура владельца.
    """
    owner_id = OWNER_ID
    owner_username = OWNER_USERNAME

    # Владелец уже* в таблице админов
    return {"user_id": owner_id, "username": owner_username}
