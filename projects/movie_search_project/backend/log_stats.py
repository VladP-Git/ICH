from pymongo import MongoClient
from pymongo.errors import PyMongoError
from local_settings import MONGO_URI, MONGO_COLLECTION_NAME


def get_top_5_searches():
    """
    Функция агрегации логов из MongoDB.
    Возвращает Топ-5 самых популярных поисковых запросов пользователей.
    """
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


# Блок для локального тестирования агрегации в консоли PyCharm
if __name__ == "__main__":
    print("Тестирование извлечения Топ-5 поисковых запросов из MongoDB...")

    # Чтобы статистика была наглядной, запишем еще пару разных логов для теста
    from log_writer import write_search_log

    write_search_log(search_word="dinosaur", results_count=5)
    write_search_log(search_word="dinosaur", results_count=5)
    write_search_log(search_word="matrix", results_count=1)

    # Вызываем нашу функцию статистики
    stats = get_top_5_searches()

    if stats:
        from tabulate import tabulate

        print("\nРезультаты агрегации (Топ-5):")
        print(tabulate(stats, headers="keys", tablefmt="grid"))
    else:
        print("Статистика пуста. Добавьте больше логов с заполнением 'search_word'.")
