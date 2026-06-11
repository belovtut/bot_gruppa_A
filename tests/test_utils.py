"""Tests for bot/utils.py — pure utility functions."""
import pytest
from bot.utils import (
    validate_date,
    validate_phone_ru,
    validate_full_name,
    validate_birth_date,
    format_rating,
    format_enum_list,
    age_from_birth_date,
    birth_date_to_display,
    validate_time,
)
from database.models import Specialization, ExperienceType, Language


# ---------------------------------------------------------------------------
# validate_date
# ---------------------------------------------------------------------------

class TestValidateDate:
    def test_accepts_dd_mm_yyyy(self):
        assert validate_date("15.06.2025") == "2025-06-15"

    def test_accepts_iso_format(self):
        assert validate_date("2025-06-15") == "2025-06-15"

    def test_rejects_invalid_day(self):
        assert validate_date("32.01.2025") is None

    def test_rejects_wrong_separator(self):
        assert validate_date("15/06/2025") is None

    def test_rejects_empty_string(self):
        assert validate_date("") is None

    def test_rejects_partial_date(self):
        assert validate_date("15.06") is None

    def test_strips_whitespace(self):
        assert validate_date("  15.06.2025  ") == "2025-06-15"


# ---------------------------------------------------------------------------
# validate_time
# ---------------------------------------------------------------------------

class TestValidateTime:
    def test_accepts_hh_mm(self):
        assert validate_time("14:30") == "14:30"

    def test_accepts_single_digit_hour(self):
        assert validate_time("9:00") == "09:00"

    def test_rejects_invalid_time(self):
        assert validate_time("25:00") is None

    def test_rejects_wrong_format(self):
        assert validate_time("1430") is None


# ---------------------------------------------------------------------------
# validate_phone_ru
# ---------------------------------------------------------------------------

class TestValidatePhoneRu:
    def test_accepts_correct_format(self):
        assert validate_phone_ru("+79991234567") == "+79991234567"

    def test_rejects_without_plus(self):
        assert validate_phone_ru("79991234567") is None

    def test_rejects_8_prefix(self):
        assert validate_phone_ru("89991234567") is None

    def test_rejects_too_short(self):
        assert validate_phone_ru("+7999123456") is None

    def test_rejects_too_long(self):
        assert validate_phone_ru("+799912345678") is None

    def test_rejects_letters(self):
        assert validate_phone_ru("+7999123456a") is None

    def test_strips_whitespace(self):
        assert validate_phone_ru("  +79991234567  ") == "+79991234567"


# ---------------------------------------------------------------------------
# validate_full_name
# ---------------------------------------------------------------------------

class TestValidateFullName:
    def test_accepts_three_words(self):
        assert validate_full_name("Иванов Иван Иванович") == "Иванов Иван Иванович"

    def test_accepts_four_words(self):
        result = validate_full_name("Иванов Иван Иванович Дополнительный")
        assert result is not None

    def test_rejects_two_words(self):
        assert validate_full_name("Иванов Иван") is None

    def test_rejects_with_initials(self):
        # Dots are forbidden (treated as initials)
        assert validate_full_name("Иванов И.И.") is None

    def test_accepts_hyphenated_surname(self):
        result = validate_full_name("Иванов-Петров Иван Иванович")
        assert result is not None

    def test_rejects_empty(self):
        assert validate_full_name("") is None

    def test_normalizes_extra_spaces(self):
        result = validate_full_name("  Иванов  Иван  Иванович  ")
        assert result == "Иванов Иван Иванович"


# ---------------------------------------------------------------------------
# validate_birth_date
# ---------------------------------------------------------------------------

class TestValidateBirthDate:
    def test_accepts_adult(self):
        # Someone born in 1990 is definitely 18+
        result = validate_birth_date("01.01.1990")
        assert result == "1990-01-01"

    def test_rejects_underage(self):
        # Born "today" means 0 years old
        from datetime import date
        today = date.today()
        dob = today.strftime("%d.%m.%Y")
        assert validate_birth_date(dob) is None

    def test_rejects_too_old(self):
        assert validate_birth_date("01.01.1920") is None

    def test_rejects_wrong_format(self):
        assert validate_birth_date("1990-01-01") is None

    def test_rejects_invalid_day(self):
        assert validate_birth_date("32.01.1990") is None


# ---------------------------------------------------------------------------
# format_rating
# ---------------------------------------------------------------------------

class TestFormatRating:
    def test_formats_zero(self):
        assert format_rating(0.0) == "0.0/5.0"

    def test_formats_max(self):
        assert format_rating(5.0) == "5.0/5.0"

    def test_formats_decimal(self):
        assert format_rating(4.5) == "4.5/5.0"


# ---------------------------------------------------------------------------
# format_enum_list
# ---------------------------------------------------------------------------

class TestFormatEnumList:
    def test_single_value(self):
        result = format_enum_list(["entrance"], Specialization)
        assert result == "Контролер на входе"

    def test_multiple_values(self):
        result = format_enum_list(["entrance", "hall"], Specialization)
        assert "Контролер на входе" in result
        assert "Распорядитель в зале" in result

    def test_empty_list_returns_dash(self):
        assert format_enum_list([], Specialization) == "—"

    def test_unknown_value_returned_as_is(self):
        result = format_enum_list(["unknown_code"], Specialization)
        assert "unknown_code" in result


# ---------------------------------------------------------------------------
# age_from_birth_date / birth_date_to_display
# ---------------------------------------------------------------------------

class TestDateHelpers:
    def test_age_from_birth_date_1990(self):
        age = age_from_birth_date("1990-01-01")
        from datetime import date
        expected = date.today().year - 1990
        assert abs(age - expected) <= 1  # allow ±1 for birthday not yet passed

    def test_age_from_birth_date_none(self):
        assert age_from_birth_date(None) is None

    def test_birth_date_to_display_normal(self):
        assert birth_date_to_display("1990-06-15") == "15.06.1990"

    def test_birth_date_to_display_none(self):
        assert birth_date_to_display(None) == "—"
