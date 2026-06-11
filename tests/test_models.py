"""Tests for database/models.py — enums, FilterState, constants."""
import pytest
from database.models import (
    FilterState,
    Specialization,
    ExperienceType,
    Language,
    WorkArea,
    InvitationStatus,
    DeclineReason,
    CONTROLLERS_PER_PAGE,
)


class TestEnumLabels:
    def test_specialization_labels_not_empty(self):
        for spec in Specialization:
            assert spec.label, f"{spec} has empty label"

    def test_experience_type_labels_not_empty(self):
        for exp in ExperienceType:
            assert exp.label, f"{exp} has empty label"

    def test_language_labels_not_empty(self):
        for lang in Language:
            assert lang.label, f"{lang} has empty label"

    def test_work_area_labels_not_empty(self):
        for area in WorkArea:
            assert area.label, f"{area} has empty label"

    def test_invitation_status_labels_not_empty(self):
        for status in InvitationStatus:
            assert status.label, f"{status} has empty label"

    def test_decline_reason_labels_not_empty(self):
        for reason in DeclineReason:
            assert reason.label, f"{reason} has empty label"

    def test_specific_specialization_label(self):
        assert Specialization.ENTRANCE.label == "Контролер на входе"
        assert Specialization.HALL.label == "Распорядитель в зале"
        assert Specialization.VIP.label == "VIP-сопровождение"

    def test_specific_invitation_status_label(self):
        assert "Принято" in InvitationStatus.ACCEPTED.label
        assert "Отклонено" in InvitationStatus.DECLINED.label
        assert "раздумьях" in InvitationStatus.THINKING.label


class TestFilterState:
    def test_empty_by_default(self):
        fs = FilterState()
        assert fs.is_empty is True

    def test_not_empty_with_specialization(self):
        fs = FilterState(specializations=["entrance"])
        assert fs.is_empty is False

    def test_not_empty_with_rating(self):
        fs = FilterState(min_rating=3.5)
        assert fs.is_empty is False

    def test_not_empty_with_date(self):
        fs = FilterState(available_date="2025-06-15")
        assert fs.is_empty is False

    def test_roundtrip_serialization(self):
        original = FilterState(
            specializations=["entrance", "vip"],
            min_rating=4.0,
            experience_types=["concerts"],
            areas=["nn_sovetsky"],
            languages=["english"],
            available_date="2025-08-01",
        )
        restored = FilterState.from_dict(original.to_dict())
        assert restored.specializations == original.specializations
        assert restored.min_rating == original.min_rating
        assert restored.experience_types == original.experience_types
        assert restored.areas == original.areas
        assert restored.languages == original.languages
        assert restored.available_date == original.available_date

    def test_from_dict_empty_returns_default(self):
        fs = FilterState.from_dict({})
        assert fs.is_empty is True

    def test_describe_empty(self):
        fs = FilterState()
        assert fs.describe() == "Фильтры не заданы"

    def test_describe_with_rating(self):
        fs = FilterState(min_rating=4.0)
        desc = fs.describe()
        assert "4.0" in desc
        assert "Рейтинг" in desc

    def test_describe_with_specializations(self):
        fs = FilterState(specializations=["entrance"])
        desc = fs.describe()
        assert "Специализация" in desc
        assert "Контролер на входе" in desc

    def test_describe_with_date(self):
        fs = FilterState(available_date="2025-07-01")
        desc = fs.describe()
        assert "2025-07-01" in desc

    def test_controllers_per_page_positive(self):
        assert CONTROLLERS_PER_PAGE > 0
