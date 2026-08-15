import mysql.connector
from mysql.connector import pooling
from local_settings import dbconfig

# Инициализируем стандартный синхронный пул соединений MySQL
try:
    _pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="sakila_pool",
        pool_size=10,  # Резервируем до 10 одновременных подключений к БД
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


def get_all_categories():
    """Синхронно получает список жанров из Sakila."""
    conn = _pool.get_connection()
    cursor = conn.cursor()
    try:
        query = "SELECT name FROM category ORDER BY name ASC;"
        cursor.execute(query)
        result = cursor.fetchall()
        # mysql-connector возвращает кортежи, извлекаем первый элемент
        return [row[0] for row in result]
    except Exception as err:
        print(f"Ошибка при получении категорий: {err}")
        return []
    finally:
        cursor.close()
        conn.close()  # Возвращаем соединение обратно в пул


def get_year_bounds():
    """Синхронно возвращает минимальный и максимальный год выпуска фильмов."""
    conn = _pool.get_connection()
    # dictionary=True заменяет DictCursor и возвращает строки в виде словарей
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT MIN(release_year) as min_y, MAX(release_year) as max_y FROM film;"
        cursor.execute(query)
        res = cursor.fetchone()
        if res and res['min_y'] and res['max_y']:
            return int(res['min_y']), int(res['max_y'])
        return 1900, 2026
    except Exception as err:
        print(f"Ошибка при получении границ годов: {err}")
        return 1900, 2026
    finally:
        cursor.close()
        conn.close()


def get_movies(search_word=None, category=None, year_from=None, year_to=None, limit=10, offset=0):
    """
    Синхронная функция поиска фильмов.
    Группируем все жанры фильма, даже при фильтрации по конкретному жанру.
    """
    conn = _pool.get_connection()
    cursor = conn.cursor(dictionary=True)

    # В WHERE оставляем только общие фильтры (текст и годы)
    base_where = " WHERE 1=1"
    params_where = []

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

    # 1. Запрос подсчета количества (COUNT) с учетом выбранного жанра
    count_params = params_where.copy()
    category_condition = ""
    if category:
        category_condition = " AND c.name = %s"
        count_params.append(category)

    count_query = f"""
        SELECT COUNT(DISTINCT f.film_id) as total 
        FROM film f
        JOIN film_category fc ON f.film_id = fc.film_id
        JOIN category c ON fc.category_id = c.category_id
        {base_where} {category_condition}
    """

    # 2. Главный запрос: фильтруем сгруппированные жанры через HAVING
    having_clause = ""
    params_having = []
    if category:
        # Ищем выбранный жанр внутри строки всех жанров фильма
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
        # 1. Считаем общее количество подходящих под фильтр фильмов - total
        cursor.execute(count_query, count_params)
        count_res = cursor.fetchone()
        total_count = count_res['total'] if count_res else 0

        # 2. Собираем параметры для основного запроса
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


# Изолированный встроенный тест для мгновенной проверки модуля
if __name__ == "__main__":
    from tabulate import tabulate

    print("Запуск локального теста синхронного mysql_connector.py...")

    # Тестируем получение категорий
    cats = get_all_categories()
    print(f"Жанры в базе ({len(cats)}): {cats[:3]}...")

    # Тестируем поиск фильма
    movies_list, total_found = get_movies(search_word="dinosaur", year_from=2005)
    print(f"\n[Успех] Найдено фильмов: {total_found}")
    if movies_list:
        print(tabulate(movies_list[:2], headers="keys", tablefmt="grid"))
