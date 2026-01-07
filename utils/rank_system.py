import logging
from typing import Union

from telegram.ext import ContextTypes

from config import LOG_ENCODING, LOG_FORMAT, LOG_LEVEL, OWNER_ID, RANKS
from database import Database

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/rank_system.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def get_user_restrictions(rank_name: str) -> list:
    """
    Эта функция отвечает за получения ограничений для указанного ранга.
    Args:
        rank_name (str): Название ранга.
    Returns:
        list: Список ограничений.
    """
    restrictions = []

    if rank_name == "Новичок":
        restrictions.append("Нельзя скачивать файлы")
        restrictions.append("Нельзя приглашать участников")
        restrictions.append("Нельзя публиковать медиа (фото, видео, кружочки)")
        restrictions.append("Удаление ботом за 24 часа бездействия")
        restrictions.append("Баллы уменьшаются на 0.2 каждый час")
        restrictions.append("Нельзя рекламироваться в сообществе")

    elif rank_name == "Стажёр":
        restrictions.append("Удаление ботом за 3 дня бездействия")
        restrictions.append("Баллы уменьшаются на 0.1 каждый час")

    elif rank_name == "Участник":
        restrictions.append("Удаление за 7 дней бездействия")

    elif rank_name == "Активист":
        restrictions.append("Удаление за 1 месяц бездействия")

    # Для высших рангов ограничений нет
    return restrictions


def get_rank_by_points(points: float) -> str:
    """
    Эта функция отвечает за определения ранга на основе количества баллов.
    Args:
        points (float): Количество баллов пользователя.
    Returns:
        str: Название ранга.
    """
    for rank in reversed(RANKS):  # Проверяем от высшего к низшему
        if rank["name"] == "Легенда":
            # Выдается вручную
            continue
        if points >= rank["min_points"]:
            return rank["name"]
    return "Новичок"  # Дефолтный ранг


