import os
import logging
from logging.handlers import TimedRotatingFileHandler
# Импортируем настройку режима из нашего локального файла
from local_settings import ENV_MODE


def setup_logger():
    """
    Настраивает и возвращает глобальный логгер для веб-приложения.
    Реализует ежедневную ротацию логов с добавлением даты к архивным файлам.
    """
    # Абсолютный путь к папке backend/
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Абсолютный путь к корню проекта (movie_search_project/)
    base_dir = os.path.dirname(current_dir)
    # Файл лога будет лежать в корне проекта
    log_file = os.path.join(base_dir, 'app.log')

    # Создаем объект логгера
    logger = logging.getLogger("sakila_app")

    # Динамически управляем уровнем строгости логов на основе local_settings
    if ENV_MODE == 'production':
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)

    # Защита от дублирования хендлеров при перезапусках Flask
    if not logger.handlers:
        # Ротация каждый день ('D'), хранить архивы за последние 30 дней
        file_handler = TimedRotatingFileHandler(
            log_file,
            when='D',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )

        # Суффикс даты, который добавится к имени файла при ротации (например, app.log.2026-07-08)
        file_handler.suffix = "%Y-%m-%d"

        # Задаем формат записи лога
        # [Время] [УРОВЕНЬ LOG_LEVEL] [Имя файла:Линия кода] -> Текст сообщения
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] -> %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        # Добавляем хендлер к логгеру
        logger.addHandler(file_handler)

        # Ошибки дублируем в консоль PyCharm
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.ERROR)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


# Инициализируем глобальный объект логгера, который будут импортировать другие модули
app_logger = setup_logger()
