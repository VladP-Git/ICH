from pymongo import MongoClient
from pymongo.errors import PyMongoError
from datetime import timezone
from local_settings import MONGO_URI, MONGO_COLLECTION_NAME


def get_top_5_searches():
    """
    Функция агрегации логов из MongoDB.
    Возвращает Топ-5 самых популярных поисковых запросов пользователей.
    """

    client = None

    try:
        # Подключение к локальной БД
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client['sakila_logs']
        collection = db[MONGO_COLLECTION_NAME]

        # Конвейер агрегации MongoDB
        pipeline = [
            # Шаг 1: Фильтруем логи, оставляя только те, где пользователь вводил текстовый запрос
            {
                "$match": {
                    "params.search_word": {"$exists": True, "$ne": ""}
                }
            },
            # Шаг 2: Группируем по поисковому слову и считаем количество (count)
            {
                "$group": {
                    "_id": "$params.search_word",  # Группируем вокруг значения ключевого слова
                    "count": {"$sum": 1}  # Прибавляем 1 за каждое совпадение
                }
            },
            # Шаг 3: Сортируем по количеству вызовов в порядке убывания (-1)
            {
                "$sort": {"count": -1}
            },
            # Шаг 4: Ограничиваем вывод пятью элементами
            {
                "$limit": 5
            }
        ]

        # Выполняем агрегацию
        results = list(collection.aggregate(pipeline))

        # Переформатируем результат для удобного вывода на веб-страницу
        top_searches = []
        for index, item in enumerate(results, start=1):
            top_searches.append({
                "rank": f"#{index}",
                "keyword": item["_id"],
                "count": item["count"]
            })

        return top_searches

    except PyMongoError as err:
        print(f"[MongoDB] Ошибка при получении статистики: {err}")
        return []
    finally:
        client.close()


def get_last_5_searches():
    """
    Извлекает 5 последних поисковых запросов пользователей из MongoDB.
    """
    client = None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client['sakila_logs']
        collection = db[MONGO_COLLECTION_NAME]

        # Находим документы, где есть параметры поиска, сортируем по убыванию времени и берем 5 штук
        cursor = collection.find({"params": {"$ne": {}}}).sort("timestamp", -1).limit(5)

        last_searches = []
        for index, item in enumerate(cursor, start=1):
            # Переводим UTC-время в читаемый локальный формат строки (Часы:Минуты День.Месяц)
            # .astimezone() без аргументов автоматически переведет UTC-время из базы в локальное время
            utc_time = item["timestamp"]

            # 1. Явно говорим Python, что это время в UTC
            if utc_time.tzinfo is None:
                utc_time = utc_time.replace(tzinfo=timezone.utc)
            # 2. Конвертируем в локальный часовой пояс вашего компьютера (.astimezone(None))
            local_time = utc_time.astimezone(None)
            # 3. Форматируем для таблицы
            formatted_time = local_time.strftime("%H:%M %d.%m.%Y")

            # Собираем текстовое описание параметров, чтобы вывести в таблицу
            p = item.get("params", {})
            param_parts = []
            if "search_word" in p: param_parts.append(f"Текст: '{p['search_word']}'")
            if "category" in p: param_parts.append(f"Жанр: {p['category']}")
            if "year" in p: param_parts.append(f"Год: {p['year']}")

            params_str = ", ".join(param_parts) if param_parts else "Пустой поиск"

            last_searches.append({
                "index": index,
                "time": formatted_time,
                "type": item.get("search_type", "mixed"),
                "params": params_str,
                "results": item.get("results_count", 0)
            })

        return last_searches

    except PyMongoError as err:
        print(f"[MongoDB] Ошибка при получении последних запросов: {err}")
        return []
    finally:
        if client is not None:
            client.close()


# Блок для локального тестирования агрегации в консоли PyCharm
if __name__ == "__main__":
    print("Тестирование извлечения Топ-5 поисковых запросов из MongoDB...")

    # Чтобы статистика была более наглядной, запишется несколько разных логов для теста
    from log_writer import write_search_log

    write_search_log(search_word="dinosaur", results_count=5)
    write_search_log(search_word="dinosaur", results_count=5)
    write_search_log(search_word="matrix", results_count=1)

    # Вызываем функцию статистики
    stats = get_top_5_searches()

    if stats:
        from tabulate import tabulate

        print("\nРезультаты агрегации (Топ-5):")
        print(tabulate(stats, headers="keys", tablefmt="grid"))
    else:
        print("Статистика пуста. Добавьте больше логов с заполнением 'search_word'.")
