"""Модуль интеграции с реляционной СУБД MySQL (База данных Sakila).

Реализует управление синхронным пулом соединений (Connection Pool),
динамическое построение параметризованных SQL-запросов для фильтрации и пагинации,
а также защиту от SQL-инъекций и агрегацию связей 'многие ко многим' через GROUP_CONCAT.
"""

import mysql.connector
from mysql.connector import pooling
from local_settings import dbconfig

# ─── ПРЕЗЕНТАЦИЯ: ИНИЦИАЛИЗАЦИЯ ПУЛА СОЕДИНЕНИЙ (CONNECTION POOL) ───────────
try:
    # ПОЧЕМУ ТАК: Использование пула на 10 подключений предотвращает перегрузку
    # удаленной СУБД MySQL и ускоряет отклик за счет переиспользования открытых коннектов.
    _pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="sakila_pool",
        pool_size=10,
        host=dbconfig['host'],
        port=dbconfig.get('port', 3306),
        user=dbconfig['user'],
        password=dbconfig['password'],
        database=dbconfig['database'],
        charset='utf8mb4',
        use_unicode=True
    )
    print("[MySQL Синхронный] Пул соединений успешно инициализирован.")
except Exception as e:
    print(f"[MySQL Синхронный] КРИТИЧЕСКАЯ ОШИБКА инициализации пула: {e}")
    _pool = None


# ─── ПРЕЗЕНТАЦИЯ: МЕТОДЫ ИЗВЛЕЧЕНИЯ СПРАВОЧНЫХ ДАННЫХ ────────────────────────

def get_all_categories() -> list[str]:
    """Синхронно извлекает полный отсортированный список всех жанров из базы данных.

    Используется бэкендом для динамического наполнения выпадающего списка (Select)
    в поисковой форме на главной странице.

    Returns:
        list[str]: Список названий категорий (жанров) по алфавиту.
    """
    # 🎯: Запрашиваем коннект из пула. Конструкция try/finally гарантирует возврат.
    conn = _pool.get_connection()
    cursor = conn.cursor()
    try:
        query = "SELECT name FROM category ORDER BY name ASC;"
        cursor.execute(query)
        result = cursor.fetchall()
        # ПОЧЕМУ ТАК: Распаковываем кортежи строк в плоский одномерный список строк Python
        return [row[0] for row in result]
    except Exception as err:
        print(f"Ошибка при получении категорий: {err}")
        return []
    finally:
        cursor.close()
        conn.close()  # Соединение не закрывается физически, а возвращается в пул


def get_year_bounds() -> tuple[int, int]:
    """Синхронно вычисляет минимальный и максимальный года выпуска фильмов в таблице.

    Позволяет динамически формировать плейсхолдеры и правила валидации для полей
    "Год от" и "Год до" на фронтенде на основе реальных данных СУБД.

    Returns:
        tuple[int, int]: Кортеж, содержащий (минимальный_год, максимальный_год).
    """
    conn = _pool.get_connection()
    # ПОЧЕМУ ТАК: dictionary=True возвращает результат в виде ассоциативного словаря (DictCursor)
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT MIN(release_year) as min_y, MAX(release_year) as max_y FROM film;"
        cursor.execute(query)
        res = cursor.fetchone()
        if res and res['min_y'] and res['max_y']:
            return int(res['min_y']), int(res['max_y'])
        return 1890, 2026
    except Exception as err:
        print(f"Ошибка при получении границ годов: {err}")
        return 1890, 2026
    finally:
        cursor.close()
        conn.close()

# ─── ПРЕЗЕНТАЦИЯ: ОСНОВНОЙ КНОПОЧНЫЙ ПОИСК И ПАГИНАЦИЯ ───────────────────────

