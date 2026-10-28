"""Создание Telegram-приложения и регистрация обработчиков."""

import logging
import os

from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from handlers import handle_error, handle_location, my_id_command, say_hi, wake_up

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


def run_bot() -> None:
    """Загружает секреты, проверяет TOKEN и запускает polling."""
    load_dotenv()
    token = (os.getenv('TOKEN') or '').strip()

    # Часть 3: проверка обязательной переменной окружения до запуска.
    if not token or ':' not in token:
        raise RuntimeError(
            'Ошибка настройки: заполните TOKEN в файле .env '
            '(получить токен можно у @BotFather).'
        )

    if not os.getenv('TOKEN_WEATHER'):
        logger.warning('TOKEN_WEATHER не задан: функция погоды будет недоступна.')

    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler('start', wake_up))
    application.add_handler(CommandHandler('myid', my_id_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, say_hi))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))

    # Часть 3: последние непредвиденные ошибки обработчиков попадают в журнал.
    application.add_error_handler(handle_error)

    logger.info('Бот запущен. Для остановки нажмите Ctrl+C.')
    application.run_polling()
