"""Keyboard layouts for all bot interactions.

Naming conventions:
  get_*_keyboard  – returns a ReplyKeyboardMarkup / InlineKeyboardMarkup
  Callback-data prefixes:
    fc:  – filter category
    f:   – filter value toggle
    b:   – browse-mode controller action
    i:   – invite-mode controller action
    ir:  – invitation response
    dr:  – decline reason
    pr:  – profile registration callbacks
"""
from typing import Dict, List, Optional, Set

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from database.models import (
    CONTROLLERS_PER_PAGE,
    DeclineReason,
    ExperienceType,
    FilterState,
    Language,
    Specialization,
    WorkArea,
)

# ======================================================================
# Reply keyboards (persistent buttons below the text input)
# ======================================================================


def get_main_menu_keyboard(*, is_controller: bool = False) -> ReplyKeyboardMarkup:
    """Main menu for regular users (and registered controllers)."""
    rows = [
        [KeyboardButton(text="📋 Часто задаваемые вопросы")],
        [KeyboardButton(text="💼 О вакансиях КРС")],
        [KeyboardButton(text="📞 Контакты")],
        [KeyboardButton(text="ℹ️ О боте")],
    ]
    if is_controller:
        rows.append([
            KeyboardButton(text="📨 Мои приглашения"),
            KeyboardButton(text="👤 Мой профиль"),
        ])
    else:
        rows.append([KeyboardButton(text="✍️ Хочу стать КРС")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Admin panel keyboard per tech-spec §2.1."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 База контролеров")],
            [KeyboardButton(text="📨 Пригласить из базы")],
            [KeyboardButton(text="➕ Добавить контролера")],
            [KeyboardButton(text="📥 Заявки в штат")],
            [KeyboardButton(text="📨 Рассылка всем")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🔙 Главное меню")],
        ],
        resize_keyboard=True,
    )


