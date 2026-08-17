import functools
from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from local_settings import MONGO_URI, MONGO_COLLECTION_NAME
from logger_config import app_logger


def log_search():
    """
    Синхронный декоратор для NoSQL-логирования поисковых запросов в MongoDB.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Извлекаем и удаляем маркер поиска, чтобы не сломать MySQL
            search_submitted = kwargs.pop('search_submitted', None)

            # Вызываем синхронную функцию mysql_connector напрямую в этом же потоке
            result = func(*args, **kwargs)

            movies, total_movies = result if isinstance(result, tuple) else ([], 0)

            limit = kwargs.get('limit', 10)
            offset = kwargs.get('offset', 0)
            current_page = (offset // limit) + 1

            # Логируем строго при нажатии кнопки "Искать" на главной странице
            if search_submitted == '1' and current_page == 1:
                search_word = kwargs.get('search_word')
                category = kwargs.get('category')
                year_from = kwargs.get('year_from')
                year_to = kwargs.get('year_to')

                search_params = {}
                if search_word: search_params['search_word'] = str(search_word).lower()
                if category: search_params['category'] = category
                if year_from or year_to: search_params['year'] = f"{year_from or ''}-{year_to or ''}"

                log_document = {
                    "timestamp": datetime.now(timezone.utc),
                    "search_type": "mixed" if len(search_params) > 1 else "single",
                    "params": search_params,
                    "results_count": total_movies
                }

                # Синхронная запись в MongoDB
                client = None
                try:
                    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
                    db = client['sakila_logs']
                    collection = db[MONGO_COLLECTION_NAME]
                    res = collection.insert_one(log_document)
                    app_logger.info(f"[PyMongo NoSQL] Лог поиска сохранен. ID: {res.inserted_id}")
                except PyMongoError as err:
                    app_logger.error(f"[PyMongo NoSQL] Ошибка логирования: {err}")
                finally:
                    if client is not None:
                        client.close()

            return result

        return wrapper

    return decorator
