import aiomysql
from typing import Optional
from local_settings import dbconfig

# Глобальная переменная для хранения пула соединений
_pool: Optional[aiomysql.Pool] = None


async def get_mysql_pool():
    """
    Инициализирует асинхронный пул соединений к MySQL с принудительным декодированием строк в UTF-8.
    Использует шаблон Singleton (одиночка), чтобы не создавать пул дважды.
    """
    global _pool
    if _pool is None:
        # aiomysql ожидает параметры в чуть другом формате,
        # поэтому явно распаковываем dbconfig
        # noinspection PyUnresolvedReferences
        _pool = await aiomysql.create_pool(
            host=dbconfig['host'],
            port=dbconfig.get('port', 3306),
            user=dbconfig['user'],
            password=dbconfig['password'],
            db=dbconfig['database'],
            minsize=2,  # Минимальное количество коннектов в пуле
            maxsize=10,  # Максимальное количество коннектов в пуле
            autocommit=True,
            charset='utf8mb4',
            use_unicode=True
        )
    return _pool


async def get_all_categories_async():
    """
    Асинхронно получает список жанров из базы данных Sakila.
    """
    pool = await get_mysql_pool()
    # Одалживаем одно свободное соединение из пула
    async with pool.acquire() as conn:
        # Открываем асинхронный курсор
        async with conn.cursor() as cursor:
            query = "SELECT name FROM category ORDER BY name ASC;"
            await cursor.execute(query)
            result = await cursor.fetchall()
            # Извлекаем чистые строки из списка кортежей
            return [row[0] for row in result]


async def get_year_bounds_async():
    """
    Асинхронно возвращает минимальный и максимальный год выпуска фильмов в базе.
    """
    pool = await get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:  # DictCursor возвращает словари
            query = "SELECT MIN(release_year) as min_y, MAX(release_year) as max_y FROM film;"
            await cursor.execute(query)
            res = await cursor.fetchone()
            if res and res['min_y'] and res['max_y']:
                return int(res['min_y']), int(res['max_y'])
            return 1900, 2026


async def get_movies_async(search_word=None, category=None, year_from=None, year_to=None, limit=10, offset=0):
    """
    Полностью асинциированная функция поиска фильмов.
    Возвращает кортеж: (список_фильмов, общее_количество)
    """
    pool = await get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:

            base_where = " WHERE 1=1"
            params = []

            if search_word:
                base_where += " AND (f.title LIKE %s OR f.description LIKE %s)"
                search_param = f"%{search_word}%"
                params.extend([search_param, search_param])

            if category:
                base_where += " AND c.name = %s"
                params.append(category)

            if year_from:
                base_where += " AND f.release_year >= %s"
                params.append(int(year_from))

            if year_to:
                base_where += " AND f.release_year <= %s"
                params.append(int(year_to))

            count_query = f"""
                SELECT COUNT(DISTINCT f.film_id) as total 
                FROM film f
                JOIN film_category fc ON f.film_id = fc.film_id
                JOIN category c ON fc.category_id = c.category_id
                {base_where}
            """

            movies_query = f"""
                SELECT DISTINCT
                    f.film_id, f.title, f.description, f.release_year, f.length, 
                    c.name AS category_name, f.rating, f.special_features, f.rental_duration, f.rental_rate
                FROM film f
                JOIN film_category fc ON f.film_id = fc.film_id
                JOIN category c ON fc.category_id = c.category_id
                {base_where}
                ORDER BY f.title ASC 
                LIMIT %s OFFSET %s
            """

            try:
                # Асинхронно считаем количество
                await cursor.execute(count_query, params)
                count_res = await cursor.fetchone()
                total_count = count_res['total'] if count_res else 0

                # Асинхронно извлекаем порцию фильмов
                movies_params = params + [limit, offset]
                await cursor.execute(movies_query, movies_params)
                movies = await cursor.fetchall()

                return movies, total_count

            except Exception as err:
                print(f"Ошибка асинхронного SQL-запроса: {err}")
                return [], 0


# Локальный асинхронный тест модуля в консоли PyCharm
if __name__ == "__main__":
    import asyncio
    from tabulate import tabulate


    async def main_test():
        print("Тестирование асинхронного подключения aiomysql...")
        movies_list, total_found = await get_movies_async(search_word="dinosaur", year_from=2005)
        print(f"\n[Успех] Найдено асинхронно: {total_found}")
        if movies_list:
            print(tabulate(movies_list, headers="keys", tablefmt="grid"))

        # Закрываем пул после окончания теста, чтобы программа завершилась
        global _pool
        if _pool is not None:
            _pool.close()
            await _pool.wait_closed()


    asyncio.run(main_test())
