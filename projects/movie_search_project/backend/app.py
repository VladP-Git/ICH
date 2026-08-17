import os
import math
import time
from jinja2 import pass_context
from fastapi import FastAPI, Request, Query, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from log_writer import log_search
from mysql_connector import get_movies, get_all_categories, get_year_bounds
from log_stats import get_top_5_searches, get_last_5_searches
from logger_config import app_logger

# Определяем базовую директорию проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Инициализируем FastAPI
app = FastAPI(title="Sakila Cinema - FastAPI Edition")

# Подключаем статические файлы (CSS, JS, картинки)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Настраиваем шаблонизатор Jinja2
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# Перенаправляем аргумент 'filename' во внутренний 'path' для FastAPI
# Это позволит использовать один и тот же index.html и во Flask, и в FastAPI!
@pass_context
def fastapi_url_for(context: dict, name: str, **path_params):
    """
    Универсальный мост синтаксиса.
    Корректирует вызовы url_for из Flask под требования архитектуры FastAPI.
    """
    # Извлекаем объект request, инкапсулированный FastAPI внутри контекста шаблона
    request = context["request"]

    # 1. Исправление для статических ресурсов (CSS/JS)
    # Если Jinja2 пытается вызвать статику по правилам Flask
    if name == 'static' and 'filename' in path_params:
        path_params['path'] = path_params.pop('filename')
        return request.url_for(name, **path_params)

    # 2. Исправление для ссылок пагинации главной страницы
    if name == 'index_page':
        # Генерируем базовый URL для эндпоинта главной страницы
        # Перенаправляем вызов на имя функции роута внутри FastAPI (это имя 'index_page')
        # В FastAPI параметры Query-поиска передаются через URL, поэтому убираем их из path_params,
        # чтобы они автоматически приклеились как GET-параметры строки
        url = request.url_for('index_page')

        # Превращаем параметры в классическую GET-строку (?search_word=...&page=...)
        from urllib.parse import urlencode
        # Очищаем GET-параметры от пустых значений для сохранения чистоты URL
        clean_params = {k: v for k, v in path_params.items() if v is not None and v != ''}
        # Если view_mode не передан в path_params, берем его из текущего request, чтобы сохранить состояние
        if 'view_mode' not in clean_params and 'view_mode' in request.query_params:
            clean_params['view_mode'] = request.query_params['view_mode']
        # Формируем валидную GET-строку (?search_word=...&page=...)
        if clean_params:
            url = f"{url}?{urlencode(clean_params)}"
        return url

    # Для всех остальных роутов (например, /stats) используем стандартный метод Starlette
    return request.url_for(name, **path_params)



# Регистрируем функцию в глобальном окружении шаблонизатора FastAPI
templates.env.globals['url_for'] = fastapi_url_for


