"""
Модуль вспомогательных функции.
Сюда входят функции, которых нельзя было помещать в классы.
"""

import logging
import re
from datetime import datetime

from telegram.ext import ContextTypes

from config import LOG_ENCODING, LOG_FORMAT, LOG_LEVEL, OWNER_ID

# Иерархия рангов
RANK_HIERARCHY = [
    "Новичок",
    "Стажёр",
    "Участник",
    "Активист",
    "Завсегдатай",
    "Представитель",
    "Легенда",
]

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/helpers.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """
    Эта вспомогательная функция осуществляет
    нормализацию текста для сравнения (удаление лишних пробелов, знаков, регистр).
    Args:
        text (str): Нормализируемая строка.
    Returns:
        str: Нормализованная строка.
    """
    normalized = text.strip().lower()
    # Is this loss?
    normalized = re.sub(r"[^a-zA-Z0-9а-яё]", "", normalized)
    return normalized


def get_clean_rank(rank_with_emoji: str) -> str:
    """
    Эта вспомогательная функция очищает ранга от
    эмодзи и префиксов для работы с базой данных.
    Args:
        rank_with_emoji (str): Название ранга из телеграмы с эмодзи.
    Returns:
        str: Название ранга без эмодзи.
    """
    if not rank_with_emoji:
        return "Новичок"

    clean_rank = "".join(
        char
        for char in rank_with_emoji
        if char.isalpha() or char.isspace() or char == "-"
    )
    clean_rank = clean_rank.strip()

    rank_mapping = {
        "🔰 Новичок": "Новичок",
        "🎗 Стажёр": "Стажёр",
        "🥉 Участник": "Участник",
        "🥈 Активист": "Активист",
        "🥇 Завсегдатай": "Завсегдатай",
        "🏆 Представитель": "Представитель",
        "💎 Легенда": "Легенда",
    }

    return rank_mapping.get(clean_rank, "Новичок")


def format_rank_with_emoji(rank: str) -> str:
    """
    Эта вспомогательная функция форматирует ранг с эмодзи для отображения.
    Args:
        rank (str): Название ранга без эмодзи.
    Returns:
        str: Название ранга с эмодзи.
    """
    emoji_mapping = {
        "Новичок": "🔰 Новичок",
        "Стажёр": "🎗 Стажёр",
        "Участник": "🥉 Участник",
        "Активист": "🥈 Активист",
        "Завсегдатай": "🥇 Завсегдатай",
        "Представитель": "🏆 Представитель",
        "Легенда": "💎 Легенда",
    }
    return emoji_mapping.get(rank, f"👤 {rank}")


def get_rank_level(rank_name: str) -> int:
    """
    Эта вспомогательная функция возвращает
    уровень ранга для сравнения при проверке прав.
    Args:
        rank_name (str): Название ранга.
    Returns:
        int: Числовой уровень заданного ранга.
    """
    try:
        return RANK_HIERARCHY.index(rank_name)
    except ValueError:
        logger.error(f"Unknown rank name: {rank_name}")
        return 0


async def notify_owner_error(
    context: ContextTypes.DEFAULT_TYPE, error: Exception
) -> None:
    """
    Эта функция отвечает за отправкой уведомления
    владельцу об ошибке в процессе очистки.
    Args:
        context (ContextTypes): Контекст приложения.
        error (Exception): Сама ошибка.
    """
    error_text = (
        f"🚨 <b>КРИТИЧЕСКАЯ ОШИБКА</b>\n\n"
        f"🔧 <b>Модуль:</b> CleanupSystem\n"
        f"⏰ <b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"❌ <b>Ошибка:</b> {str(error)[:500]}\n\n"
        f"⚠️ <b>Действие:</b> Очистка неактивных участников прервана"
    )

    try:
        await context.bot.send_message(
            chat_id=OWNER_ID, text=error_text, parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify owner about error: {e}")
