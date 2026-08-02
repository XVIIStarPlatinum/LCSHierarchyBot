import logging
import os

from dotenv import load_dotenv

load_dotenv()
# Настройки для взаимодействия с Telegram API
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = int(os.environ.get("CHAT_ID"))
TOPIC_ID = int(os.environ.get("TOPIC_ID"))
TOPIC_IMPORTANT_ID = int(os.environ.get("TOPIC_IMPORTANT_ID"))
OWNER_ID = int(os.environ.get("OWNER_ID"))
OWNER_USERNAME = os.environ.get("OWNER_USERNAME")
BOT_USERNAME = os.environ.get("BOT_USERNAME")

# База данных
DATABASE_PATH = os.environ.get("DATABASE_PATH", "database/hierarchy.db")

# Логирование
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_ENCODING = "utf-8"

# Система начисления баллов
POINTS_CONFIG = {
    "text_message": {
        "min_length": 5,
        "points_per_message": 0.1,
        "daily_limit": 3.6,
        "max_messages_per_day": 36,
    },
    "audio_upload": {
        "allowed_mime_types": ["audio/mpeg", "audio/wav", "audio/mp3"],
        "points_per_file": 1.0,
        "daily_limit": 3.0,
        "max_files_per_day": 3,
    },
    "reaction_given": {
        "points_per_reaction": 0.1,
        "daily_limit": 3.3,
        "max_reactions_per_day": 33,
    },
    "reaction_received": {"points_per_reaction": 0.2, "daily_limit": None},
}

# Система рангов
RANKS = [
    {
        "name": "Новичок",
        "min_points": 0,
        "max_points": 9.9,
        "emoji": "🔰",
        "inactivity_period": 24,
        "points_decay": 1,  # -1 балл за каждые 24ч без сообщений И реакций
    },
    {
        "name": "Стажёр",
        "min_points": 10,
        "max_points": 99.9,
        "emoji": "🎗",
        "inactivity_period": 72,
        "points_decay": 0.0,  # без уменьшения
    },
    {
        "name": "Участник",
        "min_points": 100,
        "max_points": 199.9,
        "emoji": "🥉",
        "inactivity_period": 168,
        "points_decay": 0.0,  # дальше то же самое
    },
    {
        "name": "Активист",
        "min_points": 200,
        "max_points": 299.9,
        "emoji": "🥈",
        "inactivity_period": 720,
        "points_decay": 0.0,
    },
    {
        "name": "Завсегдатай",
        "min_points": 300,
        "max_points": 499.9,
        "emoji": "🥇",
        "inactivity_period": None,  # пользователь не удаляется (дальше то же самое)
        "points_decay": 0.0,
    },
    {
        "name": "Представитель",
        "min_points": 500,
        "max_points": 999.9,
        "emoji": "🏆",
        "inactivity_period": None,
        "points_decay": 0.0,
    },
    {
        "name": "Легенда",
        "min_points": 1000,
        "max_points": float("inf"),
        "emoji": "💎",
        "inactivity_period": None,
        "points_decay": 0.0,
    },
]

# Настройки антиспама (лучше дополнить ключевые слова,
# а то так себе побороться с этими спамерами)
ANTI_SPAM_CONFIG = {
    "max_messages_per_minute": 45,
    "identical_messages_threshold": 3,
    "inactive_days_threshold": 30,
    "spam_keywords": [
        "http",
        "https",
        "t.me",
        "telegram.me",
        "ссылка",
        "реклама",
        "чат",
        "канал",
        "заходи",
        "подписывайся",
        "зарабатывай",
    ],
    "flood_wait_minutes": 5,
}

# Периодические задачи
SCHEDULED_TASKS = {
    "daily_reset": 24 * 3600,  # Сброс дневных лимитов
    "points_decay": 24 * 3600,  # Срок между уменьшениями баллов у новичков (24ч)
    "inactivity_check": 10 * 60,  # Срок между проверками неактивности (10 минут)
    "cache_cleanup": 600,  # Срок между очистками кэша
}

# Настройки самоочистки ЛС
PRIVATE_CHAT_CLEANUP = {
    "keep_last_messages": 1,  # Последнее сообщение
    "preserve_start_message": True,  # Сообщение /start
    "cleanup_delay": 2,  # Задержка перед очисткой
}

# Настройки верификации новых участников (то есть,
# если не отправить /start, то пользователь не верифицирован)
VERIFICATION_CONFIG = {
    "welcome_message_cooldown": 300,  # 5 минут перед повторным приветствием
    "unverified_timeout": 24 * 3600,  # 24 часа на верификацию (/start)
    "max_welcome_attempts": 3,  # Максимальное количество приветствий
}

# Кэширование статистики
CACHE_CONFIG = {
    "user_cache_duration": 600,  # 10 минут для обычных пользователей
    "admin_cache_duration": 0,  # 0 секунд = мгновенное обновление
    "owner_cache_duration": 0,  # 0 секунд = мгновенное обновление
}
