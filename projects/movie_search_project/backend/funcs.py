"""Модуль бизнес-логики и координации данных веб-приложения Sakila Cinema.

Содержит функции подготовки контекста для шаблонизатора Jinja2,
валидации входящих HTTP-параметров и перехвата глобальных исключений.
"""

import math
import time
from fastapi import Request
from logger_config import app_logger
from fastapi.responses import HTMLResponse
from mysql_connector import get_movies, get_all_categories, get_year_bounds
from log_stats import get_top_5_searches, get_last_5_searches
from log_writer import log_search


# ─── ПРЕЗЕНТАЦИЯ: ДЕКЛАРАТИВНОЕ ЛОГИРОВАНИЕ NOSQL НА БАЗЕ ДЕКОРАТОРА ─────────
@log_search
def _fetch_movies_with_logging(
        search_submitted: str | None,
        search_word: str | None,
        category: str | None,
        year_from: int | None,
        year_to: int | None,
        limit: int,
        offset: int
) -> tuple[list[dict], int]:
    """Служебный прокси-метод для прозрачной интеграции MySQL и логирования в MongoDB.

    Аннотирован кастомным декоратором @log_search, который автоматически перехватывает
    именованные аргументы в момент вызова и фиксирует их в NoSQL базу данных аналитики.

    Args:
        search_submitted: Системный маркер отправки поисковой формы.
        search_word: Поисковое текстовое слово.
        category: Выбранный пользователем жанр фильма.
        year_from: Начальный год фильтрации.
        year_to: Конечный год фильтрации.
        limit: Количество записей для выборки СУБД (размер страницы).
        offset: Смещение выборки (пропущенные карточки).

    Returns:
        tuple[list[dict], int]: Кортеж из списка найденных фильмов и общего их числа.
    """
    # ПОЧЕМУ ТАК: Декоратор изолирует бэкенд от явного кода записи логов в базу MongoDB.
    # Код поиска ничего не знает о NoSQL, соблюдая принцип единственной ответственности.
    return get_movies(
        search_word=search_word,
        category=category,
        year_from=year_from,
        year_to=year_to,
        limit=limit,
        offset=offset
    )


