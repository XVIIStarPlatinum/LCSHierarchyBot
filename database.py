import logging
import sqlite3
from datetime import datetime, timedelta

from config import (DATABASE_PATH, LOG_ENCODING, LOG_FORMAT, LOG_LEVEL,
                    OWNER_ID, OWNER_USERNAME)

COUNTER_MESSAGES = "messages"
COUNTER_MUSIC = "music"
COUNTER_REACTIONS = "reactions"

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/database.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def get_rank_requirements(rank_name: str) -> dict:
    """
    Эта функция возвращает требования для конкретного ранга.
    Args:
        rank_name (str): Название ранга.
    Returns:
         dict: Словарь с порогами баллов.
    """
    rank_requirements = {
        "Новичок": {"min_points": 0, "max_points": 9.9},
        "Стажёр": {"min_points": 10, "max_points": 99.9},
        "Участник": {"min_points": 100, "max_points": 199.9},
        "Активист": {"min_points": 200, "max_points": 299.9},
        "Завсегдатай": {"min_points": 300, "max_points": 499.9},
        "Представитель": {"min_points": 500, "max_points": 999.9},
        "Легенда": {"min_points": 1000, "max_points": float("inf")},
    }
    return rank_requirements.get(rank_name, {})


class Database:
    """
    Класс для работы с базой данных.
    Все необходимые информации для бота будут храниться в БД SQLite.
    В базе данных рассмотрены 3 таблиц:

    - users: пользователи
    - bot_messages: сообщения от бота
    - admins: админы

    Attributes:
        conn (Connection): Связь с БД для обеспечения SQLite соединения.
        COUNTER_QUERIES (dict): Предопределенные SQL-запросы для
        инкремента значений атрибутов пользователя.
        VERIFY_THRESHOLD (timedelta): Срок верификации пользователя
        после его вступления в группу.
    """

    def __init__(self, db_path: str = None) -> None:
        """
        Конструктор класса взаимодействия с базой данных.
        """
        try:

            self.DATABASE_PATH = db_path if db_path is not None else DATABASE_PATH
            self.conn = sqlite3.connect(self.DATABASE_PATH, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

            # Предопределенные SQL запросы для счетчиков.
            # А то нефиг писать одно и то же 3 раза
            self.COUNTER_QUERIES = {
                COUNTER_MESSAGES: """
                    UPDATE users
                    SET messages_today = messages_today + 1,
                    last_activity  = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """,
                COUNTER_MUSIC: """
                    UPDATE users
                    SET music_today = music_today + 1,
                    last_activity = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """,
                COUNTER_REACTIONS: """
                    UPDATE users
                    SET reactions_given_today = reactions_given_today + 1,
                    last_activity = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """,
            }

            self.COUNTER_LOGS = {
                COUNTER_MESSAGES: "Счетчик сообщений увеличен",
                COUNTER_MUSIC: "Счетчик музыки увеличен",
                COUNTER_REACTIONS: "Счетчик реакций увеличен",
            }
            self.VERIFY_THRESHOLD = timedelta(hours=24)  # 24 часа на верификацию
            self.create_tables()
            self.initialize_owner()
            self.create_indexes()
            logger.info(f"Database initialized successfully at {self.DATABASE_PATH}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def create_tables(self) -> None:
        """
        Этот метод создаёт таблицы для работы бота с базой данных SQLite.
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                points REAL DEFAULT 0.0,
                rank TEXT DEFAULT 'Новичок',
                last_activity TIMESTAMP,
                messages_today INTEGER DEFAULT 0,
                music_today INTEGER DEFAULT 0,
                reactions_given_today INTEGER DEFAULT 0,
                last_reset DATE
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_messages (
                message_id INTEGER,
                chat_id INTEGER,
                user_id INTEGER,
                is_start_command BOOLEAN DEFAULT 0,
                timestamp TIMESTAMP DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            )
        """
        )

        self.conn.commit()
        logger.info("All tables created successfully")

    def initialize_owner(self) -> None:
        """
        Этот метод добавляет владельца в таблицу
        пользователей на момент создания базы данных.
        """
        cursor = self.conn.cursor()
        today = datetime.now().date()
        cursor.execute(
            """
            INSERT OR IGNORE INTO users (
                user_id, username, points, rank, last_activity, last_reset
            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """,
            (OWNER_ID, OWNER_USERNAME, 9999.0, "Легенда", today),
        )

        cursor.execute(
            """
            INSERT OR IGNORE INTO admins (
                user_id, username
            ) VALUES (?, ?)
        """,
            (OWNER_ID, OWNER_USERNAME),
        )
        self.conn.commit()
        logger.info(
            "Owner initialized successfully as admin: "
            f"user_id={OWNER_ID}, username={OWNER_USERNAME}"
        )

    def create_indexes(self) -> None:
        """
        Этот метод создает индексы для оптимизации
        производительности часто используемых запросов.
        """
        cursor = self.conn.cursor()

        # Операций поиска
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_rank ON users(rank)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_last_activity ON users(last_activity)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_points ON users(points)")

        # Таблица bot_messages (потому что часто удаляются старые сообщения из лс)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS
                idx_bot_messages_user_id ON bot_messages(user_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS
                idx_bot_messages_timestamp ON bot_messages(timestamp)
        ''')

        # Таблица admins (поиск администраторов)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_admins_user_id ON admins(user_id)"
        )

        self.conn.commit()
        logger.info("Database indexes created successfully")

    def get_user(self, user_id: int) -> object:
        """
        Этот метод даёт возможность получить пользователя по ID.
        Args:
             user_id (int): ID пользователя.
        Returns:
            object: пользователь.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()

    def create_user(self, user_id: int, username: str = None) -> object:
        """Этот метод даёт возможность зарегистрировать нового пользователя.
        Args:
            user_id (int): ID пользователя из Telegram API.
            username (str, optional): Имя пользователя.
        Returns:
            object: Добавленный пользователь из вида базы данных."""
        cursor = self.conn.cursor()
        today = datetime.now().date()
        cursor.execute(
            """
            INSERT OR IGNORE INTO USERS (
                user_id, username, rank, last_reset
            ) VALUES (?, ?, 'Новичок', ?)
        """,
            (user_id, username, today),
        )

        self.conn.commit()
        logger.info(f"New user created: user_id={user_id}, username={username}")
        return self.get_user(user_id)

    def update_user_points(
        self, user_id: int, points: float, admin_id: int = None, reason: str = None
    ) -> bool:
        """Этот метод даёт возможность обновить
        пользовательские очки за один из совершенных действий:

        - отправка сообщения
        - отправка аудио-файла
        - реакция на сообщение.
        Args:
            user_id (int): ID пользователя.
            points (float): Количество баллов. Может принять отрицательные значения.
            admin_id (int, optional): ID админа, обновляющий баллы.
            reason (str, optional): Причина обновления баллов
            пользователя с заданным ID.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        cursor = self.conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        try:
            cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
            current = cursor.fetchone()
            if not current:
                self.conn.rollback()
                return False

            new_points = current["points"] + points

            cursor.execute(
                """
                UPDATE users
                SET points = ?,
                    last_activity = ?
                WHERE user_id = ?
            """,
                (new_points, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id),
            )
            self.conn.commit()
            logger.info(
                f"{points} points added to user_id={user_id} for "
                f"reason={reason}, total={new_points}"
            )
            self.update_user_ranks_by_points(user_id, new_points)
            return True
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error updating user_id={user_id} for user={user_id}: {e}")
            return False

    def increment_counter(self, user_id: int, counter_type: str) -> bool:
        """Этот метод универсально увеличивает счетчики действия пользователей.
        Args:
            user_id (int): ID пользователя.
            counter_type (str): Тип счетчика
            (COUNTER_MESSAGES, COUNTER_MUSIC, COUNTER_REACTIONS).
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        if counter_type not in self.COUNTER_QUERIES:
            valid_types = ", ".join(self.COUNTER_QUERIES.keys())
            logger.error(
                f"Invalid counter type: {counter_type}. Valid types are: {valid_types}"
            )
            return False

        try:
            cursor = self.conn.cursor()
            cursor.execute(self.COUNTER_QUERIES[counter_type], (user_id,))
            self.conn.commit()
            logger.info(f"{self.COUNTER_LOGS[counter_type]} for user_id={user_id}")
            return True
        except Exception as e:
            self.conn.rollback()
            logger.error(
                f"Error incrementing {counter_type} counter for user={user_id}: {e}"
            )
            return False

    def reset_daily_counters(self) -> bool:
        """
        Этот метод сбрасывает дневные счётчики для всех пользователей.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        cursor = self.conn.cursor()
        try:
            today = datetime.now().date().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                """
                UPDATE users
                SET messages_today = 0,
                    music_today = 0,
                    reactions_given_today = 0,
                    last_reset = ?
            """,
                (today,),
            )

            self.conn.commit()
            logger.info(f"Daily counters reset for all users at {today}")
            return True
        except Exception as e:
            self.conn.rollback()
            logger.exception("Failed to reset daily counters: %s", e)
            return False

    def update_user_rank(self, user_id: int, rank: str) -> bool:
        """
        Этот метод обновляет ранг пользователя.
        Args:
            user_id (int): ID пользователя.
            rank (str): Ранг пользователя.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE users SET rank = ?
            WHERE user_id = ?
        """,
            (rank, user_id),
        )
        self.conn.commit()
        logger.info(f"Rank updated for user_id={user_id}. New rank={rank}")
        return True

    def update_user_ranks_by_points(self, user_id: int, points: float = None) -> bool:
        """
        Этот метод обновляет ранг пользователя на основе его баллов.
        Args:
            user_id (int): ID пользователя.
            points (float, optional): Количество баллов пользователя.
            Не может принять отрицательные значения.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        cursor = self.conn.cursor()

        try:
            # Если баллы не переданы, получаем их из базы данных
            if points is None:
                cursor.execute(
                    "SELECT points, rank FROM users WHERE user_id = ?", (user_id,)
                )
                result = cursor.fetchone()

                if not result:
                    logger.warning(f"User not found for rank update: user_id={user_id}")
                    return False
                points = result["points"]
                current_rank = result["rank"]
            else:
                # Существует ли пользователь, когда хотим передать баллы им?
                cursor.execute("SELECT rank FROM users WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                if not result:
                    logger.warning(f"User not found for rank update: user_id={user_id}")
                    return False

                current_rank = result["rank"]

            if current_rank == "Легенда":
                logger.debug(f"User {user_id} is a Legend - skipping auto-update.")
                return False

            if points >= 500:
                new_rank = "Представитель"
            elif points >= 300:
                new_rank = "Завсегдатай"
            elif points >= 200:
                new_rank = "Активист"
            elif points >= 100:
                new_rank = "Участник"
            elif points >= 10:
                new_rank = "Стажёр"
            else:
                new_rank = "Новичок"

            if new_rank == current_rank:
                return False

            # Обновление ранга в базе данных
            cursor.execute(
                """
                UPDATE users
                SET rank = ?
                WHERE user_id = ?
            """,
                (new_rank, user_id),
            )

            affected_rows = cursor.rowcount
            self.conn.commit()

            if affected_rows > 0:
                logger.info(
                    f"Rank updated for user_id={user_id} on the "
                    f"basis of points={points}. New rank={new_rank}"
                )
                return True
            else:
                logger.warning(
                    f"No rows affected when updating rank for user_id={user_id}"
                )
                return False

        except Exception as e:
            logger.error(
                f"Error updating rank for user_id={user_id}: {str(e)}", exc_info=True
            )
            self.conn.rollback()
            return False

    def get_user_rank_position(self, user_id: int) -> int:
        """
        Этот метод получает позиции пользователя в рейтинге по баллам.
        Возвращает позицию пользователя (1 = самый высокий балл).
        Владелец не входит в рейтинге.
        Args:
            user_id (int): ID пользователя.

        Returns:
            int: Позиция в рейтинге (начиная с 1).
        """
        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                SELECT COUNT(*) + 1 as position
                FROM users
                WHERE points > (
                    SELECT points
                    FROM users
                    WHERE user_id = ?
                )
                AND user_id != ?
                AND rank != 'УДАЛЕН'
            """,
                (user_id, OWNER_ID),
            )

            result = cursor.fetchone()

            if result and result["position"]:
                return int(result["position"])
            else:
                cursor.execute(
                    """
                               SELECT COUNT(*) as total_users
                               FROM users
                               WHERE user_id != ?
                    AND rank != 'УДАЛЕН'
                               """,
                    (OWNER_ID,),
                )

                total_result = cursor.fetchone()
                if total_result and total_result["total_users"]:
                    return int(total_result["total_users"])
                return 1

        except Exception as e:
            logger.error(f"Error getting user rank position for user_id={user_id}: {e}")
            return 1

    def add_admin(self, user_id: int, username: str) -> bool:
        """
        Этот метод добавляет нового администратора.
        Args:
            user_id (int): ID пользователя.
            username (str): Имя пользователя.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        cursor = self.conn.cursor()

        cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            logger.warning(
                f"Admin with user_id={user_id} and username={username} already exists"
            )
            return False

        cursor.execute(
            """
            INSERT INTO admins (user_id, username)
            VALUES (?, ?)
        """,
            (user_id, username),
        )

        self.conn.commit()
        logger.info(f"Admin added: user_id={user_id}, username={username}")
        return True

    def remove_admin(self, user_id: int, username: str) -> bool:
        """
        Этот метод устраняет администратора от его должности, удалив его.
        Args:
            user_id (int): ID пользователя.
            username (str): Имя пользователя.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        cursor = self.conn.cursor()

        # А есть ли вообще такого админа?
        cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            logger.warning(f"Admin not found: user_id={user_id}")
            return False

        cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))

        self.conn.commit()
        logger.info(f"Admin removed: user_id={user_id}, username={username}")
        return True

    def is_admin(self, user_id: int) -> bool:
        """
        Этот метод проверяет, является ли пользователь админом.
        Args:
            user_id (int): ID пользователя.
        Returns:
            bool: `True` если есть админ с таким ID, `False` если нет.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        logger.info(f"Admin check: user_id={user_id}, is_admin={bool(result)}")
        return result is not None

    def get_all_admins(self) -> list:
        """
        Этот метод получает все администраторов в системе.
        Returns:
            list: Список админов в системе, включая владельца.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM admins")
        return cursor.fetchall()

    def save_bot_message(
        self,
        message_id: int,
        chat_id: int,
        user_id: int,
        is_start_command: bool = False,
    ) -> bool:
        """
        Этот метод сохраняет сообщение бота в ЛС.
        Args:
            message_id (int): ID сообщения.
            chat_id (int): ID чата.
            user_id (int): ID пользователя.
            is_start_command (bool): Является ли это ответом на /start?
        Returns:
            bool: `True` если сообщение сохранено, `False` если нет.
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO bot_messages (
                    message_id,
                    chat_id,
                    user_id,
                    is_start_command
                )
                VALUES (?, ?, ?, ?)
            """,
                (message_id, chat_id, user_id, 1 if is_start_command else 0),
            )
            if not getattr(self.conn, "in_transaction", False):
                self.conn.commit()
            logger.info(
                f"Bot message saved: message_id={message_id}, "
                f"chat_id={chat_id}, user_id={user_id}, "
                f"is_start_command={is_start_command}"
            )
            return True
        except Exception as e:
            logger.error(f"Error saving bot message for message_id={message_id}: {e}")
            return False

    def get_user_bot_messages(self, user_id: int, limit: int = 100) -> list:
        """
        Этот метод получает все сообщения бота для пользователя.
        Args:
            user_id (int): ID пользователя.
            limit (int): Предел количества возвращаемых сообщений.
        Returns:
            list: список сообщений, отправленный ботом пользователю.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT message_id, chat_id, user_id, is_start_command, timestamp
            FROM bot_messages
            WHERE user_id = ?
            ORDER BY timestamp DESC, message_id DESC
            LIMIT ?
        """,
            (user_id, limit),
        )
        return cursor.fetchall()

    def delete_bot_message(self, message_id: int, user_id: int) -> bool:
        """
        Этот метод удаляет сообщения бота из записей базы данных.
        Args:
            message_id (int): ID сообщения.
            user_id (int): ID пользователя.
        Returns:
            bool: `True` если сообщение удалено, `False` если нет.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            DELETE FROM bot_messages
            WHERE message_id = ? and user_id = ?
        """,
            (message_id, user_id),
        )

        self.conn.commit()
        logger.info(f"Bot message deleted: {message_id}, user_id={user_id}")
        return True

    def get_top_users(self, limit: int = 100) -> list:
        """
        Этот метод получает всех топ пользователей по баллам.
        Без указанного аргумента - топ 100.
        Args:
            limit (int, optional): размер отображаемой таблицы пользователей по баллам.
        Returns:
            list: таблица пользователей по баллам в виде списка (пользователь — баллы).
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                           SELECT user_id, username, points, rank
                           FROM users
                           WHERE user_id != ?
                             AND rank != 'УДАЛЕН'
                           ORDER BY CAST(points AS REAL) DESC, user_id
                           LIMIT ?
                           """,
                (OWNER_ID, limit),
            )
            rows = cursor.fetchall()
            res = []
            for r in rows:
                if isinstance(r, sqlite3.Row):
                    uid = r["user_id"]
                    uname = r["username"]
                    pts = float(r["points"])
                else:
                    uid, uname, pts = r[0], r[1], float(r[2])
                res.append(
                    {"user_id": uid, "username": uname, "points": pts, "rank": r[3]}
                )
            return res
        except Exception as e:
            logger.exception("Failed to get top users: %s", e)
            return []

    def get_users_by_rank(self, rank_name: str) -> list:
        """
        Этот метод возвращает всех пользователей определенного ранга.
        Args:
            rank_name (str): Название ранга.
        Returns:
            list: список пользователей с заданным рангом.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM users
            WHERE rank = ?
            ORDER BY points DESC
        """,
            (rank_name,),
        )
        return cursor.fetchall()

    def get_inactive_users(self) -> list:
        """
        Этот метод получает всех неактивных пользователей для удаления.
        Для каждого ранга действует своё правило по тому,
        какие пользователи считаются неактивными.
        Returns:
            list: Список неактивных пользователей.
        """
        cursor = self.conn.cursor()
        now = datetime.now()

        # Пороги бездействия (правила) для каждого ранга
        inactive_periods = {
            "Новичок": timedelta(hours=24),
            "Стажёр": timedelta(days=3),
            "Участник": timedelta(days=7),
            "Активист": timedelta(days=30),
        }

        conditions = []
        params = []

        for rank, period in inactive_periods.items():
            cutoff_time = now - period
            conditions.append("(rank = ? AND last_activity < ?)")
            params.extend((rank, cutoff_time))

        # Чтоб не втыкали админам и владельцу
        query = f"""
                    SELECT * FROM users
                    WHERE ({' OR '.join(conditions)})
                    AND user_id NOT IN (SELECT user_id FROM admins)
                    AND user_id != ?
                    ORDER BY last_activity
                """
        params.append(OWNER_ID)

        cursor.execute(query, params)
        return cursor.fetchall()

    def get_unverified_users(self) -> list:
        """
        Этот метод получает неверифицированных пользователей
        (нет записей в bot_messages за 24 часа).
        Returns:
            list: Список неверифицированных пользователей.
        """
        cursor = self.conn.cursor()
        cutoff_time = datetime.now() - self.VERIFY_THRESHOLD

        cursor.execute(
            """
            SELECT u.* FROM users u
            LEFT JOIN bot_messages b ON u.user_id = b.user_id AND b.timestamp > ?
            WHERE b.message_id IS NULL
                AND u.user_id != ?
                AND u.last_activity < ?
                AND u.user_id NOT IN (SELECT user_id FROM admins)
        """,
            (cutoff_time, OWNER_ID, cutoff_time),
        )

        return cursor.fetchall()

    def mark_user_for_deletion(self, user_id: int) -> bool:
        """
        Этот метод отмечает пользователя для удаления в целях аудита.
        Args:
            user_id (int): ID пользователя.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        if user_id == OWNER_ID:
            logger.warning("Attempt to mark owner for deletion ignored")
            return False
        cursor = self.conn.cursor()
        cursor.execute(
            """
                SELECT 1 FROM admins WHERE user_id = ?
                """,
            (user_id,),
        )
        if cursor.fetchone():
            logger.warning("Attempt to mark admin for deletion ignored")
            return False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Обновление ранга для пометки (т.н. Tombstoning)
        cursor.execute(
            """
            UPDATE users
            SET rank = 'УДАЛЕН',
            last_activity = ?
            WHERE user_id = ?
        """,
            (now, user_id),
        )

        self.conn.commit()
        logger.info(f"User marked for deletion: user_id={user_id}")
        return True

    def decrease_points_for_inactive(self) -> int:
        """
        Этот метод отвечает за реализацию уменьшения баллов для неактивных
        пользователей (т.е. Новичок и Стажёр).
        Returns:
            int: количество пользователей, у которых уменьшили баллы.
        """
        cursor = self.conn.cursor()
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Новички: -0.2 балла в час
        cursor.execute(
            """
                       UPDATE users
                       SET points = MAX(0, points - 0.2)
                       WHERE rank = 'Новичок'
                         AND last_activity < ?
                       """,
            (one_hour_ago,),
        )
        novice_count = cursor.rowcount

        # Стажёры: -0.1 балла в час
        cursor.execute(
            """
                       UPDATE users
                       SET points = MAX(0, points - 0.1)
                       WHERE rank = 'Стажёр'
                         AND last_activity < ?
                       """,
            (one_hour_ago,),
        )
        intern_count = cursor.rowcount

        affected_rows = novice_count + intern_count
        self.conn.commit()
        logger.info(
            f"Decreased points for {affected_rows} inactive users: "
            f"(Новичок: {novice_count}, Стажер: {intern_count})"
        )
        return affected_rows

    # Дальше методы только для админов
    def reset_inactivity_timer(self, user_id: int) -> bool:
        """
        Этот метод сбрасывает таймер неактивности для пользователя.
        Args:
            user_id (int): ID пользователя.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        cursor = self.conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """
            UPDATE users
            SET last_activity = ?
            WHERE user_id = ?
        """,
            (now, user_id),
        )

        self.conn.commit()
        logger.info(f"Inactivity timer reset for user_id={user_id}")
        return True

    def add_points_manually(
        self, user_id: int, points: float, admin_id: int, reason: str
    ) -> bool:
        """
        Этот метод реализует ручное добавление/снятие баллов с причиной.
        Args:
            user_id (int): ID пользователя.
            points (float): Количество баллов. Может принять отрицательные значения.
            admin_id (int): ID админа, обновляющий баллы.
            reason (str): Причина обновления баллов пользователя с заданным ID.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        return self.update_user_points(
            user_id, points, reason=f"MANUAL:{reason}", admin_id=admin_id
        )

    def set_legend_rank(self, user_id: int, admin_id: int) -> bool:
        """
        Этот метод предназначен для присваивания ранга 'Легенда'.
        Args:
            user_id (int): ID пользователя.
            admin_id (int): ID админа, обновляющий баллы.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
                       UPDATE users
                       SET rank = 'Легенда'
                       WHERE user_id = ?
                       """,
            (user_id,),
        )

        self.conn.commit()
        logger.info(f"Legend rank set for user_id={user_id} by admin_id={admin_id}")
        return True

    def unset_legend_rank(self, user_id: int, admin_id: int) -> bool:
        """
        Этот метод предназначен для снятия ранги 'Легенда'.
        Args:
            user_id (int): ID пользователя.
            admin_id (int): ID админа, обновляющий баллы.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        cursor = self.conn.cursor()

        cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

        if not result:
            return False

        points = result["points"]

        cursor.execute(
            """
            UPDATE users
            SET rank = 'Представитель'
            WHERE user_id = ?
        """,
            (user_id,),
        )

        self.update_user_ranks_by_points(user_id, points)

        self.conn.commit()
        logger.info(f"Legend rank unset for user_id={user_id} by admin_id={admin_id}")
        return True

    def close(self) -> None:
        """Этот метод закрывает соединения с базой данных."""
        try:
            self.conn.close()
            logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error when attempting to close database connection: {e}")

    def __str__(self):
        """
        Этот метод возвращает строковое представление системы для работы с базой данных.
        Returns:
            str: Название класса.
        """
        return "Database"
