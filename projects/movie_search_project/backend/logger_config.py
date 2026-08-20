"""Модуль централизованного журналирования и логирования Sakila Cinema.

Настраивает глобальный регистратор событий приложения (app_logger), реализует
механизм автоматической ежедневной ротации файлов журналов (TimedRotatingFileHandler),
динамически управляет уровнями строгости (DEBUG/INFO) на основе окружения ENV_MODE
и обеспечивает защиту от дублирования потоков вывода при Live Reload.
"""

import os
import logging
from logging.handlers import TimedRotatingFileHandler
# Импортируем настройку режима из нашего локального файла конфигурации
from local_settings import ENV_MODE


def setup_logger() -> logging.Logger:
    """Конфигурирует и инициализирует глобальный объект логгера для всего проекта.

    Автоматически рассчитывает пути к корневому каталогу, настраивает форматирование
    временных меток, изолирует потоки вывода ошибок в стандартную консоль
    и ограничивает глубину хранения архивных журналов тридцатью днями.

    Returns:
        logging.Logger: Настроенный экземпляр логгера, готовый к сквозному импорту.
    """
    # Абсолютный путь к папке backend/
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Абсолютный путь к корню проекта (movie_search_project/)
    base_dir = os.path.dirname(current_dir)
    # Файл лога будет лежать в корне проекта для быстрого доступа разработчика
    log_file = os.path.join(base_dir, 'app.log')

    # Создаем именованный объект логгера
    logger = logging.getLogger("sakila_app")

    # ─── ПРЕЗЕНТАЦИЯ: ДИНАМИЧЕСКИЙ МЕНЕДЖМЕНТ УРОВНЕЙ СТРОГОСТИ ──────────────
    # ПОЧЕМУ ТАК: На продакшене избыточный дебаг-лог отключается ради экономии I/O,
    # а в режиме локальной разработки (development) пишется максимум информации.
    if ENV_MODE == 'production':
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)

    # 🎯: Защита от дублирования хендлеров при перезапусках.
    # Uvicorn при Live Reload постоянно перезагружает контекст модулей. Без этой проверки
    # обработчики бы плодились, вызывая дублирование записей и утечку дескрипторов файлов.
    if not logger.handlers:
        # ─── ПРЕЗЕНТАЦИЯ: СТРАТЕГИЯ АВТОМАТИЧЕСКОЙ РОТАЦИИ (CLEAN ARCHITECTURE) ──
        # ПОЧЕМУ ТАК: TimedRotatingFileHandler с параметром 'D' и backupCount=30
        # автоматически ротирует логи каждые сутки и хранит историю за месяц,
        # полностью защищая сервер от критического переполнения дискового пространства.
        file_handler = TimedRotatingFileHandler(
            log_file,
            when='D',
            interval=1,
            backupCount=30,
            encoding='utf-8'  # Гарантирует корректное сохранение кириллицы в файле
        )

        # Суффикс даты, который добавится к имени файла при ротации (например, app.log.2026-08-20)
        file_handler.suffix = "%Y-%m-%d"

        # Задаем промышленный стандарт форматирования записи лога
        # [Время] [УРОВЕНЬ] [Имя файла:Линия кода] -> Текст сообщения
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] -> %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        # Прикрепляем файловый обработчик к ядру логгера
        logger.addHandler(file_handler)

        # ─── ПРЕЗЕНТАЦИЯ: ДУБЛИРОВАНИЕ КРИТИЧЕСКИХ СБОЕВ В СТАНДАРТНЫЙ ВЫВОД ─────
        # ПОЧЕМУ ТАК: Ошибки уровня ERROR дублируются в StreamHandler (консоль PyCharm).
        # Разработчику не нужно открывать app.log во время демонстрации — аварии видны сразу.
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.ERROR)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


# Инициализируем глобальный объект логгера для импорта в funcs.py и другие модули
app_logger = setup_logger()
