import time
import os
from flask import Flask, render_template, request
# Импортируем готовые модули.
# Так как app.py лежит в папке backend/, импорты делаются напрямую
from mysql_connector import get_movies
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

    # Преобразуем пустые строки в None для корректной работы SQL-фильтров
    s_word = search_word if search_word else None
    cat = category if category else None
    yr = int(year) if year and year.isdigit() else None

    # По умолчанию (если пользователь только зашел на сайт) выводим первые 10 фильмов
    # или первые 10 случайных фильмов?

    is_searched = False

    # --- ЗАМЕР ВРЕМЕНИ ДЛЯ MYSQL ---
    start_mysql = time.time()
    # Если пользователь нажал кнопку "Искать" (хотя бы один фильтр передан)
    if s_word or cat or yr:
        is_searched = True
        # 1. Получаем фильмы из MySQL
        movies = get_movies(search_word=s_word, category=cat, year=yr, limit=10, offset=0)

        # --- ЗАМЕР ВРЕМЕНИ ДЛЯ MONGODB (ЗАПИСЬ) ---
        start_mongo_write = time.time()
        # 2. Логируем поисковый запрос в MongoDB
        write_search_log(search_word=s_word, category=cat, year=yr, results_count=len(movies))
        print(f"[⏱️ TIME] MongoDB запись заняла: {time.time() - start_mongo_write:.2f} сек.")
    else:
        # Если поиска не было, просто покажем 10 базовых фильмов без логирования
        movies = get_movies(limit=10, offset=0)

    print(f"[⏱️ TIME] Общая работа MySQL заняла: {time.time() - start_mysql:.2f} \n")

    # Передаем данные в HTML-шаблон Jinja2
    return render_template(
        'index.html',
        movies=movies,
        search_word=search_word,
        category=category,
        year=year,
        is_searched=is_searched
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
