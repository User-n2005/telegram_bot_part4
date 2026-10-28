"""Команды, кнопки и геолокация Telegram-бота."""

import logging

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from utils import ExternalAPIError, get_cat_url, get_server_ip, get_user_info, get_weather

logger = logging.getLogger(__name__)

# Часть 3: резервные координаты при отсутствии геолокации (Москва).
MOSCOW_LAT, MOSCOW_LON = 55.7558, 37.6173


def main_keyboard() -> ReplyKeyboardMarkup:
    """Один вариант меню для /start и возврата после погоды."""
    return ReplyKeyboardMarkup(
        [
            ['Фото котика', 'Сгенери аватар'],
            ['Мой ID', 'IP сервера'],
            ['Погода сегодня'],
        ],
        resize_keyboard=True,
    )


async def wake_up(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает /start."""
    chat_id, _, full_name, _, _ = get_user_info(update)
    await context.bot.send_message(
        chat_id=chat_id,
        text=f'Привет {full_name}, спасибо, что присоединился!',
        reply_markup=main_keyboard(),
    )


async def say_hi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает кнопки и обычные текстовые сообщения."""
    message = update.effective_message
    if message is None or not message.text:
        return

    chat_id, first_name, _, avatar_url, user_id = get_user_info(update)
    text = message.text

    if text == 'Сгенери аватар':
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=avatar_url)
        except TelegramError as exc:
            logger.warning('Не удалось отправить аватар: %s', exc)
            await message.reply_text('Не получилось отправить аватар. Попробуйте позже.')

    elif text == 'Мой ID':
        await message.reply_text(f'Твой ID: {user_id}')

    elif text == 'Фото котика':
        try:
            cat_url = await get_cat_url()
            await context.bot.send_photo(chat_id=chat_id, photo=cat_url)
        except (ExternalAPIError, TelegramError) as exc:
            logger.warning('Не удалось получить или отправить котика: %s', exc)
            await message.reply_text('Котики временно недоступны 😿 Попробуйте позже.')

    elif text in ('IP сервера', 'Мой IP'):
        # Исправление предыдущей части: ipify показывает IP компьютера бота,
        # а НЕ реальный IP пользователя Telegram.
        try:
            ip = await get_server_ip()
            await message.reply_text(f'Публичный IP сервера бота: {ip}')
        except ExternalAPIError as exc:
            logger.warning('Не удалось получить IP сервера: %s', exc)
            await message.reply_text('Не удалось определить IP сервера.')

    elif text == 'Погода сегодня':
        await request_location(update, context)

    else:
        await message.reply_text(f'{first_name}, как твои дела?')


async def request_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запрашивает геолокацию для погоды."""
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton('Отправить координаты', request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.effective_message.reply_text(
        'Пожалуйста, поделитесь своей геолокацией:',
        reply_markup=keyboard,
    )


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает координаты и возвращает главное меню даже при ошибке."""
    message = update.effective_message
    if message is None:
        return

    prefix = ''
    location = message.location

    # Часть 3: проверяем отсутствующие или ошибочные координаты.
    try:
        if location is None:
            raise ValueError('Геолокация не передана')
        lat = float(location.latitude)
        lon = float(location.longitude)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('Координаты находятся вне допустимого диапазона')
    except (AttributeError, TypeError, ValueError) as exc:
        logger.warning('Не удалось прочитать геолокацию: %s', exc)
        lat, lon = MOSCOW_LAT, MOSCOW_LON
        prefix = 'Геолокация не получена. Показываю погоду для Москвы.\n'

    try:
        context.user_data['location'] = (lat, lon)
        report = await get_weather(lat, lon)
    except Exception:
        # Последний рубеж на случай неожиданной ошибки внутри обработчика.
        logger.exception('Ошибка обработки геолокации')
        report = 'Не удалось обработать геолокацию.'

    # В отличие от сообщения из одного пробела — нормальный текст с клавиатурой.
    await message.reply_text(prefix + report, reply_markup=main_keyboard())


async def my_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает /myid."""
    _, _, _, _, user_id = get_user_info(update)
    await update.effective_message.reply_text(f'Твой ID: {user_id}')


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует неожиданные исключения, чтобы бот продолжал работу."""
    logger.error('Необработанная ошибка Telegram-бота', exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                'Произошла непредвиденная ошибка. Попробуйте ещё раз позже.',
                reply_markup=main_keyboard(),
            )
        except TelegramError:
            logger.exception('Не удалось сообщить пользователю об ошибке')
