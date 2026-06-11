"""Data models, enums, and constants for the bot."""
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class Specialization(str, Enum):
    """Controller specialization types."""
    ENTRANCE = "entrance"
    HALL = "hall"
    VIP = "vip"

    @property
    def label(self) -> str:
        return _SPEC_LABELS[self.value]


_SPEC_LABELS = {
    "entrance": "Контролер на входе",
    "hall": "Распорядитель в зале",
    "vip": "VIP-сопровождение",
}


class ExperienceType(str, Enum):
    """Event experience types."""
    CONCERTS = "concerts"
    CONFERENCES = "conferences"
    SPORTS = "sports"
    CORPORATE = "corporate"

    @property
    def label(self) -> str:
        return _EXP_LABELS[self.value]


_EXP_LABELS = {
    "concerts": "Концерты",
    "conferences": "Конференции",
    "sports": "Спорт",
    "corporate": "Корпоративы",
}


class Language(str, Enum):
    """Language skills."""
    RUSSIAN = "russian"
    ENGLISH = "english"
    CHINESE = "chinese"
    FRENCH = "french"
    GERMAN = "german"
    SPANISH = "spanish"
    JAPANESE = "japanese"
    TURKISH = "turkish"
    KAZAKH = "kazakh"
    POLISH = "polish"

    @property
    def label(self) -> str:
        return _LANG_LABELS[self.value]


_LANG_LABELS = {
    "russian": "Русский",
    "english": "Английский",
    "chinese": "Китайский",
    "french": "Французский",
    "german": "Немецкий",
    "spanish": "Испанский",
    "japanese": "Японский", 
    "turkish": "Турецкий",
    "kazakh": "Казахский",
    "polish": "Польский",
}


class WorkArea(str, Enum):
    """Supported work areas for registration and admin filtering."""
    NN_SORMOVSKY = "nn_sormovsky"
    NN_AVTOZAVOD = "nn_avtozavod"
    NN_KANAVINSKY = "nn_kanavinsky"
    NN_LENINSKY = "nn_leninsky"
    NN_MOSKOVSKY = "nn_moskovsky"
    NN_NIZHEGORODSKY = "nn_nizhegorodsky"
    NN_PRIOKSKY = "nn_prioksky"
    NN_SOVETSKY = "nn_sovetsky"
    NN_OBLAST = "nn_oblast"

    @property
    def label(self) -> str:
        return _AREA_LABELS[self.value]


_AREA_LABELS = {
    "nn_sormovsky": "НН, Сормовский",
    "nn_avtozavod": "НН, Автозавод",
    "nn_kanavinsky": "НН, Канавинский",
    "nn_leninsky": "НН, Ленинский",
    "nn_moskovsky": "НН, Московский",
    "nn_nizhegorodsky": "НН, Нижегородский",
    "nn_prioksky": "НН, Приокский",
    "nn_sovetsky": "НН, Советский",
    "nn_oblast": "Нижегородская область",
}


class InvitationStatus(str, Enum):
    """Invitation response statuses."""
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    THINKING = "thinking"
    EXPIRED = "expired"

    @property
    def label(self) -> str:
        return _INV_STATUS_LABELS[self.value]


_INV_STATUS_LABELS = {
    "sent": "📤 Отправлено",
    "accepted": "✅ Принято",
    "declined": "❌ Отклонено",
    "thinking": "🤔 В раздумьях",
    "expired": "⏰ Истекло",
}


class EventStatus(str, Enum):
    """Event statuses."""
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeclineReason(str, Enum):
    """Standard decline reasons for invitations."""
    DATE = "date"
    LOCATION = "location"
    RATE = "rate"
    BUSY = "busy"
    OTHER = "other"

    @property
    def label(self) -> str:
        return _DECLINE_LABELS[self.value]


_DECLINE_LABELS = {
    "date": "Неудобная дата",
    "location": "Неудобная локация",
    "rate": "Не устраивает ставка",
    "busy": "Уже занят(а)",
    "other": "Другая причина",
}


@dataclass
class FilterState:
    """Current filter state for admin controller search."""
    specializations: List[str] = field(default_factory=list)
    min_rating: float = 0.0
    experience_types: List[str] = field(default_factory=list)
    location: Optional[str] = None
    areas: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    available_date: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dict for FSM storage."""
        return {
            "specializations": self.specializations,
            "min_rating": self.min_rating,
            "experience_types": self.experience_types,
            "location": self.location,
            "areas": self.areas,
            "languages": self.languages,
            "available_date": self.available_date,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FilterState":
        """Deserialize from FSM storage dict."""
        if not data:
            return cls()
        return cls(
            specializations=data.get("specializations", []),
            min_rating=data.get("min_rating", 0.0),
            experience_types=data.get("experience_types", []),
            location=data.get("location"),
            areas=data.get("areas", []),
            languages=data.get("languages", []),
            available_date=data.get("available_date"),
        )

    @property
    def is_empty(self) -> bool:
        """Check if no filters are active."""
        return (
            not self.specializations
            and self.min_rating == 0.0
            and not self.experience_types
            and self.location is None
            and not self.areas
            and not self.languages
            and self.available_date is None
        )

    def describe(self) -> str:
        """Return human-readable description of active filters."""
        parts = []
        if self.specializations:
            specs = [Specialization(s).label for s in self.specializations]
            parts.append(f"🎯 Специализация: {', '.join(specs)}")
        if self.min_rating > 0:
            parts.append(f"⭐ Рейтинг: от {self.min_rating}")
        if self.experience_types:
            exps = [ExperienceType(e).label for e in self.experience_types]
            parts.append(f"🏢 Опыт: {', '.join(exps)}")
        if self.location:
            parts.append(f"📍 Локация: {self.location}")
        if self.areas:
            area_labels = [WorkArea(a).label if a in [w.value for w in WorkArea] else a for a in self.areas]
            parts.append(f"📍 Районы: {', '.join(area_labels)}")
        if self.languages:
            langs = [Language(l).label for l in self.languages]
            parts.append(f"🌐 Языки: {', '.join(langs)}")
        if self.available_date:
            parts.append(f"📅 Доступен: {self.available_date}")
        return "\n".join(parts) if parts else "Фильтры не заданы"


# Pagination
CONTROLLERS_PER_PAGE = 5
