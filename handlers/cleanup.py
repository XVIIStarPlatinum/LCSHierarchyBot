import logging
from datetime import datetime, timedelta
from typing import Tuple

from telegram.error import TelegramError
from telegram.ext import Application, ContextTypes
from telegram.ext._utils.types import BD

from config import (BOT_USERNAME, CHAT_ID, LOG_ENCODING, LOG_FORMAT, LOG_LEVEL,
                    OWNER_ID)
from utils.helpers import get_clean_rank, notify_owner_error

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/cleanup.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


async def send_deletion_warning(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    rank: str,
    last_activity: datetime,
    reason: str = "inactivity",
) -> None:
    """
    Эта функция отвечает за отправкой уведомления пользователю перед удалением.
    Args:
        context (ContextTypes): Контекст приложения.
        user_id (int): ID пользователя.
        rank (str): Ранг пользователя.
        last_activity (datetime): Последняя активность пользователя.
        reason (str): Причина удаления с суперчата.
    """
    try:
        # Если челик не нажал на /start
        if reason == "unverified":
            warning_text = (
                "⚠️ <b>Предупреждение о неверификации</b>\n\n"
                "Вы не прошли верификацию в сообществе!\n\n"
                "💡 <b>Что нужно сделать:</b>\n"
                f"• Напишите /start в личные сообщения боту @{BOT_USERNAME}\n"
                "• Это займёт всего 5 секунд\n\n"
                "⏳ <b>Важно:</b> Если вы не отправите /start в течение 24 "
                "часов после вступления в чат, вы будете автоматически удалены.\n\n"
                "🚀 Пожалуйста, пройдите верификацию, "
                "чтобы сохранить доступ к сообществу!"
            )
        else:
            warning_text = (
                "⚠️ <b>Предупреждение о неактивности</b>\n\n"
                f"Ваш ранг в сообществе: <b>{rank}</b>\n"
                f"Последняя активность: {last_activity.strftime('%Y-%m-%d %H:%M')}\n\n"
                "Вы были автоматически удалены из чата из-за "
                "длительного отсутствия активности.\n\n"
                "💡 <b>Как вернуться:</b>\n"
                "• Вы можете повторно вступить в чат\n"
                "• Пройти верификацию через /start\n"
                "• Начать активность заново\n\n"
                "🎯 <b>Совет:</b> Регулярно участвуйте в обсуждениях, "
                "чтобы сохранить свой ранг и привилегии!"
            )

        await context.bot.send_message(
            chat_id=user_id, text=warning_text, parse_mode="HTML"
        )
        logger.debug(f"Deletion warning sent to user_id={user_id}, reason={reason}")
    except Exception as e:
        logger.debug(
            f"Failed to send warning to user {user_id}: {e} (user may have blocked bot)"
        )


async def send_cleanup_report(
    context: ContextTypes.DEFAULT_TYPE,
    removed_count: int,
    skipped_count: int,
    inactive_users: list,
    unverified_users: list,
) -> None:
    """
    Эта функция отвечает за отправкой отчета владельцу о результатах очистки.
    Args:
        context (ContextTypes): Контекст приложения.
        removed_count (int): Число удалённых пользователей.
        skipped_count (int): Число пользователей, которых не получилось удалять.
        inactive_users (list): Список неактивных пользователей.
        unverified_users (list): Список неверифицированных пользователей.
    """
    total_inactive = len(inactive_users)
    total_unverified = len(unverified_users)
    total_removed = removed_count + len(unverified_users)

    rank_counts = {}
    for user in inactive_users:
        clean_rank = get_clean_rank(user["rank"])
        rank_counts[clean_rank] = rank_counts.get(clean_rank, 0) + 1

    report_text = (
        f"📊 <b>Отчет по очистке неактивных участников</b>\n\n"
        f"⏰ <b>Время выполнения:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🔍 <b>Всего проверено:</b>\n"
        f"   • Неактивных: {total_inactive}\n"
        f"   • Неверифицированных: {total_unverified}\n"
        f"✅ <b>Удалено:</b>\n"
        f"   • За неактивность: {removed_count}\n"
        f"   • За неверификацию: {total_unverified}\n"
        f"   • <b>Всего удалено:</b> {total_removed}\n"
        f"⏭️ <b>Пропущено:</b> {skipped_count}\n\n"
        f"📈 <b>Статистика по рангам (неактивные):</b>\n"
        f"• 🔰 Новичок: {rank_counts.get('Новичок', 0)}\n"
        f"• 🎗 Стажёр: {rank_counts.get('Стажёр', 0)}\n"
        f"• 🥉 Участник: {rank_counts.get('Участник', 0)}\n"
        f"• 🥈 Активист: {rank_counts.get('Активист', 0)}\n\n"
    )

    try:
        await context.bot.send_message(
            chat_id=OWNER_ID, text=report_text, parse_mode="HTML"
        )
        logger.info("Cleanup report sent to owner")
    except Exception as e:
        logger.error(f"Failed to send cleanup report: {e}")


