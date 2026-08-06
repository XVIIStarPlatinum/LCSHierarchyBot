"""
Модуль экранов инлайн-навигации.

Экран — чистая функция (без побочных эффектов, без общения с Telegram
API или базой данных), которая по уже готовым данным строит пару
(текст, клавиатура). Один и тот же экран используется и текстовой
командой (создаёт новое сообщение через reply_text), и инлайн-кнопкой
(редактирует существующее через edit_message_text) — поэтому,
например, /profile и кнопка "Мой профиль" всегда показывают
идентичный результат, а не два отдельных, потенциально расходящихся
представления.
"""

import logging
from typing import Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import LOG_ENCODING, LOG_FORMAT, LOG_LEVEL
from utils.helpers import format_rank_with_emoji

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/screens.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Кнопка "домой" одинакова на любом экране, кроме самого входного зала.
HOME_BUTTON = InlineKeyboardButton("🏠 Домой", callback_data="nav:home")


def render_entrance_hall(
    is_owner: bool, is_admin: bool
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Этот экран — входной зал (аналог текста команды /start), с
    ролевым приветствием и переходом в профиль.
    Args:
        is_owner (bool): Является ли пользователь владельцем?
        is_admin (bool): Является ли пользователь администратором?
    Returns:
        Tuple[str, InlineKeyboardMarkup]: Текст и клавиатура экрана.
    """
    if is_owner:
        welcome_prefix = (
            "🎉 <b>Добро пожаловать, создатель сообщества! "
            "Доступны команды: /profile, /top, /add, /legend, "
            "/unlegend, /setadmin, /unsetadmin, /admins, /reset, "
            "/@username.</b>"
        )
    elif is_admin:
        welcome_prefix = (
            "🎉 <b>Привет, админ! Управляй сообществом с помощью "
            "команд: /profile, /top, /add, "
            "/admins, /reset, /@username.</b>"
        )
    else:
        welcome_prefix = (
            "🎉 <b>Добро пожаловать в сообщество! Используй /profile"
            " для просмотра статуса, /top для рейтинга. Будь активным"
            " и повышай свой ранг!</b>"
        )

    text = welcome_prefix + (
        "\n\n"
        "🤖 Я - бот-калькулятор, который помогает отслеживать "
        "вашу активность и ранг в сообществе.\n\n"
        "📊 <b>Как это работает:</b>\n"
        "• За каждое сообщение вы получаете 0.1 балла\n"
        "• За загрузку музыки (MP3/WAV) - 1.0 балл\n"
        "• За реакции - 0.1 балла (макс. 33 в день)\n"
        "• За полученные реакции - 0.2 балла (без лимита)\n\n"
        "🏆 <b>Ранги в сообществе:</b>\n"
        "• 🔰 Новичок: 0+ баллов\n"
        "• 🎗 Стажёр: 10+ баллов\n"
        "• 🥉 Участник: 100+ баллов\n"
        "• 🥈 Активист: 200+ баллов\n"
        "• 🥇 Завсегдатай: 300+ баллов\n"
        "• 🏆 Представитель: 500+ баллов\n"
        "• 💎 Легенда: 1000+ баллов\n\n"
        "💡 <b>Полезные команды:</b>\n"
        "/profile - посмотреть свой профиль и статистику\n"
        "/top - топ-100 участников сообщества\n\n"
        "⚠️ <b>Важно:</b> Если вы не будете активны 24 часа в "
        "ранге «Новичок», вы будете удалены из чата. "
        "Регулярная активность поможет вам улучшить "
        "ранг и получить больше привилегий!\n\n"
        "🚀 <b>Начните общаться в основном чате, "
        "чтобы набирать баллы и повышать свой ранг!</b>"
    )

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("👤 Мой профиль", callback_data="nav:profile")]]
    )
    return text, keyboard


def render_profile_screen(
    profile: dict, rank_system
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Экран профиля пользователя. Данные (`profile`) должны быть уже
    получены заранее (например, через get_cached_profile) — эта
    функция только форматирует их и не обращается к БД сама, чтобы
    оставаться чистой и одинаково тестируемой независимо от того,
    кто её вызвал.
    Args:
        profile (dict): Данные профиля (см. get_cached_profile).
        rank_system: Экземпляр RankSystem для привилегий/ограничений.
    Returns:
        Tuple[str, InlineKeyboardMarkup]: Текст и клавиатура экрана.
    """
    username = profile["username"] or f"user{profile['user_id']}"
    rank_with_emoji = format_rank_with_emoji(profile["rank"])

    privileges = rank_system.get_user_privileges(profile["rank"])
    restrictions = rank_system.get_user_restrictions(profile["rank"])

    text = (
        f"👤 <b>Профиль: @{username}</b>\n"
        f"🏆 <b>Ранг:</b> {rank_with_emoji}\n"
        f"💡 <b>Баллы:</b> {profile['points']:.1f}\n"
        f"📊 <b>Место:</b> {profile['position']}\n\n"
        f"🔓 <b>Привилегии:</b>\n"
    )

    if privileges:
        for i, privilege in enumerate(privileges, 1):
            text += f"   {i}. {privilege}\n"
    else:
        text += "   Нет особых привилегий\n"

    text += "\n🔒 <b>Ограничения:</b>\n"

    if restrictions:
        for i, restriction in enumerate(restrictions, 1):
            text += f"   {i}. {restriction}\n"
    else:
        text += "   Нет ограничений\n"

    text += "\n📝 <b>Будь активным в жизни сообщества и повышай свой ранг!</b>"

    keyboard = InlineKeyboardMarkup([[HOME_BUTTON]])
    return text, keyboard
