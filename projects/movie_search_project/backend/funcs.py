import math
import time
from fastapi import Request
from logger_config import app_logger
from mysql_connector import get_movies, get_all_categories, get_year_bounds
from log_stats import get_top_5_searches, get_last_5_searches
from log_writer import log_search


# Применяем оптимизированный декоратор. Внутренняя функция поглощает
# search_submitted для логов и передает в MySQL только чистые параметры.
@log_search
def _fetch_movies_with_logging(search_submitted, search_word, category, year_from, year_to, limit, offset):
    return get_movies(
        search_word=search_word,
        category=category,
        year_from=year_from,
        year_to=year_to,
        limit=limit,
        offset=offset
    )


def prepare_index_context(request: Request) -> dict:
    """
    Формирует полный набор данных для отображения главной страницы.
    Самостоятельно извлекает и валидирует Query-параметры из HTTP-запроса.
    """
    # Вытаскиваем параметры из строки запроса URL
    query = request.query_params
    app_logger.debug(f"Обработка фильтров. Параметры URL: {dict(query)}")

    # Извлекаем значения и очищаем от пробелов по краям
    search_submitted = query.get("search_submitted")
    search_word = query.get("search_word", "").strip()
    category = query.get("category", "").strip()
    year_from = query.get("year_from", "").strip()
    year_to = query.get("year_to", "").strip()
    view_mode = query.get("view_mode", "adaptive")

    # Валидация номера страницы (номер должен быть целым числом не меньше 1)
    try:
        page = int(query.get("page", 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1

    # Рассчитываем количество карточек на страницу
    limit = 10 if view_mode == "strict" else 6
    offset = (page - 1) * limit

    # Подготавливаем фильтры для SQL-строителя
    s_word = search_word if search_word else None
    cat = category if category else None
    yr_from = int(year_from) if year_from and year_from.isdigit() else None
    yr_to = int(year_to) if year_to and year_to.isdigit() else None

    # Извлекаем метаданные для формы из MySQL
    start_mysql = time.time()
    categories = get_all_categories()
    min_db_year, max_db_year = get_year_bounds()

    empty_search = False

    if search_submitted == '1':
        # Проверяем, заполнил ли пользователь хотя бы одно поле фильтра
        has_any_filter = bool(s_word or cat or yr_from or yr_to)

        if not has_any_filter:
            if page == 1:
                empty_search = True
            is_searched = False

            # Передаем именованные параметры, чтобы их перехватил декоратор логов
            movies, total_movies = _fetch_movies_with_logging(
                search_submitted=None,
                search_word=None,
                category="New",
                year_from=None,
                year_to=None,
                limit=limit,
                offset=offset
            )

            if page == 1:
                app_logger.info("[Поиск] Отправлен абсолютно пустой запрос. Отображен базовый каталог.")
            else:
                app_logger.info(f"[Пагинация] Просмотр страницы #{page} новинок проката")
        else:
            # Выполняем полноценный поиск по выбранным критериям
            is_searched = True

            # Строго именованная передача параметров для корректной работы **kwargs логгера
            movies, total_movies = _fetch_movies_with_logging(
                search_submitted=search_submitted,
                search_word=s_word,
                category=cat,
                year_from=yr_from,
                year_to=yr_to,
                limit=limit,
                offset=offset
            )

            if page == 1:
                app_logger.info(f"Выполнен поиск по фильтрам: текст='{s_word}', жанр='{cat}'. Найдено: {total_movies}")
            else:
                app_logger.info(f"[Пагинация] Переход на страницу #{page} для результатов поиска")
    else:
        # Стартовый экран при первом посещении сайта
        is_searched = False

        movies, total_movies = _fetch_movies_with_logging(
            search_submitted=None,
            search_word=None,
            category="New",
            year_from=None,
            year_to=None,
            limit=limit,
            offset=offset
        )
        if page == 1:
            app_logger.debug("Стартовый экран: загружена категория 'New' (Новинки проката)")
        else:
            app_logger.info(f"[Пагинация] Просмотр страницы #{page} новинок проката")

    app_logger.info(f"[TIME] Запрос к MySQL и сбор метаданных заняли: {time.time() - start_mysql:.2f} сек.")
    total_pages = math.ceil(total_movies / limit) if total_movies > 0 else 1

    return {
        "movies": movies,
        "search_word": search_word,
        "category": category,
        "year_from": year_from,
        "year_to": year_to,
        "min_db_year": min_db_year,
        "max_db_year": max_db_year,
        "is_searched": is_searched,
        "empty_search": empty_search,
        "categories": categories,
        "current_page": page,
        "total_pages": total_pages,
        "total_movies": total_movies,
        "view_mode": view_mode,
        "current_limit": limit
    }


def prepare_stats_context() -> dict:
    """Собирает агрегированные данные аналитики из MongoDB для страницы статистики."""
    top_searches = get_top_5_searches()
    last_searches = get_last_5_searches()
    return {
        "top_searches": top_searches,
        "last_searches": last_searches
    }