async def safe_ban_user(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, reason: str
) -> bool:
    """
    Эта функция отвечает за безопасного бана пользователя с проверкой прав бота.
    Пользователь не сможет вернуться в группу без предварительного разбана.
    Args:
        context (ContextTypes): Контекст приложения.
        user_id (int): ID пользователя.
        username (str): Имя пользователя.
        reason (str): Причина удаления с суперчата.
    Returns:
        bool: `True` если пользователь был успешно забанен, `False` если не был забанен.
    """
    try:
        logger.debug(
            f"Attempting to ban user {user_id} ({username}) for reason: {reason}"
        )

        await context.bot.ban_chat_member(chat_id=CHAT_ID, user_id=user_id)
        logger.info(
            f"Successfully banned user {user_id} ({username}) for reason: {reason}"
        )
        return True

    except Exception as e:
        error_msg = f"Failed to ban user {user_id} ({username}): {str(e)}"
        logger.error(error_msg)

        try:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=f"❌ <b>Ошибка бана</b>\n\n{error_msg}\n\n<b>"
                f"Действие:</b> Проверьте права бота в суперчате",
                parse_mode="HTML",
            )
        except TelegramError:
            pass

        return False


class CleanupSystem:
    """
    Класс для очистки неактивных пользователей от чата.
    Действуют определённые правила, согласно которым осуществляется очистка.
    В ЛС удалённого пользователя всегда приведена причина удаления с чата.
    Удаление не равносилен бану, поэтому пользователь может снова вспупить в чат.
    Attributes:
        bot (BD): Экземпляр бота.
        last_cleanup (datetime): Последний момент очистки.
        DELETION_THRESHOLDS (dict): Периоды разрешенной неактивности.
    """

    def __init__(self, bot_instance: BD) -> None:
        """Конструктор класса для очистки неактивных пользователей.
        Args:
            bot_instance (BD): Экземпляр бота.
        """
        self.bot = bot_instance
        self.last_cleanup = datetime.now()
        self.DELETION_THRESHOLDS = {
            "Новичок": timedelta(hours=24),
            "Стажёр": timedelta(days=3),
            "Участник": timedelta(days=7),
            "Активист": timedelta(days=30),
            # Их не трогаем
            "Завсегдатай": None,
            "Представитель": None,
            "Легенда": None,
        }

    async def check_and_remove_inactive_users(
        self, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Этот метод отвечает за проверкой и удалением неактивных пользователей.
        Args:
            context (ContextTypes): Контекст приложения.
        """
        logger.info("Starting inactive users cleanup...")

        try:
            # Удаление неверифицированных пользователей (участники без /start)
            unverified_users = await self.remove_unverified_users(context)

            # Удаление инактивов по рангам
            removed_count, skipped_count = await self.remove_inactive_by_ranks(
                context, unverified_users
            )

            inactive_users = self.bot.db.get_inactive_users()
            await send_cleanup_report(
                context, removed_count, skipped_count, inactive_users, unverified_users
            )

            logger.info(
                f"Cleanup completed: removed {removed_count} inactive "
                f"+ {len(unverified_users)} unverified users, "
                f"skipped {skipped_count} users."
            )

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            await notify_owner_error(context, e)

    async def remove_unverified_users(self, context: ContextTypes.DEFAULT_TYPE):
        """
        Этот метод отвечает за удалением пользователей,
        не прошедших верификацию (/start) в течение 24 часов.
        Args:
            context (ContextTypes): Контекст приложения.
        """
        unverified_users = self.bot.db.get_unverified_users()
        if not unverified_users:
            logger.debug("No unverified users found for removal")
            return []

        logger.info(f"Found {len(unverified_users)} unverified users for removal")
        removed_users = []

        for user in unverified_users:
            user_id = user["user_id"]
            username = user["username"]
            join_time = datetime.strptime(user["last_activity"], "%Y-%m-%d %H:%M:%S")

            # Можно и нужно ли удалять этого пользователя
            if await self.should_skip_unverified_removal(user_id, username):
                continue

            try:
                await send_deletion_warning(
                    context, user_id, "Новичок", join_time, reason="unverified"
                )

                if await safe_ban_user(context, user_id, username, "unverified"):
                    self.bot.db.mark_user_for_deletion(user_id)
                    removed_users.append(user)
                    logger.info(
                        f"Unverified user removed: {user_id}, "
                        f"username={username}, join_time={join_time}"
                    )

            except Exception as e:
                logger.error(f"Error removing unverified user {user_id}: {e}")
                await notify_owner_error(context, e)

        return removed_users

    async def should_skip_unverified_removal(self, user_id: int, username: str) -> bool:
        """
        Этот метод отвечает за проверкой того, следует ли
        пропустить удаление неверифицированного пользователя.
        Args:
            user_id: ID пользователя.
            username: Имя пользователя.
        Returns:
            bool: `True` если пользователь был пропущен, `False` если не был пропущен.
        """
        # Пропускаем владельца и админов
        if user_id == OWNER_ID or self.bot.db.is_admin(user_id):
            logger.info(f"Skipping unverified removal for admin/owner: {user_id}")
            return True

        # Пропускаем, если пользователь имеет высокий ранг
        user = self.bot.db.get_user(user_id)
        if user:
            rank = get_clean_rank(user["rank"])
            if rank in ["Завсегдатай", "Представитель", "Легенда"]:
                logger.debug(
                    "Skipping unverified removal for user: "
                    f"{username} ({user_id}). Rank: {rank}"
                )
                return True

        return False

    async def remove_inactive_by_ranks(
        self, context: ContextTypes.DEFAULT_TYPE, excluded_users: list
    ) -> Tuple[int, int]:
        """
        Этот метод отвечает за удалением неактивных
        пользователей по рангам с учетом исключений.
        Args:
            context (ContextTypes): Контекст приложения.
            excluded_users (list): Список пользователей,
            исключённых от процесса очистки.
        Returns:
            Tuple[int, int]:
                - int: Число удалённых пользователей.
                - int: Число пропущенных пользователей.
        """
        inactive_users = self.bot.db.get_inactive_users()
        removed_count = 0
        skipped_count = 0

        for user in inactive_users:
            user_id = user["user_id"]

            # Пропускаем уже удаленных неверифицированных пользователей
            if any(u["user_id"] == user_id for u in excluded_users):
                continue

            username = user["username"]
            rank = user["rank"]

            try:
                # Дополнительная проверка формата времени
                last_activity_str = user["last_activity"]
                if last_activity_str:
                    if "." in last_activity_str:
                        last_activity = datetime.strptime(
                            last_activity_str, "%Y-%m-%d %H:%M:%S.%f"
                        )
                    else:
                        last_activity = datetime.strptime(
                            last_activity_str, "%Y-%m-%d %H:%M:%S"
                        )
                else:
                    last_activity = self.last_cleanup
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Error parsing last_activity for user "
                    f"{user_id}: {e}. Using default time."
                )
                last_activity = self.last_cleanup

            if await self.should_skip_removal(user_id, rank, last_activity):
                skipped_count += 1
                continue

            if await self.remove_user(context, user_id, username, rank, last_activity):
                removed_count += 1

        return removed_count, skipped_count

    async def should_skip_removal(
        self, user_id: int, rank: str, last_activity: datetime
    ) -> bool:
        """Этот метод отвечает за проверка того, следует ли
        пропустить удаление пользователя по рангу. Пропускают:

        - Админов
        - Владельца
        - Юзеров больше или равное "Завсегдатай"
        - Активов

        Args:
            user_id (int): ID пользователя.
            rank (str): Ранг пользователя.
            last_activity (datetime): Последняя активность пользователя.
        Returns:
            bool: `True` если пользователь был пропущен, `False` если не был пропущен.
        """
        if self.bot.db.is_admin(user_id):
            logger.info(f"Skipping admin removal: {user_id}")
            return True

        if user_id == OWNER_ID:
            logger.info(f"Skipping owner removal: {user_id}")
            return True

        if rank in ["Завсегдатай", "Представитель", "Легенда"]:
            logger.info(
                "Skipping removal for user with protected rank: "
                f"{user_id}, rank={rank}"
            )
            return True

        deletion_time = self.last_cleanup - self.DELETION_THRESHOLDS[rank]
        if last_activity.replace(microsecond=0) > deletion_time.replace(microsecond=0):
            logger.debug(
                "Skipping removal for user with recent activity: "
                f"{user_id}, last_activity={last_activity}"
            )
            return True

        return False

    async def remove_user(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        username: str,
        rank: str,
        last_activity: datetime,
    ) -> bool:
        """
        Этот метод отвечает за удалением пользователя за неактивность.
        Args:
            context (ContextTypes): Контекст приложения.
            user_id (int): ID пользователя.
            username (str): Имя пользователя.
            rank (str): Ранг пользователя.
            last_activity (datetime): Последняя активность пользователя.
        Returns:
            bool: `True` если пользователь был удалён, `False` если не был удалён.
        """
        try:
            await send_deletion_warning(
                context, user_id, rank, last_activity, reason="inactivity"
            )

            if await safe_ban_user(context, user_id, username, "inactivity"):
                self.bot.db.mark_user_for_deletion(user_id)
                logger.info(
                    f"Inactive user removed: {user_id}, username={username}, "
                    f"rank={rank}, last_activity={last_activity}"
                )
                return True

        except Exception as e:
            logger.error(f"Error during removal of user={user_id}: {e}")
            await notify_owner_error(context, e)

        return False

    def __str__(self) -> str:
        """
        Этот метод возвращает строковое представление системы для работы с баллами.
        Returns:
            str: Название класса.
        """
        return "PointsSystem"


async def run_scheduled_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Этот метод реализует фоновую задачу для запуска очистки каждые 10 минут.
    Args:
        context (ContextTypes): Контекст приложения.
    """
    cleanup_system = context.bot_data.get("cleanup_system")
    if not cleanup_system:
        logger.error("No cleanup system configured in bot_data")
        return

    await cleanup_system.check_and_remove_inactive_users(context)
    cleanup_system.last_cleanup = datetime.now()


def register_cleanup_task(application: Application, bot_instance: BD) -> None:
    """
    Эта функция осуществляет регистрацию обработчика очистки
    чата от неактивных пользователей с интервалом 10 минут.
    Args:
        application (Application): Экземпляр приложения.
        bot_instance (BD): Экземпляр бота.
    """
    cleanup_system = CleanupSystem(bot_instance)
    application.bot_data["cleanup_system"] = cleanup_system

    application.job_queue.run_repeating(
        run_scheduled_cleanup,
        interval=600,  # 10 минут
        first=60,  # Первый запуск через 1 минуту
        name="inactive_cleanup",
    )

    # Дополнительная задача для удаления неверифицированных
    # пользователей каждые 5 минут
    application.job_queue.run_repeating(
        lambda ctx: ctx.bot_data["cleanup_system"].remove_unverified_users(ctx),
        interval=300,  # 5 минут
        first=120,  # Через 2 минуты после запуска
        name="unverified_cleanup",
    )

    logger.info(
        "Cleanup scheduled for every 10 minutes (inactive "
        "users) and every 5 minutes (unverified users)"
    )
