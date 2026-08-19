import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routes import main_router, global_exception_handler # Импортируем роутер

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Инициализируем основное приложение FastAPI
app = FastAPI(title="Sakila Cinema — Модульная Архитектура")

# Глобальный обработчик критических ошибок
global_exception_handler(app)

# Подключаем статические ресурсы и маршруты страниц
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Подключаем изолированный роутер со всеми эндпоинтами проекта
app.include_router(main_router)

if __name__ == "__main__":
    # Запуск приложения на стандартном порту 5000 с автоперезагрузкой
    uvicorn.run("main:app", host="127.0.0.1", port=5000, reload=True)
