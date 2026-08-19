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

# Инициализируем роутер
main_router = APIRouter()

# --- УНИВЕРСАЛЬНЫЙ МОСТ СИНТАКСИСА URL_FOR ---
@pass_context
def fastapi_url_for(context: dict, name: str, **path_params):
    request = context["request"]
    if name == 'static' and 'filename' in path_params:
        path_params['path'] = path_params.pop('filename')
        return request.url_for(name, **path_params)

    if name == 'index_page':
        url = request.url_for('index_page')
        clean_params = {k: v for k, v in path_params.items() if v is not None and v != ''}
        if 'view_mode' not in clean_params and 'view_mode' in request.query_params:
            clean_params['view_mode'] = request.query_params['view_mode']
        if clean_params:
            url = f"{url}?{urlencode(clean_params)}"

        # Принудительно приклеиваем якорь в конец URL-адреса, чтобы страница не улетала вверх
        return f"{url}#movie-section"

    return request.url_for(name, **path_params)

# Регистрируем мост в окружении шаблонов
templates.env.globals['url_for'] = fastapi_url_for
# ---------------------------------------------

@main_router.get("/", response_class=HTMLResponse, name="index_page")
def index_page(request: Request):
    context = funcs.prepare_index_context(request)
    context["request"] = request
    return templates.TemplateResponse(request, "index.html", context)


@main_router.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request):
    context = funcs.prepare_stats_context()
    context["request"] = request
    return templates.TemplateResponse(request, "stats.html", context)


@main_router.get("/favicon.ico", include_in_schema=False)
def favicon():
    favicon_path = os.path.join(BASE_DIR, "static", "images", "favicon.svg")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/svg+xml")
    return Response(status_code=204)


def global_exception_handler(app):
    """
    Функция-регистратор. Принимает экземпляр FastAPI
    и регистрирует в его реестре обработку ошибок.
    """

    # Внутренняя изолированная функция, которая фактически обрабатывает ошибку
    def core_handler(request: Request, exc: Exception) -> HTMLResponse:
        return funcs.handle_global_exception(request, exc)

    # Принудительно регистрируем внутренний обработчик в приложении app для класса Exception
    app.add_exception_handler(Exception, core_handler)