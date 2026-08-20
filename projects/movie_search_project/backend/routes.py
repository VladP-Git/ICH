"""Модуль маршрутизации и конфигурации URL-адресов веб-приложения Sakila Cinema.

Отвечает за перехват HTTP-запросов, интеграцию шаблонизатора Jinja2 с FastAPI,
динамическое сохранение GET-параметров поиска и регистрацию глобального обработчика ошибок.
"""

import os
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from urllib.parse import urlencode

import funcs

# Определяем базовую директорию для поиска шаблонов и статики
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Инициализируем изолированный роутер приложения
main_router = APIRouter()


# ─── ПРЕЗЕНТАЦИЯ: АДАПТЕР URL ДЛЯ JINJA2 ─────────────────────────────────────
@pass_context
def fastapi_url_for(context: dict, name: str, **path_params) -> str:
    """Универсальный мост синтаксиса url_for для интеграции FastAPI и Jinja2.

    Корректирует стандартное поведение FastAPI, позволяя динамически собирать
    GET-параметры (Query Params) фильтрации и пагинации в URL, а также
    автоматически приклеивает хэш-якорь к поисковой выдаче.

    Args:
        context (dict): Контекст шаблонизатора Jinja2, содержащий текущий запрос.
        name (str): Имя эндпоинта или статического маршрута.
        **path_params: Произвольные параметры, передаваемые в URL.

    Returns:
        str: Полный сформированный URL-адрес для вставки в HTML.
    """
    request = context["request"]

    # ПОЧЕМУ ТАК: Переопределяем логику для статических ресурсов (картинки, стили)
    if name == 'static' and 'filename' in path_params:
        path_params['path'] = path_params.pop('filename')
        return request.url_for(name, **path_params)

    # ПОЧЕМУ ТАК: Главная страница требует сохранения фильтров при перелистывании
    if name == 'index_page':
        url = request.url_for('index_page')

        # Очищаем параметры от пустых значений и None
        clean_params = {k: v for k, v in path_params.items() if v is not None and v != ''}

        # Удерживаем текущий формат сетки (view_mode), если он не был передан явно
        if 'view_mode' not in clean_params and 'view_mode' in request.query_params:
            clean_params['view_mode'] = request.query_params['view_mode']

        if clean_params:
            url = f"{url}?{urlencode(clean_params)}"

        # 🎯 ТОЧКА ФОКУСА: Принудительный якорь для предотвращения прыжков экрана
        return f"{url}#movie-section"

    return request.url_for(name, **path_params)


# Регистрация разработанного адаптера в глобальном окружении шаблонов
templates.env.globals['url_for'] = fastapi_url_for


# ─── ПРЕЗЕНТАЦИЯ: ЭНДПОИНТЫ СТРАНИЦ САЙТА ────────────────────────────────────

@main_router.get("/", response_class=HTMLResponse, name="index_page")
def index_page(request: Request) -> HTMLResponse:
    """Эндпоинт главной страницы фильмотеки (Поиск, фильтры, новинки).

    Args:
        request (Request): Объект входящего HTTP-запроса FastAPI.

    Returns:
        HTMLResponse: Скомпилированная Jinja2-страница index.html с контекстом.
    """
    # 🎯: Вся бизнес-логика подготовки данных вынесена в funcs.py (Slim Controller)
    context = funcs.prepare_index_context(request)
    context["request"] = request
    return templates.TemplateResponse(request, "index.html", context)


@main_router.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request) -> HTMLResponse:
    """Эндпоинт аналитической страницы (Топ-5 и последние запросы NoSQL MongoDB).

    Args:
        request (Request): Объект входящего HTTP-запроса.

    Returns:
        HTMLResponse: Скомпилированная Jinja2-страница stats.html с данными аналитики.
    """
    context = funcs.prepare_stats_context()
    context["request"] = request
    return templates.TemplateResponse(request, "stats.html", context)


@main_router.get("/favicon.ico", include_in_schema=False, response_model=None)
def favicon() -> Response | FileResponse:
    """Эндпоинт обработки системного запроса на иконку сайта (Favicon).

    Returns:
        FileResponse: Файл векторной иконки (SVG), если он существует.
        Response: Пустой ответ со статусом 204 (No Content) во избежание ошибок в консоли.
    """
    favicon_path = os.path.join(BASE_DIR, "static", "images", "favicon.svg")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/svg+xml")
    return Response(status_code=204)


# ─── ПРЕЗЕНТАЦИЯ: ЦЕНТРАЛИЗОВАННАЯ ОТКАЗОУСТОЙЧИВОСТЬ ────────────────────────

def global_exception_handler(app):
    """Глобальный регистратор перехвата исключений для приложения FastAPI.

    Реализует паттерн централизованной обработки ошибок. Предотвращает
    падение приложения и показ "белого экрана" пользователю при критических сбоях.

    Args:
        app: Экземпляр основного класса FastAPI из main.py.
    """

    def core_handler(request: Request, exc: Exception) -> HTMLResponse:
        """Изолированное ядро обработки, перенаправляющее ошибку в модуль бизнес-логики."""
        # ПОЧЕМУ ТАК: Логика формирования красивой страницы ошибки инкапсулирована в funcs.py
        return funcs.handle_global_exception(request, exc)

    # Принудительно связываем базовый класс Exception с нашим обработчиком core_handler
    app.add_exception_handler(Exception, core_handler)
