import os
import math
import time
from jinja2 import pass_context
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from log_decorator import async_log_search
from mysql_async_connector import get_movies_async, get_all_categories_async, get_year_bounds_async
from fastapi import Response  # Добавьте импорт в самый верх app_fastapi.py
from log_stats import get_top_5_searches, get_last_5_searches
from logger_config import app_logger

# Определяем базовую директорию проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Инициализируем FastAPI
app = FastAPI(title="Sakila Cinema - FastAPI Edition")

# Подключаем статические файлы (CSS, JS, картинки) по правилам FastAPI
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Настраиваем шаблонизатор Jinja2
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ТРЮК-ПЕРЕВОДЧИК: Перенаправляем аргумент 'filename' во внутренний 'path' для FastAPI
# Это позволит использовать один и тот же index.html и во Flask, и в FastAPI!
# НАДЕЖНЫЙ ПЕРЕВОДЧИК СИНТАКСИСА:
@pass_context
def fastapi_url_for(context: dict, name: str, **path_params):
    """
    Универсальный мост синтаксиса.
    Корректирует вызовы url_for из Flask под требования архитектуры FastAPI.
    """
    # Извлекаем объект request, который FastAPI автоматически прячет внутри контекста шаблона
    request = context["request"]

    # 1. Исправление для статических ресурсов (CSS/JS)
    # Если Jinja2 пытается вызвать статику по правилам Flask
    if name == 'static' and 'filename' in path_params:
        path_params['path'] = path_params.pop('filename')
        return request.url_for(name, **path_params)

    # 2. Исправление для ссылок пагинации главной страницы
    if name == 'index_page':
        # Перенаправляем вызов на имя функции роута внутри FastAPI (это имя 'index_page')
        # В FastAPI параметры Query-поиска передаются через URL, поэтому убираем их из path_params,
        # чтобы они автоматически приклеились как GET-параметры строки
        url = request.url_for('index_page')

        # Превращаем параметры в классическую GET-строку (?search_word=...&page=...)
        from urllib.parse import urlencode
        # Фильтруем пустые значения, чтобы ссылка была чистой
        clean_params = {k: v for k, v in path_params.items() if v is not None and v != ''}
        if clean_params:
            url = f"{url}?{urlencode(clean_params)}"
        return url

    return request.url_for(name, **path_params)


# Регистрируем функцию в глобальном окружении шаблонизатора FastAPI
templates.env.globals['url_for'] = fastapi_url_for


@app.get("/", response_class=HTMLResponse)
async def index_page(
        request: Request,
        search_submitted: str = Query(None),
        search_word: str = Query(""),
        category: str = Query(""),
        year_from: str = Query(""),
        year_to: str = Query(""),
        page: int = Query(1)
):
    # ДЕТАЛЬНЫЙ ТЕКСТОВЫЙ ЛОГ ЗАПРОСА С ПАРАМЕТРАМИ URL
    app_logger.debug(
        f"Получен GET-запрос к главной странице. Параметры URL: {dict(request.args if hasattr(request, 'args') else request.query_params)}")
    """
    Синхронный роут главной страницы в FastAPI.
    Использует старые коннекторы бэкенда.
    """
    # Очищаем строки от пробелов
    search_word = search_word.strip()
    category = category.strip()
    year_from = year_from.strip()
    year_to = year_to.strip()

    limit = 10
    offset = (page - 1) * limit

    s_word = search_word if search_word else None
    cat = category if category else None
    yr_from = int(year_from) if year_from and year_from.isdigit() else None
    yr_to = int(year_to) if year_to and year_to.isdigit() else None

    categories = await get_all_categories_async()
    min_db_year, max_db_year = await get_year_bounds_async()

    start_mysql = time.time()

    # Логика выбора фильмов (Новинки или Поиск)
    # Навешиваем декоратор на новую асинхронную функцию
    decorated_get_movies = async_log_search()(get_movies_async)

    if search_submitted == '1':
        is_searched = True

        # Запрашиваем порцию фильмов через await
        movies, total_movies = await decorated_get_movies(
            search_submitted=search_submitted,
            search_word=s_word, category=cat,
            year_from=yr_from, year_to=yr_to,
            limit=limit, offset=offset
        )

        # ВЫВОД ОДНОЗНАЧНЫХ СООБЩЕНИЙ В ЗАВИСИМОСТИ ОТ СТРАНИЦЫ
        if page == 1:
            app_logger.info(
                f"Выполнен новый поиск: текст='{s_word}', жанр='{cat}', диапазон={yr_from}-{yr_to}. Найдено: {total_movies}")
        else:
            # Однозначно пишем в лог, что пользователь просто листает страницы
            app_logger.info(f"[Пагинация] Переход на страницу #{page} для текущего поиска (текст='{s_word}')")
            # На всякий случай дублируем старый добрый консольный вывод для вас:
            print(f"[MongoDB] Пропуск логирования: переход по страницам существующего запроса (Страница #{page}).")

    else:
        is_searched = False
        # ПРИ СТАРТЕ САЙТА ПЕРЕДАЕМ search_submitted=None, ЧТОБЫ ДЕКОРАТОР НЕ ПИСАЛ ЛОГ
        movies, total_movies = await decorated_get_movies(
            search_submitted=None,
            category="New", limit=limit, offset=offset
        )
        if page == 1:
            app_logger.debug("Стартовый экран: загружена категория 'New' (Новинки проката)")
        else:
            app_logger.info(f"[Пагинация] Просмотр страницы #{page} новинок проката")

    # Выводим точный замер времени работы асинхронного пула MySQL
    app_logger.info(f"[TIME] Общая работа MySQL заняла: {time.time() - start_mysql:.2f} сек.")

    app_logger.info(f"[FastAPI] MySQL работа заняла: {time.time() - start_mysql:.2f} сек.")
    total_pages = math.ceil(total_movies / limit) if total_movies > 0 else 1

    # В FastAPI переменная request ОБЯЗАТЕЛЬНО должна передаваться в контекст Jinja2
    # Новый синтаксис FastAPI / Starlette
    return templates.TemplateResponse(
        request,  # Передаем request первым аргументом БЕЗ ключа
        "index.html",  # Имя шаблона вторым аргументом
        {  # Словарь данных (контекст) третьим аргументом
            "request": request,
            "movies": movies,
            "search_word": search_word,
            "category": category,
            "year_from": year_from,
            "year_to": year_to,
            "min_db_year": min_db_year,
            "max_db_year": max_db_year,
            "is_searched": is_searched,
            "categories": categories,
            "current_page": page,
            "total_pages": total_pages,
            "total_movies": total_movies
        }
    )


@app.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request):
    """
    Синхронный роут страницы статистики в FastAPI.
    """
    top_searches = get_top_5_searches()
    last_searches = get_last_5_searches()

    # Новый синтаксис FastAPI / Starlette
    return templates.TemplateResponse(
        request,
        "stats.html",
        {
            "top_searches": top_searches,
            "last_searches": last_searches
        }
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Глушит автоматические запросы браузера к иконке, убирая ошибку 404 из консоли."""
    return Response(status_code=204)


if __name__ == "__main__":
    import uvicorn

    # Запуск асинхронного сервера Uvicorn. Режим reload=True заменяет debug=True во Flask
    uvicorn.run("app_fastapi:app", host="127.0.0.1", port=5000, reload=True)
