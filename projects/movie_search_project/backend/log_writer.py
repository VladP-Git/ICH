"""Модуль логирования поисковых запросов в NoSQL СУБД MongoDB.

Реализует декларативный механизм фиксации пользовательской активности
через кастомный декоратор @log_search, выполняющий структурирование
и нормализацию параметров поиска, а также защиту аналитики от накрутки при пагинации.
"""

import functools
from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from local_settings import MONGO_URI, MONGO_COLLECTION_NAME
from logger_config import app_logger


def log_search(func):
    """Декоратор для декларативного NoSQL-логирования поисковых запросов в MongoDB.

    Перехватывает параметры выполнения оборачиваемой функции поиска, вычисляет
    текущую страницу пагинации и осуществляет запись метаданных поиска
    только в случае первичной инициализации запроса пользователем.

    Args:
        func: Оборачиваемая функция поиска фильмов (get_movies).

    Returns:
        Callable: Функция-обертка (wrapper), обогащенная логикой логирования.
    """
    # 🎯: @functools.wraps копирует метаданные (__doc__, __name__)
    # оригинальной функции внутрь wrapper, сохраняя прозрачность для систем документации.
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Извлекаем маркер поиска, чтобы исключить его попадание в параметры MySQL
        search_submitted = kwargs.get('search_submitted', None)

        # Выполняем базовую функцию получения фильмов из базы Sakila
        result = func(*args, **kwargs)

        movies, total_movies = result if isinstance(result, tuple) else ([], 0)

        limit = kwargs.get('limit', 10)
        offset = kwargs.get('offset', 0)
        current_page = (offset // limit) + 1

        # ─── ПРЕЗЕНТАЦИЯ: ЗАЩИТА АНАЛИТИКИ ОТ НАКРУТКИ ПАГИНАЦИЕЙ ────────────────
        # ПОЧЕМУ ТАК: Фиксируем документ в MongoDB строго на 1-й странице поиска.
        # Это исключает дублирование логов и накрутку счетчиков при обычном скроллинге.
        if search_submitted == '1' and current_page == 1:
            search_word = kwargs.get('search_word')
            category = kwargs.get('category')
            year_from = kwargs.get('year_from')
            year_to = kwargs.get('year_to')

            search_params = {}
            if search_word:
                # ПОЧЕМУ ТАК: Приведение к нижнему регистру необходимо для точной группировки в Топ-5
                search_params['search_word'] = str(search_word).lower()
            if category:
                search_params['category'] = category
            if year_from or year_to:
                search_params['year'] = f"{year_from or ''}-{year_to or ''}"

            log_document = {
                "timestamp": datetime.now(timezone.utc),
                "search_type": "mixed" if len(search_params) > 1 else "single",
                "params": search_params,
                "results_count": total_movies
            }

            # ─── ПРЕЗЕНТАЦИЯ: БЕЗОПАСНОЕ СОЕДИНЕНИЕ С NOSQL ──────────────────────
            client = None
            try:
                # ПОЧЕМУ ТАК: Ограничиваем ожидание СУБД до 3 секунд. Если MongoDB «упала»,
                # бэкенд зафиксирует ошибку в логгере, но продолжит выдавать фильмы из MySQL.
                client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
                db = client['sakila_logs']
                collection = db[MONGO_COLLECTION_NAME]
                res = collection.insert_one(log_document)
                app_logger.info(f"[PyMongo NoSQL] Лог поиска сохранен. ID: {res.inserted_id}")
            except PyMongoError as err:
                app_logger.error(f"[PyMongo NoSQL] Ошибка логирования: {err}")
            finally:
                if client is not None:
                    client.close()  # Гарантированно освобождаем сокет операционной системы

        return result

    return wrapper
