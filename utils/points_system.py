import logging
from datetime import datetime, timedelta
from typing import Any, Union

from telegram.ext import Application, ContextTypes

from config import (LOG_ENCODING, LOG_FORMAT, LOG_LEVEL, POINTS_CONFIG,
                    SCHEDULED_TASKS)
from database import Database
from utils.helpers import notify_owner_error

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/points_system.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class PointsSystem:
    """
    Класс для работы с системой баллов. Здесь рассмотрены
    ручные и автоматические средства обновления баллов пользователя.
    Attributes:
        db (Database): Класс для работы с базой данных.
    """

    def __init__(self, db: Database) -> None:
        """
        Конструктор класса системы начисления баллов.
        Args:
            db (Database): Экземпляр класса Database для работы с базой данных.
        """
        self.db = db
        logger.info("PointsSystem initialized successfully")

    async def reset_daily_limits(
        self, context: ContextTypes.DEFAULT_TYPE = None
    ) -> None:
        """
        Сброс дневных лимитов.
        Выполняется каждые 24 часа для всех пользователей.
        Args:
            context (ContextTypes, optional): Контекст приложения.
        """
        try:
            self.db.reset_daily_counters()
            logger.info("Daily limits reset completed for all users")
        except Exception as e:
            logger.error(f"Error during daily limits reset: {e}")
            if context:
                await notify_owner_error(context, e)

    async def decrease_inactive_points(
        self, context: ContextTypes.DEFAULT_TYPE = None
    ) -> None:
        """
        Уменьшение баллов для неактивных пользователей.
        Выполняется каждый час:

        - Для ранга 'Новичок': -0.2 балла в час
        - Для ранга 'Стажёр': -0.1 балла в час
        Args:
            context (ContextTypes, optional): Контекст приложения.
        """
        try:
            affected_count = self.db.decrease_points_for_inactive()
            if affected_count > 0:
                logger.info(f"Decreased points for {affected_count} inactive users")
        except Exception as e:
            logger.error(f"Error during inactive points decrease: {e}")
            if context:
                await notify_owner_error(context, e)

    def get_daily_limits_status(self, user_id: int) -> Union[dict[str, Any] | None]:
        """
        Получение статуса дневных лимитов пользователя.
        Args:
            user_id (int): ID пользователя.
        Returns:
            Union[dict[str, Any] | None]:
                - dict[str | Any]: Словарь с текущим состоянием лимитов.
                - None: Если нет такого пользователя.
        """
        user = self.db.get_user(user_id)
        if not user:
            return None

        return {
            "text_messages_used": user["messages_today"],
            "text_messages_limit": POINTS_CONFIG["text_message"][
                "max_messages_per_day"
            ],
            "text_points_used": user["messages_today"]
            * POINTS_CONFIG["text_message"]["points_per_message"],
            "text_points_limit": POINTS_CONFIG["text_message"]["daily_limit"],
            "music_files_used": user["music_today"],
            "music_files_limit": POINTS_CONFIG["audio_upload"]["max_files_per_day"],
            "music_points_used": user["music_today"]
            * POINTS_CONFIG["audio_upload"]["points_per_file"],
            "music_points_limit": POINTS_CONFIG["audio_upload"]["daily_limit"],
            "reactions_given_used": user["reactions_given_today"],
            "reactions_given_limit": POINTS_CONFIG["reaction_given"][
                "max_reactions_per_day"
            ],
            "reactions_given_points_used": user["reactions_given_today"]
            * POINTS_CONFIG["reaction_given"]["points_per_reaction"],
            "reactions_given_points_limit": POINTS_CONFIG["reaction_given"][
                "daily_limit"
            ],
            "points_total": user["points"],
        }

    async def register_scheduled_tasks(self, application: Application) -> None:
        """
        Этот метод осуществляет регистрацию периодических
        задач. Задача решает следующие проблемы:

        - Сброс дневных лимитов каждые 24 часа
        - Уменьшение баллов для неактивных каждый час

        Args:
            application (Application): Экземпляр приложения.
        """
        # Вычисление времени до следующей полночи
        now = datetime.now()
        next_midnight = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        time_to_midnight = (next_midnight - now).total_seconds()

        # Сброс дневных лимитов каждые 24 часа
        application.job_queue.run_repeating(
            self.reset_daily_limits,
            interval=SCHEDULED_TASKS["daily_reset"],
            first=time_to_midnight,
            name="daily_reset",
        )

        # Вычисление времени до начала следующего часа
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        time_to_next_hour = (next_hour - now).total_seconds()

        # Уменьшение баллов для неактивных каждый час
        application.job_queue.run_repeating(
            self.decrease_inactive_points,
            interval=SCHEDULED_TASKS["points_decay"],
            first=time_to_next_hour,
            name="points_decay",
        )

        logger.info(
            f"Scheduled tasks registered: daily_reset (24h), points_decay (1h). "
            f"Next reset at {next_midnight.strftime('%Y-%m-%d %H:%M:%S')}, "
            f"next decay at {next_hour.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def __str__(self) -> str:
        """
        Этот метод возвращает строковое представление системы для работы с баллами.
        Returns:
            str: Название класса.
        """
        return "PointsSystem"
