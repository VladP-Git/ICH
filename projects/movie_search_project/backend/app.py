import time
import math
import os
from flask import Flask, render_template, request
# Импортируем готовые модули.
# Так как app.py лежит в папке backend/, импорты делаются напрямую
from mysql_connector import get_movies, get_all_categories, get_year_bounds
from log_writer import write_search_log
from log_stats import get_top_5_searches, get_last_5_searches
from logger_config import app_logger

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
    # Записываем отладочную информацию в файл лога
    app_logger.debug(f"Получен GET-запрос к главной странице. Параметры URL: {dict(request.args)}")

    # Получаем параметры из поисковой строки URL (GET-запрос)
    search_word = request.args.get('search_word', '').strip()
    category = request.args.get('category', '').strip()

    # 2. Получаем параметры диапазона лет
    year_from = request.args.get('year_from', '').strip()
    year_to = request.args.get('year_to', '').strip()

    # Проверяем, поступил ли маркер отправки из HTML - пользователь нажал кнопку "Искать" с пустыми фильтрами
    form_submitted = request.args.get('search_submitted', '') == '1'

    # ПАГИНАЦИЯ: Получаем текущую страницу из URL (например, ?page=2)
    page = request.args.get('page', '1')
    page = int(page) if page.isdigit() else 1
    limit = 10
    offset = (page - 1) * limit

    # Подготавливаем параметры для SQL-запроса,
    # преобразовываем пустые строки в None для корректной работы SQL-фильтров
    s_word = search_word if search_word else None
    cat = category if category else None
    yr_from = int(year_from) if year_from and year_from.isdigit() else None
    yr_to = int(year_to) if year_to and year_to.isdigit() else None

    # Динамически вытягиваем из MySQL жанры и границы годов для подсказок на форме ввода
    categories = get_all_categories()
    min_db_year, max_db_year = get_year_bounds()

    # --- ЗАМЕР ВРЕМЕНИ ДЛЯ MYSQL ---
    start_mysql = time.time()

    # ЕСЛИ ПОЛЬЗОВАТЕЛЬ НАЖАЛ КНОПКУ "ИСКАТЬ"
    if form_submitted:
        is_searched = True
        # База данных сама поймет, что если cat=None (Все жанры), нужно искать по всей базе!
        # Передаем yr_from и yr_to в get_movies
        movies, total_movies = get_movies(
            search_word=s_word, category=cat,
            year_from=yr_from, year_to=yr_to,
            limit=limit, offset=offset
        )

        # Логируем только первую страницу нового запроса
        if page == 1:
            start_mongo_write = time.time()
            # Для MongoDB лога объединяем диапазон лет в понятную структуру параметров
            # чтобы в логах было явно видно, что искали именно диапазон
            # Внутри backend/app.py, для обобщения статистики, переводим в нижний регистр перед отправкой в MongoDB:
            write_search_log(search_word=s_word.lower() if s_word else None, category=cat,
                             year=f"{year_from}-{year_to}" if (year_from or year_to) else None,
                             results_count=total_movies)

            # --- ЗАМЕР ВРЕМЕНИ ДЛЯ MONGODB (ЗАПИСЬ) ---
            print(f"[⏱️ TIME] MongoDB запись заняла: {time.time() - start_mongo_write:.2f} сек.")
            app_logger.info(
                f"Выполнен новый поиск: текст='{s_word}', жанр='{cat}', диапазон={yr_from}-{yr_to}. Найдено: {total_movies}")

    # ЕСЛИ ПОЛЬЗОВАТЕЛЬ ТОЛЬКО ЧТО ЗАШЕЛ НА САЙТ (ПЕРВЫЙ КЛИК)
    else:
        print("[MongoDB] Пропуск логирования: переход по страницам существующего запроса.")
        is_searched = False
        # Если поиска не было, отображаются 10 базовых фильмов категории "New" на стартовом экране без логирования.
        movies, total_movies = get_movies(category="New", limit=limit, offset=offset)
        app_logger.debug("Стартовый экран: загружена категория 'New' (Новинки проката)")
        print(type(movies[0]["special_features"]))
        print(movies[0]["special_features"])

    print(f"[⏱️ TIME] Общая работа MySQL заняла: {time.time() - start_mysql:.2f} \n")
    # Высчитываем общее количество страниц (например, 85 фильмов / 10 = 8.5 -> 9 страниц)

    total_pages = math.ceil(total_movies / limit) if total_movies > 0 else 1


    # print(type(movies[0]["special_features"]))
    # print(movies[0]["special_features"])
    # Передаем данные в HTML-шаблон Jinja2
    return render_template(
        'index.html',
        movies=movies,
        search_word=search_word,
        category=category,
        year_from=year_from,
        year_to=year_to,
        min_db_year=min_db_year,
        max_db_year=max_db_year,
        is_searched=is_searched,
        categories=categories,  # Передаем список жанров
        current_page=page,  # Передаем текущую страницу
        total_pages=total_pages,  # Передаем общее число страниц
        total_movies=total_movies  # Передаем общее число найденных фильмов
    )
    # Pfukeirf
    # return "INDEX WORKS"

@app.route('/stats')
def stats_page():
    """
    Роут страницы статистики. Подтягивает Топ-5 из MongoDB.
    """
    # --- ЗАМЕР ВРЕМЕНИ ДЛЯ MONGODB (СТАТИСТИКА) ---
    start_mongo_stats = time.time()
    top_searches = get_top_5_searches()
    last_searches = get_last_5_searches()
    print(f"[⏱️ TIME] MongoDB агрегация заняла: {time.time() - start_mongo_stats:.2f} сек. \n")

    return render_template(
        'stats.html',
        top_searches=top_searches,
        last_searches=last_searches
    )


if __name__ == '__main__':
    # Запуск локального сервера в режиме отладки (debug=True автоматически перезагружает сервер при изменении кода)
    app.run(debug=True, port=5000)
