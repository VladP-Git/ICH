import mysql.connector
from local_settings import dbconfig


def get_movies(search_word=None, category=None, year=None, limit=10, offset=0):
    """
    Функция поиска фильмов в базе данных "Sakila" по заданным фильтрам.
    Реализует безопасную параметризованную фильтрацию.
    """
    # Инициализируем соединение с использованием параметров из local_settings
    connection = mysql.connector.connect(**dbconfig)

    # dictionary=True позволяет получать результаты в виде {'имя_колонки': значение}
    cursor = connection.cursor(dictionary=True)

    # Базовый SQL-запрос
    query = """
            SELECT f.film_id, \
                   f.title, \
                   f.description, \
                   f.release_year, \
                   f.length, \
                   c.name AS category_name
            FROM film f
                     JOIN film_category fc ON f.film_id = fc.film_id
                     JOIN category c ON fc.category_id = c.category_id
            WHERE 1 = 1 \
            """

    # Список параметров для безопасной передачи в SQL-запрос (защита от SQL-инъекций)
    params = []

    # Динамически добавляем условия в зависимости от того, что ввел пользователь
    if search_word:
        query += " AND (f.title LIKE %s OR f.description LIKE %s)"
        search_param = f"%{search_word}%"
        params.extend([search_param, search_param])

    if category:
        query += " AND c.name = %s"
        params.append(category)

    if year:
        query += " AND f.release_year = %s"
        params.append(int(year))

    # Сортировка и пагинация
    query += " ORDER BY f.title ASC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    try:
        cursor.execute(query, params)
        movies = cursor.fetchall()  # Получаем список словарей с фильмами
        return movies
    except mysql.connector.Error as err:
        print(f"Ошибка выполнения SQL-запроса: {err}")
        return []
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
