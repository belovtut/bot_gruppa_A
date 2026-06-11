"""Controller-database handlers: browse, filter, search, view cards, history.

Shared between *browse* (mode="browse") and *invite* (mode="invite") flows.
"""
import logging
from typing import Any, Dict, Set

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.deps import is_admin
from database import Database
from bot.services.controller_filters import filters_to_search_kwargs
from bot.keyboards import (
    get_admin_keyboard,
    get_area_filter_keyboard,
    get_controller_card_keyboard,
    get_controller_edit_fields_keyboard,
    get_controller_list_keyboard,
    get_experience_filter_keyboard,
    get_filter_menu_keyboard,
    get_history_back_keyboard,
    get_language_filter_keyboard,
    get_rating_filter_keyboard,
    get_specialization_filter_keyboard,
)
from database.models import CONTROLLERS_PER_PAGE, FilterState
from bot.utils import (
    format_controller_card,
    format_history_entry,
    validate_birth_date,
    validate_date,
    validate_full_name,
    validate_phone_ru,
)
from .states import ControllerEditStates, FilterStates

logger = logging.getLogger(__name__)
router = Router(name="controller_db")


# ------------------------------------------------------------------
# Entry-points (reply-keyboard buttons)
# ------------------------------------------------------------------

@router.message(F.text == "👥 База контролеров")
async def browse_controllers(message: Message, state: FSMContext) -> None:
    """Open the controller database in browse mode."""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return
    await _open_filter_menu(message, state, mode="browse")


@router.message(F.text == "📨 Пригласить из базы")
async def invite_from_db(message: Message, state: FSMContext) -> None:
    """Open the controller database in invite mode."""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return
    await _open_filter_menu(message, state, mode="invite")


async def _open_filter_menu(message: Message, state: FSMContext, mode: str) -> None:
    """Send the filter menu and enter filter FSM."""
    await state.set_state(FilterStates.active)
    await state.update_data(
        filters=FilterState().to_dict(),
        mode=mode,
        page=0,
        selected_ids=[],
    )
    filters = FilterState()
    await message.answer(
        f"🔍 <b>{'Поиск контролеров' if mode == 'browse' else 'Выбор контролеров для приглашения'}</b>\n\n"
        f"{filters.describe()}",
        parse_mode="HTML",
        reply_markup=get_filter_menu_keyboard(filters, mode),
    )


# ------------------------------------------------------------------
# Filter-category selection
# ------------------------------------------------------------------

@router.callback_query(FilterStates.active, F.data.startswith("fc:"))
async def filter_category(callback: CallbackQuery, state: FSMContext) -> None:
    """Open a specific filter sub-menu."""
    parts = callback.data.split(":")  # type: ignore[union-attr]
    cat = parts[1]   # spec / rat / exp / lng / loc / date
    mode = parts[2]
    data = await state.get_data()
    filters = FilterState.from_dict(data.get("filters", {}))

    if cat == "spec":
        kb = get_specialization_filter_keyboard(filters.specializations, mode)
        text = "Выберите специализации:"
    elif cat == "rat":
        kb = get_rating_filter_keyboard(filters.min_rating, mode)
        text = "Выберите минимальный рейтинг:"
    elif cat == "exp":
        kb = get_experience_filter_keyboard(filters.experience_types, mode)
        text = "Выберите типы мероприятий (опыт):"
    elif cat == "lng":
        kb = get_language_filter_keyboard(filters.languages, mode)
        text = "Выберите языки:"
    elif cat == "loc":
        kb = get_area_filter_keyboard(filters.areas, mode)
        text = "📍 Выберите районы для фильтра:"
    elif cat == "date":
        await state.set_state(FilterStates.entering_date)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "📅 Введите дату доступности (ДД.ММ.ГГГГ)\n"
            "(или отправьте /clear чтобы сбросить):"
        )
        await callback.answer()
        return
    else:
        await callback.answer("Неизвестный фильтр")
        return

    await callback.message.edit_text(text, reply_markup=kb)  # type: ignore[union-attr]
    await callback.answer()


# ------------------------------------------------------------------
# Filter value toggles
# ------------------------------------------------------------------

@router.callback_query(FilterStates.active, F.data.startswith("f:s:"))
async def toggle_spec(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    val, mode = parts[2], parts[3]
    data = await state.get_data()
    filters = FilterState.from_dict(data.get("filters", {}))
    if val in filters.specializations:
        filters.specializations.remove(val)
    else:
        filters.specializations.append(val)
    await state.update_data(filters=filters.to_dict())
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_specialization_filter_keyboard(filters.specializations, mode),
    )
    await callback.answer()


