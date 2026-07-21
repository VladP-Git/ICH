import functools
import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
from local_settings import MONGO_URI, MONGO_COLLECTION_NAME
from logger_config import app_logger


def async_log_search():
    """
    Асинхронный декоратор для NoSQL-логирования поисковых запросов в MongoDB.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Извлекаем и удаляем маркер поиска, чтобы не сломать MySQL
            search_submitted = kwargs.pop('search_submitted', None)

            # --- ОЧИСТКА ОТ КОСТЫЛЕЙ: Теперь функция всегда асинхронная! ---
            # Больше никаких run_in_executor и проверок iscoroutinefunction.
            # Просто вызываем и ждем результат через await в едином потоке
            result = await func(*args, **kwargs)

            movies, total_movies = result if isinstance(result, tuple) else ([], 0)

            limit = kwargs.get('limit', 10)
            offset = kwargs.get('offset', 0)
            current_page = (offset // limit) + 1

            # Логируем строго при нажатии кнопки "Искать" на первой странице
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

                async def _save_to_mongo():
                    client = None
                    try:
                        client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=3000)
                        db = client['sakila_logs']
                        collection = db[MONGO_COLLECTION_NAME]
                        res = await collection.insert_one(log_document)
                        app_logger.info(f"[Motor NoSQL] Лог поиска асинхронно сохранен. ID: {res.inserted_id}")
                    except PyMongoError as err:
                        app_logger.error(f"[Motor NoSQL] Ошибка асинхронного логирования: {err}")
                    finally:
                        if client is not None:
                            client.close()

                asyncio.create_task(_save_to_mongo())

            return result

        return wrapper

    return decorator
