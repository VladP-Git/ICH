import time
import math
import os
from flask import Flask, render_template, request
# Импортируем готовые модули.
# Так как app.py лежит в папке backend/, импорты делаются напрямую
from mysql_connector import get_movies, get_all_categories
from log_writer import write_search_log
from log_stats import get_top_5_searches

# Инициализируем Flask.
# Указываем правильные пути к папкам с фронтендом, так как они лежат на уровень выше папки backend
# __file__ указывает на текущий файл (app.py).
# os.path.dirname(__file__) находит папку backend/.
# С помощью join мы абсолютно точно поднимаемся на уровень выше и заходим в нужную папку.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)


@app.route('/')
def index_page():
    """
    Роут главной страницы. Обрабатывает поисковые запросы и фильтры.
    """
    # Получаем параметры из поисковой строки URL (GET-запрос)
    search_word = request.args.get('search_word', '').strip()
    category = request.args.get('category', '').strip()
    year = request.args.get('year', '').strip()

    # ПАГИНАЦИЯ: Получаем текущую страницу из URL (например, ?page=2)
    page = request.args.get('page', '1')
    page = int(page) if page.isdigit() else 1

    limit = 10
    offset = (page - 1) * limit

    # Преобразуем пустые строки в None для корректной работы SQL-фильтров
    s_word = search_word if search_word else None
    cat = category if category else None
    yr = int(year) if year and year.isdigit() else None

    # Всегда подтягиваем актуальные жанры из базы для выпадающего списка
    categories = get_all_categories()

    # --- ЗАМЕР ВРЕМЕНИ ДЛЯ MYSQL ---
    start_mysql = time.time()
    # Если пользователь нажал кнопку "Искать" (хотя бы один фильтр передан)
    if s_word or cat or yr:
        is_searched = True
        # 1. Получаем фильмы из MySQL
        movies, total_movies = get_movies(search_word=s_word, category=cat, year=yr, limit=limit, offset=offset)
        # --- ЗАМЕР ВРЕМЕНИ ДЛЯ MONGODB (ЗАПИСЬ) ---
        start_mongo_write = time.time()
        # 2. Логируем поисковый запрос в MongoDB
        if page == 1:
            write_search_log(search_word=s_word, category=cat, year=yr, results_count=total_movies)
            print(f"[⏱️ TIME] MongoDB запись заняла: {time.time() - start_mongo_write:.2f} сек.")
        else:
            print("[MongoDB] Пропуск логирования: переход по страницам существующего запроса.")

    else:
        is_searched = False
        # Если поиска не было, просто покажем 10 базовых фильмов без логирования.
        movies, total_movies = get_movies(limit=limit, offset=offset)

    print(f"[⏱️ TIME] Общая работа MySQL заняла: {time.time() - start_mysql:.2f} \n")

    # Высчитываем общее количество страниц (например, 85 фильмов / 10 = 8.5 -> 9 страниц)
    total_pages = math.ceil(total_movies / limit) if total_movies > 0 else 1

    # Передаем данные в HTML-шаблон Jinja2
    return render_template(
        'index.html',
        movies=movies,
        search_word=search_word,
        category=category,
        year=year,
        is_searched=is_searched,
        categories=categories,  # Передаем список жанров
        current_page=page,  # Передаем текущую страницу
        total_pages=total_pages,  # Передаем общее число страниц
        total_movies=total_movies  # Передаем общее число найденных фильмов
    )


@app.route('/stats')
def stats_page():
    """
    Роут страницы статистики. Подтягивает Топ-5 из MongoDB.
    """
    # --- ЗАМЕР ВРЕМЕНИ ДЛЯ MONGODB (СТАТИСТИКА) ---
    start_mongo_stats = time.time()
    top_searches = get_top_5_searches()
    print(f"[⏱️ TIME] MongoDB агрегация заняла: {time.time() - start_mongo_stats:.2f} сек. \n")

    return render_template('stats.html', top_searches=top_searches)


if __name__ == '__main__':
    # Запуск локального сервера в режиме отладки (debug=True автоматически перезагружает сервер при изменении кода)
    app.run(debug=True, port=5000)