@router.callback_query(FilterStates.active, F.data.startswith("f:r:"))
async def set_rating(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    val, mode = float(parts[2]), parts[3]
    data = await state.get_data()
    filters = FilterState.from_dict(data.get("filters", {}))
    filters.min_rating = val
    await state.update_data(filters=filters.to_dict())
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_rating_filter_keyboard(val, mode),
    )
    await callback.answer()


@router.callback_query(FilterStates.active, F.data.startswith("f:e:"))
async def toggle_exp(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    val, mode = parts[2], parts[3]
    data = await state.get_data()
    filters = FilterState.from_dict(data.get("filters", {}))
    if val in filters.experience_types:
        filters.experience_types.remove(val)
    else:
        filters.experience_types.append(val)
    await state.update_data(filters=filters.to_dict())
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_experience_filter_keyboard(filters.experience_types, mode),
    )
    await callback.answer()


@router.callback_query(FilterStates.active, F.data.startswith("f:l:"))
async def toggle_lang(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    val, mode = parts[2], parts[3]
    data = await state.get_data()
    filters = FilterState.from_dict(data.get("filters", {}))
    if val in filters.languages:
        filters.languages.remove(val)
    else:
        filters.languages.append(val)
    await state.update_data(filters=filters.to_dict())
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_language_filter_keyboard(filters.languages, mode),
    )
    await callback.answer()


@router.callback_query(FilterStates.active, F.data.startswith("f:loc:"))
async def toggle_area(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    val, mode = parts[2], parts[3]
    data = await state.get_data()
    filters = FilterState.from_dict(data.get("filters", {}))

    if val == "clear":
        filters.areas = []
        filters.location = None
    elif val in filters.areas:
        filters.areas.remove(val)
    else:
        filters.areas.append(val)

    await state.update_data(filters=filters.to_dict())
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_area_filter_keyboard(filters.areas, mode),
    )
    await callback.answer()


