"""Точка входа и инициализации веб-сервера приложения Sakila Cinema.

Отвечает за сборку компонентов модульной архитектуры: инициализацию FastAPI,
подключение глобального перехватчика исключений, монтирование директории
статических ресурсов (CSS/JS) и запуск ASGI-сервера Uvicorn.
"""

import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Импортируем изолированный роутер и глобальный обработчик ошибок
from routes import main_router, global_exception_handler

# Определяем абсолютный путь к корню проекта (movie_search_project/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Инициализируем основное приложение FastAPI
app = FastAPI(title="Sakila Cinema — Модульная Архитектура")

# ─── ПРЕЗЕНТАЦИЯ: СБОРКА АРХИТЕКТУРНЫХ СЛОЕВ ────────────────────────────────
# ПОЧЕМУ ТАК: Централизованный перехватчик регистрируется до подключения маршрутов.
# Это гарантирует, что любая ошибка внутри роутера будет безопасно поймана.
global_exception_handler(app)

# Подключаем локальные статические ресурсы (Bootstrap, стили, иконки)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ПОЧЕМУ ТАК:include_router изолирует маршруты в routes.py, сохраняя main.py чистым
app.include_router(main_router)


if __name__ == "__main__":
    # Запуск веб-сервера на порту 5000 с включенным Live Reload.
    # При любых изменениях в Python-коде или HTML-шаблонах сервер перезагружается сам.
    uvicorn.run("main:app", host="127.0.0.1", port=5000, reload=True)
