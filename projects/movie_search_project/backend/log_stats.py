from datetime import timezone
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from local_settings import MONGO_URI, MONGO_COLLECTION_NAME


def get_top_5_searches():
    """
    Синхронная функция агрегации логов из MongoDB.
    Возвращает Топ-5 самых популярных поисковых запросов пользователей.
    """
    client = None
    try:
        # Подключение к локальной БД
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
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
        print(f"[MongoDB] Ошибка при получении статистики топ-5: {err}")
        return []
    finally:
        if client is not None:
            client.close()


def get_last_5_searches():
    """
    Синхронно извлекает 5 последних уникальных поисковых запросов пользователей из MongoDB,
    оставляя только самую свежую запись из повторяющихся.
    """
    client = None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        db = client['sakila_logs']
        collection = db[MONGO_COLLECTION_NAME]

        # Конвейер агрегации для поиска уникальных последних логов
        pipeline = [
            # 1. Фильтруем, убирая пустые логи стартового экрана
            {
                "$match": {"params": {"$ne": {}}}
            },
            # 2. Сортируем по времени (от новых к старым), чтобы $first взял самую свежую запись
            {
                "$sort": {"timestamp": -1}
            },
            # 3. Группируем по параметрам поиска (убираем дубликаты)
            {
                "$group": {
                    "_id": "$params",  # Группировка по уникальному набору фильтров
                    "latest_timestamp": {"$first": "$timestamp"},  # Берем самое свежее время
                    "search_type": {"$first": "$search_type"},
                    "results_count": {"$first": "$results_count"}
                }
            },
            # 4. Снова сортируем уже уникальные результаты по времени
            {
                "$sort": {"latest_timestamp": -1}
            },
            # 5. Ограничиваем выборку пятью строками
            {
                "$limit": 5
            }
        ]

        cursor = collection.aggregate(pipeline)

        last_searches = []
        for index, item in enumerate(cursor, start=1):
            utc_time = item["latest_timestamp"]

            # Конвертируем UTC-время из MongoDB в локальное время вашего ПК
            if utc_time.tzinfo is None:
                utc_time = utc_time.replace(tzinfo=timezone.utc)
            local_time = utc_time.astimezone(None)
            formatted_time = local_time.strftime("%H:%M %d.%m.%Y")

            # Формируем красивую текстовую строку параметров
            p = item["_id"]  # В агрегации сгруппированные параметры лежат в поле _id

            param_parts = []
            if "search_word" in p and p['search_word']: param_parts.append(f"Текст: '{p['search_word']}'")
            if "category" in p and p['category']: param_parts.append(f"Жанр: {p['category']}")
            if "year" in p and p['year']: param_parts.append(f"Год: {p['year']}")

            params_str = ", ".join(param_parts) if param_parts else "Глобальный поиск"

            last_searches.append({
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
    from tabulate import tabulate

    print("Тестирование извлечения данных из MongoDB...")

    # Прямая проверка работы аналитики логов
    top = get_top_5_searches()
    last = get_last_5_searches()

    print("\nТоп-5 запросов:")
    print(tabulate(top, headers="keys", tablefmt="grid") if top else "Данных нет.")
    print("\nПоследние 5 запросов:")
    print(tabulate(last, headers="keys", tablefmt="grid") if last else "Данных нет.")