def get_faq_keyboard() -> InlineKeyboardMarkup:
    """FAQ inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Что такое КРС?", callback_data="faq_krs")],
            [InlineKeyboardButton(text="Требования к кандидатам", callback_data="faq_requirements")],
            [InlineKeyboardButton(text="График работы", callback_data="faq_schedule")],
            [InlineKeyboardButton(text="Условия работы", callback_data="faq_conditions")],
            [InlineKeyboardButton(text="Как устроиться?", callback_data="faq_how_to_apply")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ]
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Simple keyboard with a cancel button (used during FSM flows)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


# ======================================================================
# Filter keyboards (admin: browse / invite)
# ======================================================================


def get_filter_menu_keyboard(filters: FilterState, mode: str) -> InlineKeyboardMarkup:
    """Main filter-category selector.

    *mode* is ``"browse"`` or ``"invite"``.
    """
    def _badge(label: str, active: bool) -> str:
        return f"{'✅ ' if active else ''}{label}"

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(
            text=_badge("🎯 Специализация", bool(filters.specializations)),
            callback_data=f"fc:spec:{mode}")],
        [InlineKeyboardButton(
            text=_badge(f"⭐ Рейтинг{f' ⩾ {filters.min_rating}' if filters.min_rating else ''}",
                        filters.min_rating > 0),
            callback_data=f"fc:rat:{mode}")],
        [InlineKeyboardButton(
            text=_badge("🏢 Опыт работы", bool(filters.experience_types)),
            callback_data=f"fc:exp:{mode}")],
        [InlineKeyboardButton(
            text=_badge("🌐 Языки", bool(filters.languages)),
            callback_data=f"fc:lng:{mode}")],
        [InlineKeyboardButton(
            text=_badge(
                "📍 Районы" + (
                    f" ({len(filters.areas)})" if filters.areas else ""
                ),
                bool(filters.areas),
            ),
            callback_data=f"fc:loc:{mode}")],
        [InlineKeyboardButton(
            text=_badge(f"📅 Дата{f': {filters.available_date}' if filters.available_date else ''}",
                        filters.available_date is not None),
            callback_data=f"fc:date:{mode}")],
    ]

    # Action row
    rows.append([
        InlineKeyboardButton(text="🔍 Показать результаты", callback_data=f"f:apply:{mode}"),
    ])
    rows.append([
        InlineKeyboardButton(text="🔄 Сбросить фильтры", callback_data=f"f:reset:{mode}"),
        InlineKeyboardButton(text="❌ Закрыть", callback_data="f:close"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_specialization_filter_keyboard(
    selected: List[str], mode: str
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for spec in Specialization:
        check = "☑" if spec.value in selected else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{check} {spec.label}",
            callback_data=f"f:s:{spec.value}:{mode}",
        )])
    rows.append([InlineKeyboardButton(
        text="◀️ Назад к фильтрам", callback_data=f"f:back:{mode}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_rating_filter_keyboard(
    current: float, mode: str
) -> InlineKeyboardMarkup:
    options = [0.0, 3.0, 3.5, 4.0, 4.5, 5.0]
    buttons: list[InlineKeyboardButton] = []
    for val in options:
        check = "●" if val == current else "○"
        label = "Без ограничений" if val == 0 else f"⩾ {val}"
        buttons.append(InlineKeyboardButton(
            text=f"{check} {label}",
            callback_data=f"f:r:{val}:{mode}",
        ))
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton(
        text="◀️ Назад к фильтрам", callback_data=f"f:back:{mode}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_experience_filter_keyboard(
    selected: List[str], mode: str
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for exp in ExperienceType:
        check = "☑" if exp.value in selected else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{check} {exp.label}",
            callback_data=f"f:e:{exp.value}:{mode}",
        )])
    rows.append([InlineKeyboardButton(
        text="◀️ Назад к фильтрам", callback_data=f"f:back:{mode}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_language_filter_keyboard(
    selected: List[str], mode: str
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for lang in Language:
        check = "☑" if lang.value in selected else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{check} {lang.label}",
            callback_data=f"f:l:{lang.value}:{mode}",
        )])
    rows.append([InlineKeyboardButton(
        text="◀️ Назад к фильтрам", callback_data=f"f:back:{mode}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_area_filter_keyboard(
    selected: List[str], mode: str
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for area in WorkArea:
        check = "☑" if area.value in selected else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{check} {area.label}",
            callback_data=f"f:loc:{area.value}:{mode}",
        )])
    rows.append([
        InlineKeyboardButton(text="🧹 Очистить", callback_data=f"f:loc:clear:{mode}")
    ])
    rows.append([
        InlineKeyboardButton(text="◀️ Назад к фильтрам", callback_data=f"f:back:{mode}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ======================================================================
# Controller-list keyboards
# ======================================================================


def get_controller_list_keyboard(
    controllers: List[Dict],
    page: int,
    total: int,
    mode: str,
    selected_ids: Optional[Set[int]] = None,
) -> InlineKeyboardMarkup:
    """Build the paginated controller list keyboard.

    *mode*: ``"browse"`` / ``"invite"``
    """
    selected_ids = selected_ids or set()
    rows: list[list[InlineKeyboardButton]] = []

    for ctrl in controllers:
        cid = ctrl["id"]
        name = ctrl.get("name", "—")
        rating = ctrl.get("rating", 0)
        label = f"{name} ⭐{rating:.1f}"

        if mode == "invite":
            check = "☑" if cid in selected_ids else "☐"
            rows.append([
                InlineKeyboardButton(
                    text=f"{check} {label}", callback_data=f"i:s:{cid}"),
                InlineKeyboardButton(
                    text="📋", callback_data=f"i:v:{cid}"),
            ])
        else:  # browse
            rows.append([InlineKeyboardButton(
                text=f"👤 {label}", callback_data=f"b:v:{cid}"
            )])

    # Pagination
    total_pages = max(1, (total + CONTROLLERS_PER_PAGE - 1) // CONTROLLERS_PER_PAGE)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{mode[0]}:pg:{page - 1}"))
    nav.append(InlineKeyboardButton(
        text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{mode[0]}:pg:{page + 1}"))
    rows.append(nav)

    if mode == "invite":
        rows.append([
            InlineKeyboardButton(text="✅ Выбрать всех", callback_data="i:all"),
            InlineKeyboardButton(text="🎲 Случайные N", callback_data="i:rnd"),
        ])
        count = len(selected_ids)
        rows.append([InlineKeyboardButton(
            text=f"📨 Пригласить выбранных ({count})",
            callback_data="i:send",
        )])

    rows.append([InlineKeyboardButton(
        text="🔍 Изменить фильтры", callback_data=f"f:back:{mode}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_controller_card_keyboard(
    controller_id: int, mode: str
) -> InlineKeyboardMarkup:
    """Buttons under a detailed controller card."""
    rows: list[list[InlineKeyboardButton]] = []
    if mode == "browse":
        rows.append([
            InlineKeyboardButton(
                text="✏️ Редактировать анкету",
                callback_data=f"b:edit:{controller_id}",
            )
        ])
    rows.extend([
        [InlineKeyboardButton(
            text="📜 История работы",
            callback_data=f"{mode[0]}:h:{controller_id}",
        )],
        [InlineKeyboardButton(
            text="◀️ К списку",
            callback_data=f"{mode[0]}:list",
        )],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_controller_edit_fields_keyboard(controller_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 ФИО", callback_data=f"b:ef:name:{controller_id}")],
        [InlineKeyboardButton(text="🎂 Дата рождения", callback_data=f"b:ef:birth_date:{controller_id}")],
        [InlineKeyboardButton(text="📱 Телефон", callback_data=f"b:ef:phone:{controller_id}")],
        [InlineKeyboardButton(text="👤 Username", callback_data=f"b:ef:username:{controller_id}")],
        [InlineKeyboardButton(text="📍 Локация", callback_data=f"b:ef:location:{controller_id}")],
        [InlineKeyboardButton(text="⭐ Рейтинг", callback_data=f"b:ef:rating:{controller_id}")],
        [InlineKeyboardButton(text="🔄 Активен/Неактивен", callback_data=f"b:ef:is_active:{controller_id}")],
        [InlineKeyboardButton(text="◀️ Назад к карточке", callback_data=f"b:v:{controller_id}")],
    ])


def get_history_back_keyboard(controller_id: int, mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="◀️ К карточке",
            callback_data=f"{mode[0]}:v:{controller_id}",
        )],
    ])


# ======================================================================
# Invitation-creation keyboards
# ======================================================================


def get_skip_keyboard() -> InlineKeyboardMarkup:
    """Skip an optional field during event creation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ Пропустить", callback_data="inv:skip")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="inv:cancel")],
    ])


