"""Переиспользуемые функции: пользователь и три внешних API."""

import asyncio
import ipaddress
import logging
import os
from typing import TYPE_CHECKING
from urllib.parse import quote

import aiohttp

if TYPE_CHECKING:
    from telegram import Update

logger = logging.getLogger(__name__)

# Часть 3: URL вынесены в константы, их можно временно изменить для тестов.
CAT_API_URL = 'https://api.thecatapi.com/v1/images/search' 
IP_API_URL = 'https://api.ipify.org'
WEATHER_API_URL = 'https://api.openweathermap.org/data/2.5/weather'
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=8, sock_read=10)


class ExternalAPIError(Exception):
    """Ожидаемая ошибка при получении/разборе ответа внешнего API."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def get_user_info(update: 'Update') -> tuple[int, str, str, str, int]:
    """Возвращает chat_id, имя, полное имя, URL аватара, user_id."""
    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message
    if user is None or chat is None:
        raise ValueError('В обновлении Telegram отсутствует пользователь или чат')

    first_name = user.first_name or ''
    last_name = user.last_name or ''
    full_name = f'{first_name} {last_name}'.strip()
    timestamp = int(message.date.timestamp()) if message and message.date else 0
    avatar_seed = quote(f'{user.username or user.id}{timestamp}', safe='')
    avatar_url = f'https://robohash.org/{avatar_seed}?set=set4'
    return chat.id, first_name, full_name, avatar_url, user.id


async def fetch_json(url: str, *, params: dict | None = None):
    """GET + JSON с обработкой пустого URL, HTTP, таймаута и неверного JSON."""
    # Часть 3: LBYL — заранее проверяем заведомо ошибочный URL.
    if not url or not url.strip():
        raise ExternalAPIError('Адрес API пустой. Проверьте константу URL.')

    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.get(url, params=params) as response:
                # Код HTTP >= 400 преобразуем в понятное исключение.
                response.raise_for_status()
                return await response.json()
    except aiohttp.ClientResponseError as exc:
        logger.warning('API ответил HTTP %s: %s', exc.status, url)
        raise ExternalAPIError(f'Ошибка HTTP {exc.status}', status=exc.status) from exc
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        logger.warning('Ошибка API (%s): %s', url, exc)
        raise ExternalAPIError('Ошибка соединения или неверный JSON') from exc


async def get_cat_url() -> str:
    """Возвращает случайную картинку из TheCatAPI."""
    data = await fetch_json(CAT_API_URL)
    # Часть 3: обработка неполного JSON (IndexError, KeyError, TypeError).
    try:
        url = data[0]['url']
        if not isinstance(url, str) or not url.startswith(('https://', 'http://')):
            raise ValueError('Неверная ссылка на картинку')
        return url
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise ExternalAPIError('TheCatAPI вернул неполные данные') from exc


async def get_server_ip() -> str:
    """Определяет внешний IP компьютера/сервера бота, а не пользователя."""
    data = await fetch_json(IP_API_URL, params={'format': 'json'})
    try:
        ip = data['ip']
        return str(ipaddress.ip_address(ip))
    except (KeyError, TypeError, ValueError) as exc:
        raise ExternalAPIError('ipify вернул некорректный IP') from exc


async def get_weather(lat: float, lon: float) -> str:
    """Получает текущую погоду по координатам и рекомендации по ветру."""
    api_key = (os.getenv('TOKEN_WEATHER') or '').strip()
    if not api_key:
        return 'Погода недоступна: укажите TOKEN_WEATHER в файле .env.'

    try:
        data = await fetch_json(
            WEATHER_API_URL,
            params={
                'appid': api_key,
                'lang': 'ru',
                'units': 'metric',
                'lat': lat,
                'lon': lon,
            },
        )
    except ExternalAPIError as exc:
        if exc.status == 401:
            return 'Ошибка погоды: неверный или неактивированный ключ OpenWeatherMap (401).'
        if exc.status == 429:
            return 'Слишком много запросов к погоде (429). Попробуйте позже.'
        logger.warning('Погода недоступна: %s', exc)
        return 'Не удалось получить погоду. Проверьте соединение и адрес API.'

    try:
        city = data.get('name') or 'Неизвестное место'
        description = data['weather'][0]['description']
        temp = float(data['main']['temp'])
        feels_like = float(data['main']['feels_like'])
        wind_speed = float(data['wind']['speed'])
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        logger.warning('Неверный JSON от OpenWeatherMap: %s', exc)
        return 'Ошибка обработки данных погоды: ответ API неполный.'

    if wind_speed < 5:
        recommendation = 'Погода хорошая, ветра почти нет.'
    elif wind_speed < 10:
        recommendation = 'На улице ветрено, оденьтесь чуть теплее.'
    elif wind_speed < 20:
        recommendation = 'Ветер очень сильный, будьте осторожны.'
    else:
        recommendation = 'На улице штормовой ветер, лучше остаться дома.'

    return (
        f'Сейчас в {city}: {description}\n'
        f'Температура: {temp:g}°C (ощущается как {feels_like:g}°C)\n'
        f'Ветер: {wind_speed:g} м/с\n'
        f'{recommendation}'
    )