@router.message(FilterStates.entering_date)
async def enter_date_filter(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    filters = FilterState.from_dict(data.get("filters", {}))
    mode = data.get("mode", "browse")
    if text == "/clear":
        filters.available_date = None
    else:
        parsed = validate_date(text)
        if not parsed:
            await message.answer("⚠️ Неверный формат. Введите дату ДД.ММ.ГГГГ:")
            return
        filters.available_date = parsed
    await state.update_data(filters=filters.to_dict())
    await state.set_state(FilterStates.active)
    await message.answer(
        f"🔍 <b>Фильтры поиска</b>\n\n{filters.describe()}",
        parse_mode="HTML",
        reply_markup=get_filter_menu_keyboard(filters, mode),
    )


# ------------------------------------------------------------------
# Back / Reset / Close / Apply
# ------------------------------------------------------------------

@router.callback_query(FilterStates.active, F.data.startswith("f:back:"))
async def filter_back(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.split(":")[2]  # type: ignore[union-attr]
    data = await state.get_data()
    filters = FilterState.from_dict(data.get("filters", {}))
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"🔍 <b>Фильтры поиска</b>\n\n{filters.describe()}",
        parse_mode="HTML",
        reply_markup=get_filter_menu_keyboard(filters, mode),
    )
    await callback.answer()


@router.callback_query(FilterStates.active, F.data.startswith("f:reset:"))
async def filter_reset(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.split(":")[2]  # type: ignore[union-attr]
    filters = FilterState()
    await state.update_data(filters=filters.to_dict(), page=0, selected_ids=[])
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"🔍 <b>Фильтры поиска</b>\n\n{filters.describe()}",
        parse_mode="HTML",
        reply_markup=get_filter_menu_keyboard(filters, mode),
    )
    await callback.answer("Фильтры сброшены")


@router.callback_query(F.data == "f:close")
async def filter_close(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Меню фильтров закрыто.")  # type: ignore[union-attr]
    await callback.answer()


# ------------------------------------------------------------------
# Apply filters → show results
# ------------------------------------------------------------------

@router.callback_query(FilterStates.active, F.data.startswith("f:apply:"))
async def apply_filters(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    mode = callback.data.split(":")[2]  # type: ignore[union-attr]
    await _show_results(callback, state, db, mode, page=0)
    await callback.answer()


async def _show_results(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    mode: str,
    page: int,
) -> None:
    data = await state.get_data()
    filters = FilterState.from_dict(data.get("filters", {}))
    selected_ids: Set[int] = set(data.get("selected_ids", []))
    offset = page * CONTROLLERS_PER_PAGE

    controllers, total = await db.search_controllers(
        **filters_to_search_kwargs(filters),
        limit=CONTROLLERS_PER_PAGE,
        offset=offset,
    )

    await state.update_data(page=page, mode=mode)

    if not controllers:
        text = "🔍 <b>Результаты поиска</b>\n\nКонтролеры не найдены."
    else:
        lines = [f"🔍 <b>Результаты поиска</b> ({total} контролеров)\n"]
        for i, c in enumerate(controllers, start=offset + 1):
            lines.append(f"<b>{i}.</b> {format_controller_card(c, short=True)}\n")
        text = "\n".join(lines)

    kb = get_controller_list_keyboard(controllers, page, total, mode, selected_ids)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)  # type: ignore[union-attr]


# ------------------------------------------------------------------
# Pagination
# ------------------------------------------------------------------

@router.callback_query(FilterStates.active, F.data.startswith("b:pg:"))
async def browse_page(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    page = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    await _show_results(callback, state, db, "browse", page)
    await callback.answer()


@router.callback_query(FilterStates.active, F.data.startswith("i:pg:"))
async def invite_page(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    page = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    await _show_results(callback, state, db, "invite", page)
    await callback.answer()


# ------------------------------------------------------------------
# Browse-mode: view controller card
# ------------------------------------------------------------------

@router.callback_query(FilterStates.active, F.data.startswith("b:v:"))
async def browse_view_card(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    cid = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    ctrl = await db.get_controller_by_id(cid)
    if not ctrl:
        await callback.answer("Контролер не найден")
        return
    text = format_controller_card(ctrl, short=False)
    await callback.message.edit_text(  # type: ignore[union-attr]
        text, parse_mode="HTML",
        reply_markup=get_controller_card_keyboard(cid, "browse"),
    )
    await callback.answer()


@router.callback_query(FilterStates.active, F.data.startswith("b:edit:"))
async def browse_edit_card(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    cid = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    ctrl = await db.get_controller_by_id(cid)
    if not ctrl:
        await callback.answer("КРС не найден", show_alert=True)
        return

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✏️ <b>Редактирование анкеты КРС: {ctrl.get('name', '—')}</b>\n"
        "Выберите поле для изменения:",
        parse_mode="HTML",
        reply_markup=get_controller_edit_fields_keyboard(cid),
    )
    await callback.answer()


@router.callback_query(FilterStates.active, F.data.startswith("b:ef:"))
async def browse_edit_field(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")  # type: ignore[union-attr]
    field = parts[2]
    cid = int(parts[3])
    ctrl = await db.get_controller_by_id(cid)
    if not ctrl:
        await callback.answer("КРС не найден", show_alert=True)
        return

    if field == "is_active":
        new_value = 0 if ctrl.get("is_active", 1) else 1
        await db.update_controller(cid, is_active=new_value)
        updated = await db.get_controller_by_id(cid)
        await callback.message.edit_text(  # type: ignore[union-attr]
            format_controller_card(updated or ctrl, short=False),
            parse_mode="HTML",
            reply_markup=get_controller_card_keyboard(cid, "browse"),
        )
        await callback.answer("Статус активности обновлен")
        return

    prompts = {
        "name": "Введите новое полное ФИО (пример: Иванов Иван Иванович):",
        "birth_date": "Введите новую дату рождения (ДД.ММ.ГГГГ):",
        "phone": "Введите новый номер телефона (+79201234567):",
        "username": "Введите username в формате @username или - для очистки:",
        "location": "Введите новую локацию:",
        "rating": "Введите новый рейтинг от 0 до 5 (например 4.6):",
    }
    if field not in prompts:
        await callback.answer("Поле не поддерживается", show_alert=True)
        return

    await state.set_state(ControllerEditStates.entering_value)
    await state.update_data(edit_controller_id=cid, edit_field=field)
    await callback.message.answer(prompts[field])
    await callback.answer()


@router.message(ControllerEditStates.entering_value)
async def process_edit_field(message: Message, state: FSMContext, db: Database) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ У вас нет доступа.")
        return

    data = await state.get_data()
    cid = data.get("edit_controller_id")
    field = data.get("edit_field")
    if not cid or not field:
        await state.clear()
        await message.answer("Ошибка редактирования.")
        return

    raw = (message.text or "").strip()
    update_value: Any
    if field == "name":
        validated = validate_full_name(raw)
        if not validated:
            await message.answer("⚠️ Укажите полное ФИО без инициалов.")
            return
        update_value = validated
    elif field == "birth_date":
        validated = validate_birth_date(raw)
        if not validated:
            await message.answer("⚠️ Неверная дата. Формат ДД.ММ.ГГГГ, возраст 18-80.")
            return
        update_value = validated
    elif field == "phone":
        validated = validate_phone_ru(raw)
        if not validated:
            await message.answer("⚠️ Неверный формат телефона. Пример: +79201234567")
            return
        update_value = validated
    elif field == "username":
        if raw == "-":
            update_value = None
        else:
            if not raw.startswith("@") or len(raw) < 3:
                await message.answer("⚠️ Неверный username. Пример: @username или -")
                return
            update_value = raw[1:]
    elif field == "location":
        if len(raw) < 2:
            await message.answer("⚠️ Локация слишком короткая.")
            return
        update_value = raw
    elif field == "rating":
        try:
            rating = float(raw)
        except ValueError:
            await message.answer("⚠️ Рейтинг должен быть числом от 0 до 5.")
            return
        if not 0 <= rating <= 5:
            await message.answer("⚠️ Рейтинг должен быть от 0 до 5.")
            return
        update_value = rating
    else:
        await state.clear()
        await message.answer("Поле не поддерживается.")
        return

    await db.update_controller(cid, **{field: update_value})
    ctrl = await db.get_controller_by_id(cid)
    await state.set_state(FilterStates.active)
    await message.answer(
        "✅ Поле обновлено.\n\n" + format_controller_card(ctrl or {}, short=False),
        parse_mode="HTML",
        reply_markup=get_controller_card_keyboard(cid, "browse"),
    )


@router.callback_query(FilterStates.active, F.data.startswith("i:v:"))
async def invite_view_card(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    cid = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    ctrl = await db.get_controller_by_id(cid)
    if not ctrl:
        await callback.answer("Контролер не найден")
        return
    text = format_controller_card(ctrl, short=False)
    await callback.message.edit_text(  # type: ignore[union-attr]
        text, parse_mode="HTML",
        reply_markup=get_controller_card_keyboard(cid, "invite"),
    )
    await callback.answer()


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------

@router.callback_query(FilterStates.active, F.data.startswith("b:h:"))
@router.callback_query(FilterStates.active, F.data.startswith("i:h:"))
async def view_history(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")  # type: ignore[union-attr]
    mode_short = parts[0]
    cid = int(parts[2])
    mode = "browse" if mode_short == "b" else "invite"

    ctrl = await db.get_controller_by_id(cid)
    if not ctrl:
        await callback.answer("Контролер не найден")
        return

    history = await db.get_controller_history(cid)
    if not history:
        text = f"📜 <b>История работы: {ctrl['name']}</b>\n\nИстория пуста."
    else:
        lines = [f"📜 <b>История работы: {ctrl['name']}</b>\n"]
        for entry in history:
            lines.append(format_history_entry(entry))
        text = "\n\n".join(lines)

    await callback.message.edit_text(  # type: ignore[union-attr]
        text, parse_mode="HTML",
        reply_markup=get_history_back_keyboard(cid, mode),
    )
    await callback.answer()


# ------------------------------------------------------------------
# Back to list from card
# ------------------------------------------------------------------

@router.callback_query(FilterStates.active, F.data == "b:list")
async def browse_back_to_list(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    page = data.get("page", 0)
    await _show_results(callback, state, db, "browse", page)
    await callback.answer()


@router.callback_query(FilterStates.active, F.data == "i:list")
async def invite_back_to_list(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    page = data.get("page", 0)
    await _show_results(callback, state, db, "invite", page)
    await callback.answer()


# ------------------------------------------------------------------
# Invite-mode: select / select-all / random
# ------------------------------------------------------------------

@router.callback_query(FilterStates.active, F.data.startswith("i:s:"))
async def toggle_select(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    cid = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    data = await state.get_data()
    selected: list = data.get("selected_ids", [])
    if cid in selected:
        selected.remove(cid)
    else:
        selected.append(cid)
    await state.update_data(selected_ids=selected)
    page = data.get("page", 0)
    await _show_results(callback, state, db, "invite", page)
    await callback.answer()


@router.callback_query(FilterStates.active, F.data == "i:all")
async def select_all(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    """Select all controllers matching current filters."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    filters = FilterState.from_dict(data.get("filters", {}))
    all_ids = await db.get_controller_ids(**filters_to_search_kwargs(filters))
    await state.update_data(selected_ids=all_ids)
    page = data.get("page", 0)
    await _show_results(callback, state, db, "invite", page)
    await callback.answer(f"Выбрано: {len(all_ids)}")


@router.callback_query(FilterStates.active, F.data == "i:rnd")
async def random_select_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    """Ask admin how many random controllers to select."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    from .states import InviteStates
    await state.set_state(InviteStates.entering_random_count)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "🎲 Введите количество случайных контролеров для выбора:"
    )
    await callback.answer()
