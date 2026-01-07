import asyncio
import logging
import signal
import sys
from datetime import datetime

from telegram import Update
from telegram.ext import Application, ContextTypes

from config import LOG_ENCODING, LOG_FORMAT, LOG_LEVEL, OWNER_ID, TELEGRAM_TOKEN
from database import Database
from handlers import activity, admin, antispam, cleanup, private_chat, profile
from utils.points_system import PointsSystem
from utils.rank_system import RankSystem

logging.basicConfig(
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    encoding=LOG_ENCODING,
    handlers=[logging.FileHandler("logs/bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class BotInstance:
    """Основной класс бота, объединяющий все компоненты системы.

    Бот предназначен для управления системой иерархии в суперчате.
    Бот отслеживает активность участников, начисляет баллы, присваивает
    ранги и привилегии, предоставляет профили и рейтинги,
    управляет администраторами и предотвращает спам, удаляя неактивных участников.

    Attributes:
        db (Database): Класс для работы с базой данных.
        points_system (PointsSystem): Класс для работы с системой баллов.
        rank_system (RankSystem): Класс для работы с системой рангов.
        application (Application): Класс приложения.
        is_running (bool): Запущен ли бот?
        start_time (datetime): Дата и время запуска бота.
    """

    def __init__(self) -> None:
        """Конструктор бота."""
        self.db = None
        self.points_system = None
        self.rank_system = None
        self.application = None
        self.is_running = False
        self.start_time = None

    async def initialize(self) -> None:
        """Этот метод инициализирует все компоненты бота."""
        logger.info("=== Bot initialization started ===")

        try:
            logger.info("Initializing database...")
            self.db = Database()

            logger.info("Initializing points system...")
            self.points_system = PointsSystem(self.db)

            logger.info("Initializing rank system...")
            self.rank_system = RankSystem(self.db)

            logger.info("Initializing Telegram application...")
            self.application = Application.builder().token(TELEGRAM_TOKEN).build()

            logger.info("Registering handlers...")
            self._register_all_handlers()

            logger.info("Registering scheduled tasks...")
            await self._register_scheduled_tasks()

            self.start_time = datetime.now()
            self.is_running = True

            logger.info("=== Bot initialization completed successfully ===")
            logger.info(
                f"Bot started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            logger.info(f"Owner ID: {OWNER_ID}")

        except Exception as ex:
            logger.critical(f"Critical error during initialization: {ex}")
            await self.shutdown()
            raise

    def _register_all_handlers(self) -> None:
        """Этот метод регистрирует всех обработчиков в правильном порядке."""
        antispam.register_handlers(self.application, self)
        activity.register_handlers(self.application, self)
        private_chat.register_handlers(self.application, self)
        profile.register_handlers(self.application, self)
        admin.register_handlers(self.application, self)
        cleanup.register_cleanup_task(self.application, self)
        logger.info("All components have been registered successfully")

    async def _register_scheduled_tasks(self):
        """Этот метод регистрирует всех периодических задач."""
        await self.points_system.register_scheduled_tasks(self.application)
        logger.info("All scheduled tasks have been registered successfully")

    async def start(self) -> None:
        """Этот метод запускает бота."""
        if not self.is_running:
            raise RuntimeError("Bot not initialized. Call initialize() first.")

        logger.info("Starting bot...")

        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(
                drop_pending_updates=True, allowed_updates=Update.ALL_TYPES
            )

            logger.info("Bot is now running and accepting updates")
            logger.info("Press Ctrl+C to stop the bot gracefully")

        except Exception as ex:
            logger.critical(f"Critical error during bot startup: {ex}")
            await self.shutdown()
            raise

    async def shutdown(self) -> None:
        """Этот метод корректно завершает работу бота."""
        if not self.is_running:
            return

        logger.info("=== Bot shutdown initiated ===")

        try:
            # Остановка обработчика обновлений
            if self.application and self.application.updater:
                logger.info("Stopping updater...")
                await self.application.updater.stop()

            # Остановка приложения
            if self.application:
                logger.info("Stopping application...")
                await self.application.stop()
                await self.application.shutdown()

            # Закрытие базы данных
            if self.db:
                logger.info("Closing database connection...")
                self.db.close()

            self.is_running = False
            uptime = datetime.now() - self.start_time
            logger.info(f"Bot uptime: {str(uptime).split('.')[0]}")
            logger.info("=== Bot shutdown completed successfully ===")

        except Exception as ex:
            logger.error(f"Error during shutdown: {ex}")

    async def get_status(self) -> dict:
        """
        Этот метод возвращает статус бота в цели мониторинга.
        Returns:
            dict: словарь со статусом и метаданными процесса бота.
        """
        if not self.is_running:
            return {"status": "stopped"}

        uptime = datetime.now() - self.start_time
        return {
            "status": "running",
            "uptime": str(uptime).split(".")[0],
            "start_time": self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "owner_id": OWNER_ID,
        }

    def __str__(self) -> str:
        """
        Этот метод возвращает строковое представление системы бота.
        Returns:
            str: Название класса.
        """
        return "HierarchyBot"


async def main():
    """Основная функция запуска бота."""
    bot = None
    shutdown_event = asyncio.Event()

    def signal_handler(signum: int, frame) -> None:
        """
        Этот метод обрабатывает сигналы завершения (Ctrl+C и Ctrl+Z, к примеру).
        Args:
            signum: Код сигнала.
            frame: Обработчик.
        """
        _ = frame
        logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
        shutdown_event.set()

    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(
        signal.SIGTERM, signal_handler
    )  # kill (Ctrl+Z, а также прямой kill из командной строки ps или Task Manager)

    try:
        # Инициализация бота
        bot = BotInstance()
        await bot.initialize()

        # Запуск бота
        await bot.start()

        # Ожидание сигнала завершения
        await shutdown_event.wait()
        logger.info("Shutdown signal received. Stopping bot...")

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping bot...")
    except Exception as ex:
        logger.critical(f"Unhandled exception: {ex}")
        logger.exception("Full traceback:")
    finally:
        if bot:
            await bot.shutdown()

        logger.info("Bot process terminated")
        sys.exit(0)


def validate_environment():
    """Проверка окружения перед запуском."""
    logger.info("Validating environment...")

    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_TOKEN_HERE":
        logger.critical("TELEGRAM_TOKEN is not set or contains default value")
        sys.exit(1)


if __name__ == "__main__":
    # Настройка обработки ошибок на уровне процесса
    def handle_unhandled_exception(_loop, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Этот метод является глобальным обработчиком для необработанных исключений.
        Args:
            _loop: Событие цикла.
            context (ContextTypes): Контекст приложения.
        """
        _ = _loop
        exception = context.get("exception")
        logger.critical(f"Unhandled exception in event loop: {exception}")
        logger.error(f"Exception context: {context}")

    loop = asyncio.new_event_loop()
    loop.set_exception_handler(handle_unhandled_exception)
    asyncio.set_event_loop(loop)

    try:
        validate_environment()
        # Запуск основной функции
        loop.run_until_complete(main())

    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        logger.exception("Full traceback:")
        sys.exit(1)
    finally:
        # Закрытие цикла событий
        loop.close()
        logger.info("Event loop closed")
