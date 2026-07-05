import mysql.connector
from local_settings import dbconfig


def get_all_categories():
    """
    Получает полный список названий категорий (жанров) из базы данных Sakila.
    """
    connection = mysql.connector.connect(**dbconfig)
    cursor = connection.cursor()  # Тут dictionary=True не обязателен, нам нужен простой список

    query = "SELECT name FROM category ORDER BY name ASC;"

    try:
        cursor.execute(query)
        # fetchall() вернет список кортежей [('Action',), ('Animation',)...]
        # Превращаем его в плоский список строк ['Action', 'Animation'...] с помощью list comprehension
        categories = [row[0] for row in cursor.fetchall()]
        return categories
    except mysql.connector.Error as err:
        print(f"Ошибка при получении категорий: {err}")
        return []
    finally:
        cursor.close()
        connection.close()


def get_movies(search_word=None, category=None, year=None, limit=10, offset=0):
    """
    Функция поиска фильмов в Sakila DB.
    Возвращает КОРТЕЖ: (список_фильмов, общее_количество_найденных_фильмов)
    """
    # Инициализируем соединение с использованием параметров из local_settings
    connection = mysql.connector.connect(**dbconfig)

    # dictionary=True позволяет получать результаты в виде {'имя_колонки': значение}
    cursor = connection.cursor(dictionary=True)

    # Базовые части запросов
    base_where = " WHERE 1=1"

    # Список параметров для безопасной передачи в SQL-запрос (защита от SQL-инъекций)
    params = []

    # Динамически добавляем условия в зависимости от того, что ввел пользователь
    if search_word:
        base_where += " AND (f.title LIKE %s OR f.description LIKE %s)"
        search_param = f"%{search_word}%"
        params.extend([search_param, search_param])

    if category:
        base_where += " AND c.name = %s"
        params.append(category)

    if year:
        base_where += " AND f.release_year = %s"
        params.append(int(year))

    # --- ЗАПРОС 1: Получаем общее количество (без LIMIT) ---
    # считаем только уникальные ID фильмов:
    count_query = f"""
        SELECT COUNT(DISTINCT f.film_id) as total 
        FROM film f
        JOIN film_category fc ON f.film_id = fc.film_id
        JOIN category c ON fc.category_id = c.category_id
        {base_where}
    """

    # --- ЗАПРОС 2: Получаем сами 10 фильмов ---
    movies_query = f"""
        SELECT DISTINCT f.film_id, f.title, f.description, f.release_year, f.length, c.name AS category_name
        FROM film f
        JOIN film_category fc ON f.film_id = fc.film_id
        JOIN category c ON fc.category_id = c.category_id
        {base_where}
        ORDER BY f.title ASC 
        LIMIT %s OFFSET %s
    """

    try:
        # Сначала считаем общее количество
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()['total']

        # Теперь берем порцию фильмов (добавляем limit и offset к копии параметров)
        movies_params = params + [limit, offset]
        cursor.execute(movies_query, movies_params)
        movies = cursor.fetchall()

        return movies, total_count  # Возвращаем кортеж из двух элементов

    except mysql.connector.Error as err:
        print(f"Ошибка выполнения SQL-запроса: {err}")
        return [], 0
    finally:
        cursor.close()
        connection.close()


# Блок для локального тестирования модуля прямо в консоли
if __name__ == "__main__":
    from tabulate import tabulate

    print("Тестирование подключения и поиска фильмов...")

    # Тестовый поиск слова 'dinosaur' за 2012 год
    test_results = get_movies(search_word="dinosaur", year=2012)

    if test_results:
        print(tabulate(test_results, headers="keys", tablefmt="grid"))
    else:
        print("Фильмы по заданным критериям не найдены.")
