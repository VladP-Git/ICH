import pytest
from fastapi import Request
from unittest.mock import MagicMock
import funcs


# --- 1. ФИКСТУРЫ (Заменяют устаревший setUp) ---

@pytest.fixture
def mock_request():
    """
    Фикстура для создания виртуального HTTP-запроса.
    Позволяет имитировать Query-параметры URL без запуска сервера.
    """
    request = MagicMock(spec=Request)
    # По умолчанию строка запроса пустая
    request.query_params = {}
    return request


# --- 2. ПАРАМЕТРИЗАЦИЯ И ТЕСТЫ ВАЛИДАЦИИ ---

@pytest.mark.parametrize(
    "raw_word, expected_cleaned",
    [
        ("  ACADEMY DINOSAUR  ", "ACADEMY DINOSAUR"),  # Удаление пробелов по краям
        ("matrix", "matrix"),  # Обычное слово без изменений
        ("   ", ""),  # Строка только из пробелов превращается в пустую
    ]
)
def test_prepare_index_context_removes_spaces_from_search_word(mock_request, raw_word, expected_cleaned):
    """Проверяет, что поисковый запрос пользователя всегда очищается от пробелов методом .strip()"""
    # Симулируем отправку формы и ввод слова с пробелами
    mock_request.query_params = {
        "search_submitted": "1",
        "search_word": raw_word
    }

    context = funcs.prepare_index_context(mock_request)

    assert context["search_word"] == expected_cleaned


def test_prepare_index_context_triggers_empty_search_flag(mock_request):
    """Проверяет, что ввод одних пробелов активирует флаг empty_search для вывода плашки"""
    mock_request.query_params = {
        "search_submitted": "1",
        "search_word": "     "  # Только пробелы
    }

    context = funcs.prepare_index_context(mock_request)

    assert context["empty_search"] is True
    assert context["is_searched"] is False


@pytest.mark.parametrize(
    "view_mode, expected_limit",
    [
        ("strict", 10),  # По ТЗ выводим строго 10 карточек
        ("adaptive", 6),  # Демонстрационный формат выводит 6 карточек
        (None, 6)  # По умолчанию включается режим adaptive (6 карточек)
    ]
)
def test_prepare_index_context_calculates_correct_limit_based_on_view_mode(mock_request, view_mode, expected_limit):
    """Проверяет, что лимит пагинации строго соответствует выбранному формату сетки"""
    params = {}
    if view_mode:
        params["view_mode"] = view_mode
    mock_request.query_params = params

    context = funcs.prepare_index_context(mock_request)

    assert context["current_limit"] == expected_limit
