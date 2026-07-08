from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from local_settings import MONGO_URI, MONGO_COLLECTION_NAME
from logger_config import app_logger


def write_search_log(search_word=None, category=None, year=None, results_count=0):
    """
    Функция логирования поискового запроса пользователя в удаленную БД MongoDB.
    """
    # 1. Формируем структуру документа (Лога)
    # Собираем только те параметры, которые пользователь реально ввел
    search_params = {}
    if search_word: search_params['search_word'] = search_word
    if category: search_params['category'] = category
    if year:
        search_params['year'] = year

    # Определяем тип поиска на основе заполненных полей
    if search_word and not category and not year:
        search_type = "by_keyword"
    elif year and not search_word and not category:
        search_type = "by_year"
    elif category and not search_word and not year:
        search_type = "by_category"
    else:
        search_type = "mixed"  # Смешанный поиск по нескольким фильтрам

    log_document = {
        "timestamp": datetime.now(timezone.utc),  # Точное время в UTC
        "search_type": search_type,
        "params": search_params,
        "results_count": results_count
    }

    # 2. Подключаемся к MongoDB и записываем документ
    client = None

    try:
        # Создаем клиента (тайм-аут 5 секунд, чтобы скрипт не зависал при плохой сети)
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)

        # Подключаемся к базе данных. Обычно имя базы зашито в URI,
        # в текущей реализации используется локальная база
        # Если есть конкретное имя БД, нужно заменить client.get_default_database() на client['имя_бд']
        # db = client.get_default_database()db = client.get_default_database
        db = client['sakila_logs']
        collection = db[MONGO_COLLECTION_NAME]

        # Вставляем документ в коллекцию
        result = collection.insert_one(log_document)
        print(f"Лог поиска успешно записан в MongoDB. ID: {result.inserted_id}")
        app_logger.info(f"Лог поиска успешно записан в MongoDB. ID: {result.inserted_id}")
        return True

    except PyMongoError as err:
        print(f"Критическая ошибка записи лога в MongoDB: {err}")
        app_logger.error(f"Критическая ошибка записи лога в MongoDB: {err}")
        return False
    finally:
        client.close()


# Блок для локального тестирования записи логов
if __name__ == "__main__":
    print("Тестирование отправки лога в удаленную MongoDB...")
    # Имитируем, что пользователь искал фильм 'dinosaur' в жанре 'Action' и нашлось 3 фильма
    write_search_log(search_word="dinosaur", category="Action", results_count=3)
