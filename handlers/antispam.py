import logging
import re
from datetime import datetime, timedelta

from telegram import Message, Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.ext._utils.types import BD

from config import (ANTI_SPAM_CONFIG, CHAT_ID, LOG_ENCODING, LOG_FORMAT,
                    LOG_LEVEL, OWNER_ID, TOPIC_ID)
from utils.helpers import get_rank_level, normalize_text

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/antispam.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class AntiSpamSystem:
    """Класс для борьбы со спамом в чате.
    В зависимости от новых методов и трюков спамеров приходится
    настраивать этот класс несколько раз.
    Система отслеживает чрезмерную активность и уведомляет
    администраторов о подозрительном поведении в следующих случаях:

        - Более 45 сообщений в минуту
        - Одинаковый текст в каждом сообщении (3+ сообщений подряд)
        - Нарушение прав медиа-сообщений

    Attributes:
        bot (BD): Экземпляр бота.
        message_timestamps (dict): Временные метки сообщений.
        last_message_texts (dict): Последние сообщений.
        SPAM_THRESHOLD_MESSAGES (int): Предел частоты спама.
        SPAM_THRESHOLD_IDENTICAL (int): Предел количества одинаковых сообщений.
        SPAM_COOLDOWN (int): Период, по которому рассчитывается частота сообщений.
        MEDIA_RESTRICTED_RANK (str): Название ранга, к которому применяется запреты.
    """

    def __init__(self, bot_instance: BD):
        """
        Конструктор класса системы борьбы со спамом.
        Args:
            bot_instance (BD): Экземпляр бота.
        """
        self.bot = bot_instance
        self.message_timestamps = {}
        self.last_message_texts = {}
        self.SPAM_THRESHOLD_MESSAGES = ANTI_SPAM_CONFIG["max_messages_per_minute"]
        self.SPAM_THRESHOLD_IDENTICAL = ANTI_SPAM_CONFIG["identical_messages_threshold"]
        self.SPAM_COOLDOWN = 60
        self.MEDIA_RESTRICTED_RANK = "Новичок"

    async def check_spam(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """Этот метод осуществляет основную проверку на спам.
        Args:
            update (Update): Событие обновления состояния.
            context (ContextTypes): Контекст приложения.
        Returns:
            bool: `True` если обнаружен спам, `False` если иначе.
        """
        message = update.effective_message
        user = update.effective_user

        # Скипаем владельца и администратора
        if user.id == OWNER_ID or self.bot.db.is_admin(user.id):
            return False

        # Частота сообщений (более 45 сообщении в минуту)
        if await self.check_message_frequency(user.id):
            await self.handle_detected_spam(
                update, context, user, "чрезмерная частота сообщений"
            )
            return True

        # Идентичность текста (3+ сообщений подряд)
        if await self.check_identical_messages(user.id, message):
            await self.handle_detected_spam(
                update, context, user, "повторяющийся текст в сообщениях"
            )
            return True

        # Проверка медиа для новичков
        if await self.check_media_restrictions(user.id, message):
            await self.handle_media_restriction(update, context, user)
            return True

        return False

    async def check_message_frequency(self, user_id: int) -> bool:
        """
        Этот метод осуществляет проверку частоты сообщений
        (например, если пользователь написал 45 сообщений в минуту).
        Args:
            user_id (int): ID пользователя.
        Returns:
            bool: `True` если обнаружен спам данного вида, `False` если иначе.
        """

        now = datetime.now()

        # Если нет пользователя
        if user_id not in self.message_timestamps:
            self.message_timestamps[user_id] = []

        cutoff_time = now - timedelta(seconds=self.SPAM_COOLDOWN)
        self.message_timestamps[user_id] = [
            ts for ts in self.message_timestamps[user_id] if ts > cutoff_time
        ]

        self.message_timestamps[user_id].append(now)

        if len(self.message_timestamps[user_id]) >= self.SPAM_THRESHOLD_MESSAGES:
            logger.warning(
                f"Potential spam detected: user_id={user_id},"
                f"messages in a minute: {len(self.message_timestamps[user_id])}"
            )
            return True

        return False

    async def check_identical_messages(self, user_id: int, message: Message) -> bool:
        """
        Этот метод осуществляет проверку на одинаковых текстов в сообщении.
        Args:
            user_id (int): ID пользователя.
            message (Message): Подозреваемое сообщение.
        Returns:
            bool: `True` если обнаружен спам данного вида, `False` если иначе.
        """
        if not message.text:
            return False

        current_text = normalize_text(message.text)

        if user_id not in self.last_message_texts:
            self.last_message_texts[user_id] = {"text": current_text, "count": 1}
            return False

        last_data = self.last_message_texts[user_id]

        if current_text == last_data["text"]:
            new_count = last_data["count"] + 1
            self.last_message_texts[user_id] = {
                "text": current_text,
                "count": new_count,
            }

            if new_count >= self.SPAM_THRESHOLD_IDENTICAL:
                logger.warning(
                    f"Potential spam detected: user_id={user_id}, "
                    f"identical messages count={new_count}, message={current_text}"
                )
                return True
        else:
            self.last_message_texts[user_id] = {"text": current_text, "count": 1}

        return False

    async def check_media_restrictions(self, user_id: int, message: Message) -> bool:
        """
        Этот метод осуществляет проверку ограничений на медиа для новичков.
        Args:
            user_id (int): ID пользователя.
            message (Message): Подозреваемое сообщение.
        Returns:
            bool: `True` если обнаружен спам данного вида, `False` если иначе.
        """
        user = self.bot.db.get_user(user_id)
        if not user:
            return False

        user_rank = user["rank"]
        if get_rank_level(user_rank) > get_rank_level(self.MEDIA_RESTRICTED_RANK):
            return False

        has_restricted_media = any(
            [
                message.photo,  # Фото
                message.video,  # Видео
                message.video_note,  # Кружочки
            ]
        )

        if has_restricted_media:
            logger.warning(
                f"Media restrictions violated: user_id={user_id}, rank={user_rank}"
            )
            return True

        return False

    async def handle_detected_spam(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: object,
        reason: str,
    ) -> None:
        """
        Этот метод осуществляет обработку спама.
        Args:
            update (Update): Событие обновления состояния.
            context (ContextTypes): Контекст приложения.
            user (object): Пользователь.
            reason (str): Причина, почему был обнаружен спам.
        """
        message = update.effective_message

        try:
            await message.delete()
            logger.info(f"Spam message={message.id} from user={user.id} deleted")
        except Exception as e:
            logger.error(f"Failed to delete spam message from user={user.id}: {e}")

        await self.notify_admins(context, user, reason, message)

    async def handle_media_restriction(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, user: object
    ) -> None:
        """
        Этот метод осуществляет обработку нарушения запретов отправки медиа-сообщении.
        Args:
            update (Update): Событие обновления состояния.
            context (ContextTypes): Контекст приложения.
            user (object): Пользователь.
        """
        message = update.effective_message

        try:
            await message.delete()
            logger.info(
                f"Media message={message.id} from user={user.id} "
                "deleted due to restrictions"
            )
        except Exception as e:
            logger.error(f"Failed to delete media message from user={user.id}: {e}")

        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    "⚠️ <b>Ограничение медиа-контента</b>\n\n"
                    f"Ваш ранг: <b>{self.MEDIA_RESTRICTED_RANK}</b>\n"
                    "Участники с рангом 'Новичок' не могут публиковать"
                    "медиа (фото, видео, кружочки).\n\n"
                    "💡 <b>Как получить больше возможностей:</b>\n"
                    "• Накапливайте баллы за активность\n"
                    "• Достигайте ранга 'Стажёр' (10+ баллов)\n"
                    "• Следуйте правилам сообщества\n\n"
                    "🚀 Продолжайте участвовать в обсуждениях "
                    "текстовыми сообщениями и загрузкой музыки!"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to send restriction notice to user {user.id}: {e}")

    async def notify_admins(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user: object,
        reason: str,
        message: Message,
    ) -> None:
        """
        Этот метод уведомляет админов о подозрительной активности.
        Args:
            context (ContextTypes): Контекст приложения.
            user (object): Пользователь.
            reason (str): Причина, почему был обнаружен спам.
            message (Message): Сообщение, которое вызвало обнаружение.
        """
        admins = self.bot.db.get_all_admins()

        message_text = message.text[:100] if message.text else "[Медиа-контент]"
        # Удаление символов, ломающих HTML
        message_text = re.sub(r"[<>]", "", message_text)

        user_mention = f"@{user.username}" if user.username else f"{user.first_name}"
        if not user_mention:
            user_mention = f"ID: {user.id}"

        user_rank = "Неизвестен"
        try:
            user_data = self.bot.db.get_user(user.id)
            if user_data:
                user_rank = user_data["rank"]
        except Exception as e:
            logger.error(f"Error getting user rank for notification: {e}")

        notification_text = (
            f"🚨 <b>Обнаружена подозрительная активность!</b>\n\n"
            f"👥 <b>Пользователь:</b> {user_mention} (ID: {user.id})\n"
            f"📊 <b>Ранг:</b> {user_rank}\n"
            f"⚠️ <b>Причина:</b> {reason}\n"
            f"💬 <b>Сообщение:</b> {message_text}\n"
            f"🕒 <b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"🔧 <b>Рекомендуемые действия:</b>\n"
            f"• Проверить историю активности пользователя\n"
            f"• Рассмотреть временное ограничение\n"
            f"• Предупредить пользователя в личных сообщениях"
        )

        # Рассылка уведомлений администраторам
        for admin in admins:
            try:
                if (
                    admin["user_id"] != OWNER_ID
                ):  # Владелец получит отдельное уведомление
                    await context.bot.send_message(
                        chat_id=admin["user_id"],
                        text=notification_text,
                        parse_mode="HTML",
                    )
                    logger.info(
                        f"Admin notified: admin_id={admin['user_id']},"
                        f"user_id={user.id}, reason='{reason}'"
                    )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin['user_id']}: {e}")

        # Отдельное уведомление владельцу
        try:
            owner_notification = (
                f"👑 <b>УВЕДОМЛЕНИЕ ВЛАДЕЛЬЦУ</b>\n\n{notification_text}"
            )
            await context.bot.send_message(
                chat_id=OWNER_ID, text=owner_notification, parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify owner: {e}")

    def __str__(self) -> str:
        """
        Этот метод возвращает строковое представление системы для антиспама.
        Returns:
            str: Название класса.
        """
        return "AntiSpamSystem"


async def handle_message_with_antispam(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Эта функция является входной точкой для обработки сообщения
    на обнаружения спамов. Вызывается перед основной обработкой сообщения.
    Args:
        update (Update): Событие обновления состояния.
        context (ContextTypes): Контекст приложения.
    """
    antispam = context.bot_data.get("antispam_system")
    if not antispam:
        logger.error("AntiSpamSystem not initialized in bot_data")
        return

    message = update.effective_message
    user = update.effective_user

    # Фильтрация по чату и топику
    if message.chat.id != CHAT_ID:
        return
    if hasattr(message, "message_thread_id") and message.message_thread_id != TOPIC_ID:
        return

    # Пропускаем владельца
    if user.id == OWNER_ID:
        return

    # Проверка на спам
    is_spam = await antispam.check_spam(update, context)

    # Если спам обнаружен - значит стоп
    if is_spam:
        return
    # Ура, сообщение не спам
    logger.debug(
        f"Message={message.message_id} from user={user.id} has passed spam check."
    )


def register_handlers(application: Application, bot_instance: BD) -> None:
    """Эта функция осуществляет регистрацию функциональностей системы антиспама.
    Args:
        application (Application): Экземпляр приложения.
        bot_instance (BD): Экземпляр бота.
    """
    antispam_system = AntiSpamSystem(bot_instance)
    application.bot_data["antispam_system"] = antispam_system

    application.add_handler(
        MessageHandler(
            filters.Chat(CHAT_ID) & filters.ALL, handle_message_with_antispam
        ),
        group=0,
    )
    logger.info("Antispam handlers registered successfully")