# Классический синхронный GET-роут для главной страницы
@app.get("/", response_class=HTMLResponse)
def index_page(
        request: Request,
        search_submitted: str = Query(None),
        search_word: str = Query(""),
        category: str = Query(""),
        year_from: str = Query(""),
        year_to: str = Query(""),
        page: int = Query(1),
        view_mode: str = Query("adaptive")  # Новый параметр: по умолчанию "adaptive"
):
    # ДЕТАЛЬНЫЙ ТЕКСТОВЫЙ ЛОГ ЗАПРОСА С ПАРАМЕТРАМИ URL
    app_logger.debug(
        f"Получен GET-запрос к главной странице. Параметры URL: {dict(request.query_params)}")

    # Очищаем строки от пробелов

    search_word = search_word.strip()
    category = category.strip()
    year_from = year_from.strip()
    year_to = year_to.strip()

    # ДИНАМИЧЕСКИЙ РАСЧЕТ ЛИМИТА ИЗ РЕЖИМА ОТОБРАЖЕНИЯ
    # adaptive = 6 карточек (2 полных ряда по 3), strict = 10 карточек (по ТЗ)
    limit = 10 if view_mode == "strict" else 6
    offset = (page - 1) * limit

    s_word = search_word if search_word else None
    cat = category if category else None
    yr_from = int(year_from) if year_from and year_from.isdigit() else None
    yr_to = int(year_to) if year_to and year_to.isdigit() else None

    # Вызываем синхронные функции получения метаданных
    categories = get_all_categories()
    min_db_year, max_db_year = get_year_bounds()

    start_mysql = time.time()

    # Декорируем функцию поиска (вызывается синхронно)
    decorated_get_movies = log_search()(get_movies)

    # Новый маркер для фиксации абсолютно пустого ввода при отправке формы
    empty_search = False

    if search_submitted == '1':
        # Проверяем, выбрал ли пользователь ХОТЯ БЫ ОДИН критерий для фильтрации
        has_any_filter = bool(s_word or cat or yr_from or yr_to)

        if not has_any_filter:
            # Активируем уведомление строго на первой странице, при пагинации оно не появится.
            # АБСОЛЮТНО ПУСТОЙ ПОИСК (нет текста, нет жанра, нет годов)
            if page == 1:
                empty_search = True

            is_searched = False
            # Если пользователь выбрал жанр в селекторе, сохраняем его, иначе сбрасываем на "New"
            movies, total_movies = decorated_get_movies(
                search_submitted=None,  # Передаем None, чтобы NoSQL НЕ писал пустой лог
                category="New", limit=limit, offset=offset
            )

            if page == 1:
                app_logger.info(f"[Поиск] Отправлен абсолютно пустой запрос. Отображен базовый каталог.")
            else:
                app_logger.info(f"[Пагинация] Просмотр страницы #{page} новинок проката")

        else:
            # ПОЛНОЦЕННЫЙ ПОИСК (есть текст, ИЛИ выбран жанр, ИЛИ указаны годы)
            is_searched = True

            # Передаем маркер search_submitted дальше, чтобы декоратор залогировал этот поиск в MongoDB
            movies, total_movies = decorated_get_movies(
                search_submitted=search_submitted,
                search_word=s_word, category=cat,
                year_from=yr_from, year_to=yr_to,
                limit=limit, offset=offset
            )

            # Вывод сообщений в зависимости от страницы
            if page == 1:
                app_logger.info(
                    f"Выполнен поиск по фильтрам: текст='{s_word}', жанр='{cat}', диапазон={yr_from}-{yr_to}. Найдено: {total_movies}")
            else:
                # Пишем в лог, что пользователь просто листает страницы
                app_logger.info(f"[Пагинация] Переход на страницу #{page} для поиска (текст='{s_word}', жанр='{cat}')")

    else:
        # Стартовый экран (Новинки проката)
        is_searched = False
        # ПРИ СТАРТЕ САЙТА ПЕРЕДАЕМ search_submitted=None, ЧТОБЫ ДЕКОРАТОР НЕ ПИСАЛ ЛОГ
        movies, total_movies = decorated_get_movies(
            search_submitted=None,
            category="New", limit=limit, offset=offset
        )
        if page == 1:
            app_logger.debug("Стартовый экран: загружена категория 'New' (Новинки проката)")
        else:
            app_logger.info(f"[Пагинация] Просмотр страницы #{page} новинок проката")

    # Выводим точный замер времени работы синхронного пула MySQL
    app_logger.info(f"[TIME] Общая работа MySQL заняла: {time.time() - start_mysql:.2f} сек.")
    total_pages = math.ceil(total_movies / limit) if total_movies > 0 else 1

    # В FastAPI переменная request ОБЯЗАТЕЛЬНО должна передаваться в контекст Jinja2
    return templates.TemplateResponse(
        request,  # Идет самым первым аргументом
        "index.html",  # Имя шаблона — вторым аргументом
        {  # Словарь контекста — третьим аргументом
            "request": request,
            "movies": movies,
            "search_word": search_word,
            "category": category,
            "year_from": year_from,
            "year_to": year_to,
            "min_db_year": min_db_year,
            "max_db_year": max_db_year,
            "is_searched": is_searched,
            "empty_search": empty_search,  # ПЕРЕДАЕМ МАРКЕР ОШИБКИ В ШАБЛОН JINJA2
            "categories": categories,
            "current_page": page,
            "total_pages": total_pages,
            "total_movies": total_movies,
            "view_mode": view_mode,  # ОБЯЗАТЕЛЬНО передаем текущий режим в шаблон
            "current_limit": limit   # Передаем число для динамического текста на кнопке
        }
    )



# Чистый синхронный роут для страницы статистики
@app.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request):
    """
    Синхронный роут страницы статистики в FastAPI.
    Ничего не блокирует, так как работает в отдельном потоке.
    """
    top_searches = get_top_5_searches()
    last_searches = get_last_5_searches()

    return templates.TemplateResponse(
        request,               # Идет самым первым аргументом
        "stats.html",          # Имя шаблона — вторым аргументом
        {                      # Словарь контекста — третьим аргументом
            "request": request,
            "top_searches": top_searches,
            "last_searches": last_searches
        }
    )


# Синхронный роут отдачи иконки фавикона
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """
    Возвращает реальный файл фавикона для вкладки браузера.
    """
    favicon_path = os.path.join(BASE_DIR, "static", "images", "favicon.svg")

    # Проверяем, существует ли файл физически на диске
    if os.path.exists(favicon_path):
        # Отдаем файл с указанием правильного типа данных для SVG-вектора
        return FileResponse(favicon_path, media_type="image/svg+xml")

    return Response(status_code=204)  # Дефолтный фолбек, если файл потерялся



if __name__ == "__main__":
    import uvicorn

    # Запуск сервера Uvicorn. Режим reload=True автоматически подхватывает изменения кода
    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)