# ─── ПРЕЗЕНТАЦИЯ: ЦЕНТРАЛЬНЫЙ АГРЕГАТОР ДАННЫХ ДЛЯ ШАБЛОНА ИНТЕРФЕЙСА ────────
def prepare_index_context(request: Request) -> dict:
    """Формирует, валидирует и агрегирует полный контекст данных для главной страницы.

    Самостоятельно парсит Query-параметры входящего HTTP-запроса, вычисляет
    границы пагинации с учетом режимов отображения (ТЗ/Демо) и координирует
    запросы к СУБД для вывода "Новинок" или результатов фильтрации.

    Args:
        request (Request): Объект входящего HTTP-запроса FastAPI.

    Returns:
        dict: Полный словарь переменных, готовый для передачи в шаблонизатор Jinja2.
    """
    # Извлекаем параметры из строки запроса URL
    query = request.query_params
    app_logger.debug(f"Обработка фильтров. Параметры URL: {dict(query)}")

    # Очищаем текстовые входные параметры от невидимых символов и концевых пробелов
    search_submitted = query.get("search_submitted")
    search_word = query.get("search_word", "").strip()
    category = query.get("category", "").strip()
    year_from = query.get("year_from", "").strip()
    year_to = query.get("year_to", "").strip()
    view_mode = query.get("view_mode", "adaptive")

    # ПОЧЕМУ ТАК: Защита от ручных манипуляций с URL. Предотвращает падения (ValueError)
    # при попытке передать в параметр страницы буквенный мусор или отрицательные числа.
    try:
        page = int(query.get("page", 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1

    # ПОЧЕМУ ТАК: Адаптивный формат. Позволяет прямо из веб-интерфейса переключаться
    # между жестким лимитом ТЗ (10 карточек) и демонстрационным режимом (6 карточек).
    limit = 10 if view_mode == "strict" else 6
    offset = (page - 1) * limit

    # Подготавливаем фильтры к отправке (пустые строки транслируем в SQL-совместимый None)
    s_word = search_word if search_word else None
    cat = category if category else None
    yr_from = int(year_from) if year_from and year_from.isdigit() else None
    yr_to = int(year_to) if year_to and year_to.isdigit() else None

    # Извлекаем справочные метаданные из MySQL для наполнения элементов формы
    start_mysql = time.time()
    categories = get_all_categories()
    min_db_year, max_db_year = get_year_bounds()

    empty_search = False

    # 🎯 ТОЧКА ВХОДА ПРЕЗЕНТАЦИИ: ОБРАБОТКА ПОЛЬЗОВАТЕЛЬСКОГО ДЕЙСТВИЯ
    if search_submitted == '1':
        # Проверяем, заполнил ли пользователь хотя бы одно поле в форме
        has_any_filter = bool(s_word or cat or yr_from or yr_to)

        # СЦЕНАРИЙ А: Кнопка нажата, но все поля пустые или заполнены пробелами
        if not has_any_filter:
            if page == 1:
                empty_search = True  # Активирует Bootstrap-инфоплашку на фронтенде
            is_searched = False

            # Отдаем дефолтную категорию, убирая флаг инициации поиска для MongoDB
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

        # СЦЕНАРИЙ Б: Пользователь действительно применил фильтры
        else:
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

    # СЦЕНАРИЙ В: Первое открытие сайта (холодный визит пользователя)
    else:
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

    # ПОЧЕМУ ТАК: Метрика времени выполнения I/O операций помогает контролировать скорость работы БД
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


# ─── ПРЕЗЕНТАЦИЯ: СБОР ДАННЫХ АНАЛИТИКИ ИЗ NOSQL ─────────────────────────────
def prepare_stats_context() -> dict:
    """Собирает агрегированные данные аналитики из MongoDB для страницы статистики.

    Служит точкой интеграции с аналитическим модулем для последующего
    динамического рендеринга таблиц популярности запросов на фронтенде.

    Returns:
        dict: Словарь, содержащий списки 'top_searches' (Топ-5) и 'last_searches' (Последние 5).
    """
    # ПОЧЕМУ ТАК: Делегируем сбор данных специализированным агрегационным функциям модуля log_stats
    top_searches = get_top_5_searches()
    last_searches = get_last_5_searches()
    return {
        "top_searches": top_searches,
        "last_searches": last_searches
    }


# ─── ПРЕЗЕНТАЦИЯ: ЦЕНТРАЛИЗОВАННЫЙ ОБРАБОТЧИК КРИТИЧЕСКИХ ОШИБОК ─────────────
def handle_global_exception(request: Request, exc: Exception) -> HTMLResponse:
    """Обеспечивает централизованную отказоустойчивость всего веб-приложения.

    Перехватывает любые непредвиденные исключения (например, падение СУБД MySQL),
    изолирует технический стек ошибки внутри защищенного лога и отдает пользователю
    дизайнерский интерфейс заглушки, предотвращая поломку UI.

    Args:
        request (Request): Входящий HTTP-запрос, во время которого произошел сбой.
        exc (Exception): Экземпляр перехваченного исключения.

    Returns:
        HTMLResponse: Пользовательская Bootstrap-страница с HTTP-статусом 500.
    """
    # ПОЧЕМУ ТАК: Системная безопасность. exc_info=True выгружает полный трассировочный
    # след (traceback) в app.log для отладки, скрывая уязвимости от глаз злоумышленника в браузере.
    app_logger.error(f"[КРИТИЧЕСКИЙ СБОЙ ВЕБ-ПРИЛОЖЕНИЯ]: {str(exc)}", exc_info=True)

    # ПОЧЕМУ ТАК: Встраиваем HTML прямо в бэкенд на случай, если папка templates/ заблокирована СУБД
    html_content = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Ошибка сервера — Sakila Cinema</title>
        <link href="/static/css/bootstrap.min.css" rel="stylesheet">
        <link href="/static/css/bootstrap-icons.min.css" rel="stylesheet">
    </head>
    <body class="bg-body-secondary d-flex align-items-center justify-content-center" style="height: 100vh;">
        <div class="text-center p-5 bg-white rounded-4 shadow-sm border border-light-subtle" style="max-width: 500px;">
            <i class="bi bi-exclamation-triangle-fill text-danger display-1 mb-4 d-block"></i>
            <h1 class="h3 fw-bold text-dark mb-3">Что-то пошло не так</h1>
            <p class="text-secondary mb-4 small">На стороне веб-сервера произошел непредвиденный сбой. Подробная информация уже зафиксирована в системном журнале отладки.</p>
            <a href="/" class="btn btn-primary px-4 py-2 rounded-3 fw-bold shadow-sm">
                <i class="bi bi-house-door-fill me-2"></i>На главную страницу
            </a>
        </div>
    </body>
    </html>
    """


    return HTMLResponse(content=html_content, status_code=500)