def get_required_field_keyboard() -> InlineKeyboardMarkup:
    """Cancel button only."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="inv:cancel")],
    ])


def get_confirm_invite_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить приглашения", callback_data="inv:confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="inv:cancel")],
    ])


# ======================================================================
# Invitation-response keyboards (sent to controllers)
# ======================================================================


def get_invitation_buttons(invitation_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"ir:a:{invitation_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"ir:d:{invitation_id}"),
        ],
        [InlineKeyboardButton(text="🤔 Подумать", callback_data=f"ir:t:{invitation_id}")],
    ])


def get_decline_reasons_keyboard(invitation_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for reason in DeclineReason:
        rows.append([InlineKeyboardButton(
            text=reason.label,
            callback_data=f"dr:{invitation_id}:{reason.value}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_reminder_keyboard(invitation_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"ir:a:{invitation_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"ir:d:{invitation_id}"),
        ],
    ])


# ======================================================================
# Profile / Registration keyboards
# ======================================================================


def get_profile_specializations_keyboard(selected: List[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for spec in Specialization:
        check = "☑" if spec.value in selected else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{check} {spec.label}",
            callback_data=f"pr:s:{spec.value}",
        )])
    rows.append([InlineKeyboardButton(text="✅ Продолжить", callback_data="pr:s:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_profile_experience_keyboard(selected: List[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for exp in ExperienceType:
        check = "☑" if exp.value in selected else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{check} {exp.label}",
            callback_data=f"pr:e:{exp.value}",
        )])
    rows.append([InlineKeyboardButton(text="✅ Продолжить", callback_data="pr:e:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_profile_languages_keyboard(selected: List[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for lang in Language:
        check = "☑" if lang.value in selected else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{check} {lang.label}",
            callback_data=f"pr:l:{lang.value}",
        )])
    rows.append([InlineKeyboardButton(text="✅ Продолжить", callback_data="pr:l:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_profile_areas_keyboard(selected: List[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for area in WorkArea:
        check = "☑" if area.value in selected else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{check} {area.label}",
            callback_data=f"pr:area:{area.value}",
        )])
    rows.append([InlineKeyboardButton(text="✅ Продолжить", callback_data="pr:area:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_profile_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="pr:confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="pr:cancel")],
    ])


def get_my_invitations_keyboard(invitations: List[Dict]) -> InlineKeyboardMarkup:
    """Build a list of a controller's invitations."""
    rows: list[list[InlineKeyboardButton]] = []
    for inv in invitations[:10]:
        status_icon = {
            "sent": "📤", "accepted": "✅", "declined": "❌",
            "thinking": "🤔", "expired": "⏰",
        }.get(inv.get("status", ""), "❓")
        title = inv.get("title", "—")[:25]
        date = inv.get("event_date", "")
        rows.append([InlineKeyboardButton(
            text=f"{status_icon} {date} {title}",
            callback_data=f"mi:{inv['id']}",
        )])
    if not rows:
        rows.append([InlineKeyboardButton(text="Нет приглашений", callback_data="noop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_staff_applications_keyboard(applications: List[Dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    status_icon = {
        "new": "🆕",
        "in_review": "👀",
        "closed": "✅",
        "deleted": "🗑",
    }
    for app in applications[:20]:
        icon = status_icon.get(app.get("status", "new"), "📄")
        title = app.get("full_name", "—")[:28]
        created = app.get("created_at", "")[:10]
        rows.append([InlineKeyboardButton(
            text=f"{icon} {created} {title}",
            callback_data=f"sa:view:{app['id']}",
        )])
    if not rows:
        rows.append([InlineKeyboardButton(text="Заявок пока нет", callback_data="noop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_staff_application_actions_keyboard(
    application_id: int,
    user_id: int,
    username: Optional[str] = None,
) -> InlineKeyboardMarkup:
    account_label = (
        f"👤Telegram аккаунт @{username}" if username else "👤Telegram аккаунт (username скрыт)"
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить и добавить в базу КРС", callback_data=f"sa:approve:{application_id}")],
        [InlineKeyboardButton(text="💬 Написать кандидату", callback_data=f"sa:msg:{application_id}")],
        [InlineKeyboardButton(text=account_label, url=f"tg://user?id={user_id}")],
        [InlineKeyboardButton(text="🗑 Удалить заявку", callback_data=f"sa:del:{application_id}")],
        [InlineKeyboardButton(text="◀️ К списку заявок", callback_data="sa:list")],
    ])


def get_staff_dialog_keyboard(application_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Отправить сообщение кандидату", callback_data=f"sa:compose:{application_id}")],
        [InlineKeyboardButton(text="◀️ Назад к заявке", callback_data=f"sa:view:{application_id}")],
    ])


def get_candidate_application_reply_keyboard(application_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Ответить администратору", callback_data=f"app:reply:{application_id}")],
    ])
