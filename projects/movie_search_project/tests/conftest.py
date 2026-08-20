"""Конфигурационный модуль тестирования фреймворка pytest.

Автоматически рассчитывает абсолютные пути к корневым директориям проекта
и динамически внедряет каталог backend в системный путь поиска модулей sys.path.
Это гарантирует корректную изоляцию и бесперебойный сквозной импорт
тестируемых компонентов внутри QA-движка.
"""

import os
import sys

# Определяем абсолютный путь к корню проекта (movie_search_project/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Добавляем папку backend в пути поиска модулей Python
backend_path = os.path.join(BASE_DIR, "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
