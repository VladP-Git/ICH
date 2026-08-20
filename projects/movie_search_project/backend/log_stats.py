"""Модуль аналитики и агрегации логов из NoSQL СУБД MongoDB.

Использует продвинутые конвейеры агрегации (Aggregation Pipeline) базы данных
MongoDB для расчета топ-5 популярных поисковых запросов пользователей и выборки
последней уникальной истории поиска в режиме реального времени.
"""

from datetime import timezone
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from local_settings import MONGO_URI, MONGO_COLLECTION_NAME


# ─── ПРЕЗЕНТАЦИЯ: КОНВЕЙЕР АГРЕГАЦИИ NOSQL ДАННЫХ (TOP-5 AGGREGATION) ───────
def get_top_5_searches() -> list[dict]:
    """Синхронная функция агрегации документов из NoSQL MongoDB.

    Использует оптимизированный Aggregation Pipeline для группировки логов
    по уникальным комбинациям параметров поиска, сортирует их по популярности
    и возвращает форматированный список топ-5 лидеров для фронтенда.

    Returns:
        list[dict]: Список словарей, каждый из которых содержит ранг (#1-#5),
                    человекочитаемую строку параметров и счетчик повторений.
    """
    client = None
    try:
        # Устанавливаем соединение с коротким таймаутом для обеспечения отказоустойчивости
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        db = client['sakila_logs']
        collection = db[MONGO_COLLECTION_NAME]

        # 🎯: Объяснение этапов работы конвейера MongoDB
        pipeline = [
            # ЭТАП 1: $match — отсекаем системные стартовые пустые логи (где params: {})
            {
                "$match": {"params": {"$ne": {}}}
            },
            # ЭТАП 2: $group — схлопываем коллекцию по всему составному объекту параметров.
            # СУБД считает точное количество вызовов конкретного пересечения фильтров.
            {
                "$group": {
                    "_id": "$params",
                    "count": {"$sum": 1}
                }
            },
            # ЭТАП 3: $sort — упорядочиваем результаты по убыванию популярности (-1)
            {
                "$sort": {"count": -1}
            },
            # ЭТАП 4: $limit — отсекаем всё, кроме первых 5 записей-лидеров (Топ-5)
            {
                "$limit": 5
            }
        ]

        # Выполняем нативную агрегацию на стороне сервера базы данных
        results = list(collection.aggregate(pipeline))

        top_searches = []
        # Трансформируем сырые NoSQL структуры в презентабельный вид для Jinja2
        for index, item in enumerate(results, start=1):
            p = item["_id"]

            # ПОЧЕМУ ТАК: Формируем красивую строку критериев для ячеек таблицы
            param_parts = []
            if "search_word" in p and p['search_word']:
                param_parts.append(f"Текст: '{p['search_word']}'")
            if "category" in p and p['category']:
                param_parts.append(f"Жанр: {p['category']}")
            if "year" in p and p['year']:
                param_parts.append(f"Год: {p['year']}")

            params_str = ", ".join(param_parts) if param_parts else "Глобальный поиск"

            top_searches.append({
                "rank": f"#{index}",
                "keyword": params_str,
                "count": item["count"]
            })

        return top_searches

    except PyMongoError as err:
        print(f"[MongoDB] Ошибка при получении статистики топ-5: {err}")
        return []
    finally:
        if client is not None:
            client.close()  # Гарантированный возврат сокета операционной системе

# ─── ПРЕЗЕНТАЦИЯ: ВЫБОРКА УНИКАЛЬНОЙ ИСТОРИИ (LAST-5 UNIQUE SEARCHES) ───────
def get_last_5_searches() -> list[dict]:
    """Синхронно извлекает 5 последних уникальных поисковых запросов из MongoDB.

    Использует сложную многоступенчатую агрегацию для фильтрации дубликатов,
    оставляя для каждой повторяющейся комбинации фильтров только её самую
    свежую отметку времени, и конвертирует системное UTC время в локальное.

    Returns:
        list[dict]: Список словарей, содержащих локальное время запроса,
                    его тип, строковое представление параметров и счетчик результатов.
    """
    client = None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        db = client['sakila_logs']
        collection = db[MONGO_COLLECTION_NAME]

        # 🎯: Обоснование структуры уникальной истории
        pipeline = [
            # ЭТАП 1: Исключаем холостые визиты стартового экрана
            {
                "$match": {"params": {"$ne": {}}}
            },
            # ЭТАП 2: Сортируем от новых к старым. Это подготавливает оператор $first
            # к захвату исключительно самой свежей даты во время группировки.
            {
                "$sort": {"timestamp": -1}
            },
            # ЭТАП 3: Схлопываем дубликаты. Группируем по объекту параметров.
            # Если пользователь искал одно и то же, таблица не забьется повторами.
            {
                "$group": {
                    "_id": "$params",
                    "latest_timestamp": {"$first": "$timestamp"},  # Берем самый свежий лог
                    "search_type": {"$first": "$search_type"},
                    "results_count": {"$first": "$results_count"}
                }
            },
            # ЭТАП 4: Повторно сортируем сгруппированные уникальные сущности по свежести
            {
                "$sort": {"latest_timestamp": -1}
            },
            # ЭТАП 5: Ограничиваем срез до 5 последних уникальных событий
            {
                "$limit": 5
            }
        ]

        cursor = collection.aggregate(pipeline)

        last_searches = []
        for index, item in enumerate(cursor, start=1):
            utc_time = item["latest_timestamp"]

            # ПОЧЕМУ ТАК: MongoDB хранит время в UTC. Конвертируем его в таймзону
            # хост-машины (сервера/ПК разработчика), чтобы пользователь видел точные часы своего региона.
            if utc_time.tzinfo is None:
                utc_time = utc_time.replace(tzinfo=timezone.utc)
            local_time = utc_time.astimezone(None)
            formatted_time = local_time.strftime("%H:%M %d.%m.%Y")

            p = item["_id"]

            # Конструируем строковое представление фильтров для ячейки таблицы
            param_parts = []
            if "search_word" in p and p['search_word']:
                param_parts.append(f"Текст: '{p['search_word']}'")
            if "category" in p and p['category']:
                param_parts.append(f"Жанр: {p['category']}")
            if "year" in p and p['year']:
                param_parts.append(f"Год: {p['year']}")

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


# ─── ПРЕЗЕНТАЦИЯ: ИНТЕГРАЦИОННЫЙ ЛОКАЛЬНЫЙ ТЕСТ АНАЛИТИКИ ───────────────────
if __name__ == "__main__":
    from tabulate import tabulate

    print("Тестирование извлечения данных из MongoDB...")

    # Самостоятельная изоляция логики от веб-сервера FastAPI для быстрой отладки
    top = get_top_5_searches()
    last = get_last_5_searches()

    print("\nТоп-5 запросов:")
    print(tabulate(top, headers="keys", tablefmt="grid") if top else "Данных нет.")
    print("\nПоследние 5 запросов:")
    print(tabulate(last, headers="keys", tablefmt="grid") if last else "Данных нет.")