def get_movies(
    search_word: str | None = None,
    category: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 10,
    offset: int = 0
) -> tuple[list[dict], int]:
    """Синхронная функция параметризованного поиска фильмов с поддержкой пагинации.

    Динамически выстраивает безопасное тело SQL-запроса, агрегирует связи «многие
    ко многим» между фильмами и жанрами, а также вычисляет сквозное общее число
    найденных записей (COUNT) для корректной работы постраничного вывода.

    Args:
        search_word (str | None): Текст для поиска по названию или описанию.
        category (str | None): Фильтр по конкретному названию жанра.
        year_from (int | None): Нижняя временная граница релиза картины.
        year_to (int | None): Верхняя временная граница релиза картины.
        limit (int): Размер страницы (количество карточек в выборке).
        offset (int): Смещение (число пропускаемых строк).

    Returns:
        tuple[list[dict], int]: Кортеж, где первый элемент — список фильмов-словарей,
                                второй элемент — общее количество совпадений в базе.
    """
    conn = _pool.get_connection()
    cursor = conn.cursor(dictionary=True)

    # ПОЧЕМУ ТАК: Пассивный базовый фильтр 'WHERE 1=1' упрощает динамическое добавление AND-условий
    base_where = " WHERE 1=1"
    params_where = []

    # 🎯: Используем плейсхолдеры %s и кортежи параметров.
    # Это на 100% блокирует любые попытки проведения SQL-инъекций (SQL Injection).
    if search_word:
        base_where += " AND (f.title LIKE %s OR f.description LIKE %s)"
        search_param = f"%{search_word}%"
        params_where.extend([search_param, search_param])

    if year_from:
        base_where += " AND f.release_year >= %s"
        params_where.append(int(year_from))

    if year_to:
        base_where += " AND f.release_year <= %s"
        params_where.append(int(year_to))

    # 1️⃣ ПОДГОТОВКА СЧЕТЧИКА (PAGINATION TOTAL COUNT)
    count_params = params_where.copy()
    category_condition = ""
    if category:
        category_condition = " AND c.name = %s"
        count_params.append(category)

    # ПОЧЕМУ ТАК: COUNT(DISTINCT ...) позволяет узнать точное число уникальных фильмов
    # с учетом фильтра по жанру, отсекая размножение строк от JOIN-связей.
    count_query = f"""
        SELECT COUNT(DISTINCT f.film_id) as total 
        FROM film f
        JOIN film_category fc ON f.film_id = fc.film_id
        JOIN category c ON fc.category_id = c.category_id
        {base_where} {category_condition}
    """

    # 2️⃣ ПОДГОТОВКА ГЛАВНОГО ЗАПРОСА ВЫДАЧИ ФИЛЬМОВ
    having_clause = ""
    params_having = []
    if category:
        # ПОЧЕМУ ТАК: FIND_IN_SET внутри HAVING ищет выбранный жанр в строке GROUP_CONCAT.
        # Это позволяет отфильтровать фильмы по одному жанру, но выгрузить на фронтенд ВСЕ жанры фильма.
        having_clause = " HAVING FIND_IN_SET(%s, GROUP_CONCAT(c.name)) > 0"
        params_having.append(category)

    movies_query = f"""
        SELECT 
            f.film_id, f.title, f.description, f.release_year, f.length, 
            GROUP_CONCAT(c.name ORDER BY c.name SEPARATOR ', ') AS category_name, 
            f.rating, f.special_features, f.rental_duration, f.rental_rate
        FROM film f
        JOIN film_category fc ON f.film_id = fc.film_id
        JOIN category c ON fc.category_id = c.category_id
        {base_where}
        GROUP BY f.film_id
        {having_clause}
        ORDER BY f.title ASC 
        LIMIT %s OFFSET %s
    """

    try:
        # Шаг 1: Вычисляем общий объем выборки для пагинатора
        cursor.execute(count_query, count_params)
        count_res = cursor.fetchone()
        total_count = count_res['total'] if count_res else 0

        # Шаг 2: Выполняем точечный срез данных для текущей страницы сайта
        movies_params = params_where + params_having + [limit, offset]
        cursor.execute(movies_query, movies_params)
        movies = cursor.fetchall()

        return movies, total_count
    except Exception as err:
        print(f"Ошибка SQL-запроса при группировке жанров: {err}")
        return [], 0
    finally:
        cursor.close()
        conn.close()


# ─── ПРЕЗЕНТАЦИЯ: ЛОКАЛЬНЫЙ ТЕСТ МОДУЛЯ (SMOKE TEST) ─────────────────────────
if __name__ == "__main__":
    from tabulate import tabulate

    print("Запуск локального теста синхронного mysql_connector.py...")

    cats = get_all_categories()
    print(f"Жанры в базе ({len(cats)}): {cats[:3]}...")

    movies_list, total_found = get_movies(search_word="dinosaur", year_from=2005)
    print(f"\n[Успех] Найдено фильмов: {total_found}")
    if movies_list:
        print(tabulate(movies_list[:2], headers="keys", tablefmt="grid"))
