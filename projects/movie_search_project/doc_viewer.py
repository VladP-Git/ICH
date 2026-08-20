"""Универсальная утилита автоматической генерации и просмотра документации.

Сканирует каталоги проекта (backend, tests, корень), динамически импортирует
выбранный модуль и выводит его докстринги в терминал, отсекая сторонний код.
"""

import sys
import os
import importlib

def view_module_docs():
    if len(sys.argv) < 2:
        print("\n❌ Ошибка: Вы не указали имя модуля для проверки!")
        print("Использование: python doc_viewer.py <имя_модуля>")
        print("Пример: python doc_viewer.py funcs  ИЛИ  python doc_viewer.py test_funcs")
        return

    # Очищаем имя от расширения и путей, если пользователь ввел их вручную
    raw_input = sys.argv[1]
    module_name = os.path.basename(raw_input).replace(".py", "")

    # Определяем абсолютные пути к ключевым папкам проекта
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    backend_path = os.path.join(BASE_DIR, "backend")
    tests_path = os.path.join(BASE_DIR, "tests")

    # Добавляем все папки в пути поиска Python (sys.path)
    for path in [BASE_DIR, backend_path, tests_path]:
        if path not in sys.path:
            sys.path.insert(0, path)

    try:
        # Динамически импортируем указанный модуль из любой доступной папки
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        print(f"\n❌ Ошибка: Модуль '{module_name}' не найден ни в backend/, ни в tests/, ни в корне проекта!")
        return

    print("\n" + "=" * 60)
    print(f"📄 ДОКУМЕНТАЦИЯ МОДУЛЯ: {module_name.upper()}.PY")
    print("=" * 60)

    # Выводим описание модуля с гарантированным срезанием Windows BOM-маркеров
    doc = module.__doc__
    if doc:
        print(doc.encode('utf-8').decode('utf-8-sig').strip())
    else:
        print("Описание модуля отсутствует.")

    print("=" * 60)

    # Пробегаемся по объектам модуля
    found_functions = False
    for name, obj in module.__dict__.items():
        # Проверяем, что это функция/метод и она написана ИМЕННО в этом файле
        if callable(obj) and hasattr(obj, '__module__'):
            # Извлекаем чистое имя модуля, где объявлена функция (убирает префиксы папок)
            obj_module_base = obj.__module__.split('.')[-1]

            if obj_module_base == module_name and obj.__doc__:
                found_functions = True
                print(f"\n📌 ФУНКЦИЯ / ТЕСТ: {name}()")
                print("-" * 40)
                print(obj.__doc__.strip())
                print("-" * 40)

    if not found_functions:
        print("\nВнутри модуля не найдено собственных документированных функций.")
    print()

if __name__ == "__main__":
    view_module_docs()