class RankSystem:
    """
    Класс для работы с ранговой системой. В системе рассмотрены следующие ранги:

    - Новичок
    - Стажёр
    - Участник
    - Активист
    - Завсегдатай
    - Представитель
    - Легенда (ручное присвоение)
    Attributes:
        db (Database): Класс для работы с базой данных.
        rank_mapping (dict[Any, Any | Any]): Словарь с определениями,
        ограничениями и атрибутами для каждого ранга.
    """

    def __init__(self, db: Database) -> None:
        """
        Конструктор класса системы рангов.
        Args:
            db (Database): Экземпляр класса Database для работы с базой данных.
        """
        self.db = db
        self.rank_mapping = {rank["name"]: rank for rank in RANKS}
        logger.info("RankSystem initialized successfully")

    def get_rank_details(self, rank_name: str) -> Union[dict | None]:
        """
        Этот метод получает детальную информацию о ранге.
        Args:
            rank_name (str): Название ранга.
        Returns:
            Union[dict | None]:
                - dict: Информация о ранге
                - None: если ранг не найден.
        """
        return self.rank_mapping.get(rank_name)

    def get_user_privileges(self, rank_name: str) -> list:
        """
        Этот метод получает привилегий для указанного ранга.
        Args:
            rank_name (str): Название ранга.
        Returns:
            list: Список привилегий для заданного ранга.
        """
        rank = self.get_rank_details(rank_name)
        if not rank:
            return []

        privileges = ["Писать текстовые сообщения", "Загружать музыку (mp3/wav)"]

        if rank_name in [
            "Стажёр",
            "Участник",
            "Активист",
            "Завсегдатай",
            "Представитель",
            "Легенда",
        ]:
            privileges.append("Предпросмотр ссылок в чате")

        if rank_name in [
            "Участник",
            "Активист",
            "Завсегдатай",
            "Представитель",
            "Легенда",
        ]:
            privileges.append("Голосовые сообщения")
            privileges.append("Отправка фотографий")
            privileges.append("Скачивание файлов из сообщества")

        if rank_name in ["Активист", "Завсегдатай", "Представитель", "Легенда"]:
            privileges.append("Создание опросов")
            privileges.append("Загрузка файлов")
            privileges.append("Приглашение участников через рекомендацию @ViceMGMT")

        if rank_name in ["Завсегдатай", "Представитель", "Легенда"]:
            privileges.append("Приглашение участников без согласования")
            privileges.append("Видео-сообщения")
            privileges.append("Отправка видео")
            privileges.append("Закрепление сообщений")

        if rank_name in ["Представитель", "Легенда"]:
            privileges.append("Отправка стикеров и гифок")
            privileges.append("Создание временных топиков для проектов")
            privileges.append("Участие в обсуждении нововведений сообщества")

        if rank_name == "Легенда":
            privileges.append("Кандидат на роль администратора")
            privileges.append("Доступ к элитному чату с ресурсами и плейсментами")
            privileges.append("Возможность стать амбассадором сообщества")
            privileges.append('Бесплатная реклама в топике "ВАЖНОЕ"')

        return privileges

    def update_user_rank(self, user_id: int) -> bool:
        """
        Этот метод обновляет ранг пользователя на основе текущих баллов.
        Args:
            user_id (int): ID пользователя.
        Returns:
            bool: `True` если ранг был обновлен, `False` если нет изменений или ошибка
        """
        # Пропускаем владельца до* вызова get_user
        if user_id == OWNER_ID:
            return False

        try:
            user = self.db.get_user(user_id)
            if not user:
                logger.warning(f"User not found for rank update: user_id={user_id}")
                return False

            current_rank = user["rank"]
            points = user["points"]

            # Определяем новый ранг
            new_rank = get_rank_by_points(points)

            # Если ранг не изменился, ничего не делаем
            if current_rank == new_rank:
                return False

            # Особый случай: ранг "Легенда" устанавливается вручную
            if new_rank == "Легенда" and current_rank != "Легенда":
                # Не обновляем автоматически, только через команду /legend
                logger.debug(
                    "Automatic rank update to 'Легенда' blocked "
                    f"for user_id={user_id}. Requires manual assignment."
                )
                return False

            # Легенда — навсегда
            if current_rank == "Легенда":
                return False

            # Обновляем ранг в базе данных
            self.db.update_user_rank(user_id, new_rank)
            logger.info(
                f"Rank updated: user_id={user_id}, old_rank='{current_rank}', "
                f"new_rank='{new_rank}', points={points}"
            )
            return True

        except Exception as e:
            logger.error(f"Error updating rank for user_id={user_id}: {e}")
            return False

    async def set_legend_rank(
        self, user_id: int, admin_id: int, context: ContextTypes.DEFAULT_TYPE = None
    ):
        """
        Этот метод реализует ручного присвоения ранга "Легенда".
        Args:
            user_id (int): ID пользователя.
            admin_id (int): ID администратора, выполняющего действие.
            context (ContextTypes, optional): Контекст для отправки уведомлений.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        try:
            user = self.db.get_user(user_id)
            if not user:
                logger.warning(f"User not found for legend rank: user_id={user_id}")
                return False

            # Пропускаем владельца
            if user_id == OWNER_ID:
                logger.warning(
                    f"Attempt to set legend rank for owner: user_id={user_id}"
                )
                return False

            current_rank = user["rank"]

            # Обновляем ранг на "Легенда"
            self.db.update_user_rank(user_id, "Легенда")

            # Запись в историю баллов (если реализовано в database.py)
            try:
                self.db.add_points_manually(user_id, 0, admin_id, "SET_LEGEND")
            except AttributeError:
                # Метод может отсутствовать в текущей версии database.py
                pass

            logger.info(
                f"Legend rank manually set: user_id={user_id}, "
                f"admin_id={admin_id}, old_rank='{current_rank}'"
            )

            # Отправка уведомления в топике "ВАЖНОЕ"
            if context:
                from config import CHAT_ID, TOPIC_IMPORTANT_ID

                try:
                    username = user["username"] or f"user{user_id}"
                    await context.bot.send_message(
                        chat_id=CHAT_ID,
                        message_thread_id=TOPIC_IMPORTANT_ID,
                        text=f"🎉 @{username} теперь легенда сообщества!",
                        parse_mode="HTML",
                    )
                    logger.info(
                        "Legend notification sent to "
                        f"IMPORTANT topic for user_id={user_id}"
                    )
                except Exception as e:
                    logger.error(f"Failed to send legend notification: {e}")
            return True

        except Exception as e:
            logger.error(f"Error setting legend rank for user_id={user_id}: {e}")
            if context:
                try:
                    await context.bot.send_message(
                        chat_id=OWNER_ID,
                        text=(
                            f"❌ <b>Ошибка при присвоении ранга 'Легенда'</b>\n\n"
                            f"👤 <b>Пользователь:</b> {user_id}\n"
                            f"❌ <b>Ошибка:</b> {str(e)[:200]}\n"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            return False

    async def unset_legend_rank(
        self, user_id: int, admin_id: int, context: ContextTypes.DEFAULT_TYPE = None
    ):
        """
        Этот метод реализует снятие ранга "Легенда" с возвратом ранга по баллам.
        Args:
            user_id (int): ID пользователя.
            admin_id (int): ID администратора, выполняющего действие.
            context (ContextTypes.DEFAULT_TYPE): Контекст для отправки уведомлений.
        Returns:
            bool: `True` если успешно, `False` если ошибка.
        """
        try:
            user = self.db.get_user(user_id)
            if not user:
                logger.warning(
                    f"User not found for unset legend rank: user_id={user_id}"
                )
                return False

            current_rank = user["rank"]
            points = user["points"]

            # Если пользователь не имеет ранга "Легенда", ничего не делаем
            if current_rank != "Легенда":
                logger.debug(
                    "User does not have legend rank: "
                    f"user_id={user_id}, current_rank='{current_rank}'"
                )
                return False

            # Определяем новый ранг на основе баллов
            # "Легенды" не будет
            new_rank = get_rank_by_points(points)

            # Обновляем ранг
            self.db.update_user_rank(user_id, new_rank)

            # Запись в историю баллов (если реализовано в database.py)
            try:
                self.db.add_points_manually(user_id, 0, admin_id, "UNSET_LEGEND")
            except AttributeError:
                pass

            logger.info(
                f"Legend rank unset: user_id={user_id}, admin_id={admin_id}, "
                f"new_rank='{new_rank}', points={points}"
            )

            # Отправка уведомления в топике "ВАЖНОЕ"
            if context:
                from config import CHAT_ID, TOPIC_IMPORTANT_ID

                try:
                    username = user["username"] or f"user{user_id}"
                    await context.bot.send_message(
                        chat_id=CHAT_ID,
                        message_thread_id=TOPIC_IMPORTANT_ID,
                        text=f"🔔 @{username} больше не носит звание Легенды.",
                        parse_mode="HTML",
                    )
                    logger.info(
                        "Unset legend notification sent to "
                        f"IMPORTANT topic for user_id={user_id}"
                    )
                except Exception as e:
                    logger.error(f"Failed to send unset legend notification: {e}")

            return True

        except Exception as e:
            logger.error(f"Error unsetting legend rank for user_id={user_id}: {e}")
            return False

    def get_rank_prefix(self, rank_name: str):
        """
        Этот метод получает префикс ранга для отображения в чате.
        Args:
            rank_name (str): Название ранга.
        Returns:
            str: Префикс с эмодзи.
        """
        rank = self.get_rank_details(rank_name)
        if rank and "emoji" in rank:
            return f"{rank['emoji']} {rank_name}"
        return rank_name

    def __str__(self):
        """
        Этот метод возвращает строковое представление системы для работы с рангами.
        Returns:
            str: Название класса.
        """
        return "RankSystem"
