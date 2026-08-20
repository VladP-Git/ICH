"""Набор автоматических модульных тестов (QA) для проверки бизнес-логики.

Использует фреймворк pytest для изолированного тестирования компонента funcs.py
без реального подключения к базам данных MySQL/MongoDB с помощью MagicMock.
"""

import pytest
from fastapi import Request
from unittest.mock import MagicMock
import funcs


# ─── ПРЕЗЕНТАЦИЯ: ФИКСТУРЫ (TEST FIXTURES) ───────────────────────────────────

@pytest.fixture
def mock_request():
    """Создает виртуальный HTTP-запрос для имитации Query-параметров.

    ПОЧЕМУ ТАК: Позволяет симулировать ввод данных пользователем в форму
    и отправку GET-параметров в URL без физического поднятия сервера FastAPI.
    """
    request = MagicMock(spec=Request)
    request.query_params = {}  # По умолчанию строка параметров пустая
    return request


# ─── ПРЕЗЕНТАЦИЯ: МОДУЛЬНЫЕ ТЕСТЫ ОЧИСТКИ СТРОК И ВАЛИДАЦИИ ──────────────────

@pytest.mark.parametrize(
    "raw_word, expected_cleaned",
    [
        ("  ACADEMY DINOSAUR  ", "ACADEMY DINOSAUR"),  # Удаление пробелов по краям
        ("matrix", "matrix"),                          # Обычное слово без изменений
        ("   ", ""),                                   # Строка только из пробелов
    ]
)
def test_prepare_index_context_removes_spaces_from_search_word(mock_request, raw_word, expected_cleaned):
    """Проверяет автоматическую очистку поискового запроса методом .strip()."""
    # Симулируем отправку формы и ввод ключевого слова с пробелами
    mock_request.query_params = {
        "search_submitted": "1",
        "search_word": raw_word
    }

    context = funcs.prepare_index_context(mock_request)

    # Проверяем, что бэкенд успешно очистил строку
    assert context["search_word"] == expected_cleaned


def test_prepare_index_context_triggers_empty_search_flag(mock_request):
    """Проверяет активацию флага пустой строки при вводе одних пробелов.

    ПОЧЕМУ ТАК: Тест гарантирует, что если пользователь отправил пустые
    пробелы, бэкенд не сломается, а выведет Bootstrap-плашку предупреждения.
    """
    mock_request.query_params = {
        "search_submitted": "1",
        "search_word": "     "  # Имитируем ввод одних пробелов
    }

    context = funcs.prepare_index_context(mock_request)

    # Триггер пустого поиска должен стать True, а флаг активного поиска — False
    assert context["empty_search"] is True
    assert context["is_searched"] is False


# ─── ПРЕЗЕНТАЦИЯ: ТЕСТЫ РЕЖИМОВ ПАГИНАЦИИ (GRID MODES) ───────────────────────

@pytest.mark.parametrize(
    "view_mode, expected_limit",
    [
        ("strict", 10),    # По ТЗ выводим строго 10 карточек на страницу
        ("adaptive", 6),   # Демонстрационный формат выводит 6 карточек
        (None, 6)          # По умолчанию включается режим adaptive (fallback)
    ]
)
def test_prepare_index_context_calculates_correct_limit_based_on_view_mode(mock_request, view_mode, expected_limit):
    """Проверяет точный расчет лимита карточек для каждого режима сетки.

    🎯: Использование @pytest.mark.parametrize избавляет от дублирования
    кода, позволяя протестировать три разных граничных условия в одном методе.
    """
    params = {}
    if view_mode:
        params["view_mode"] = view_mode
    mock_request.query_params = params

    context = funcs.prepare_index_context(mock_request)

    # Лимит пагинации на бэкенде должен строго соответствовать выбранному формату
    assert context["current_limit"] == expected_limit
