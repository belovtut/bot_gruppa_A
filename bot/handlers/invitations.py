"""Invitation-flow handlers: event creation, preview, sending invitations."""
import logging
import random

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import Database
from bot.services.controller_filters import filters_to_search_kwargs
from bot.services.invitations import InvitationFlowService
from bot.keyboards import (
    get_admin_keyboard,
    get_confirm_invite_keyboard,
    get_controller_list_keyboard,
    get_required_field_keyboard,
    get_skip_keyboard,
)
from database.models import CONTROLLERS_PER_PAGE, FilterState
from bot.utils import format_controller_card, format_event_card, validate_date, validate_time
from .states import FilterStates, InviteStates

logger = logging.getLogger(__name__)
router = Router(name="invitations")


# ------------------------------------------------------------------
# Random count input (from controller_db → InviteStates.entering_random_count)
# ------------------------------------------------------------------

@router.message(InviteStates.entering_random_count)
async def enter_random_count(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) < 1:
        await message.answer("⚠️ Введите положительное число:")
        return

    n = int(text)
    data = await state.get_data()
    filters = FilterState.from_dict(data.get("filters", {}))

    all_ids = await db.get_controller_ids(**filters_to_search_kwargs(filters))
    total = len(all_ids)
    selected = random.sample(all_ids, min(n, total))
    await state.update_data(selected_ids=selected, page=0)
    await state.set_state(FilterStates.active)

    # Re-render results list
    page_ctrls, _ = await db.search_controllers(
        **filters_to_search_kwargs(filters),
        limit=CONTROLLERS_PER_PAGE,
        offset=0,
    )
    lines = [f"🔍 <b>Результаты поиска</b> ({total} контролеров)\n"]
    for i, c in enumerate(page_ctrls, start=1):
        lines.append(f"<b>{i}.</b> {format_controller_card(c, short=True)}\n")
    text_msg = "\n".join(lines) if page_ctrls else "Контролеры не найдены."

    kb = get_controller_list_keyboard(page_ctrls, 0, total, "invite", set(selected))
    await message.answer(
        text_msg, parse_mode="HTML", reply_markup=kb,
    )


# ------------------------------------------------------------------
# i:send → Start event-creation FSM
# ------------------------------------------------------------------

@router.callback_query(FilterStates.active, F.data == "i:send")
async def start_event_creation(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected: list = data.get("selected_ids", [])
    if not selected:
        await callback.answer("Сначала выберите хотя бы одного контролера!", show_alert=True)
        return

    await state.set_state(InviteStates.entering_title)
    await state.update_data(event={})
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"📝 <b>Создание приглашения</b> (для {len(selected)} контролеров)\n\n"
        "Шаг 1/7: Введите название мероприятия:",
        parse_mode="HTML",
        reply_markup=get_required_field_keyboard(),
    )
    await callback.answer()


# ------------------------------------------------------------------
# Event creation steps
# ------------------------------------------------------------------

@router.callback_query(InviteStates.entering_title, F.data == "inv:cancel")
@router.callback_query(InviteStates.entering_date, F.data == "inv:cancel")
@router.callback_query(InviteStates.entering_time, F.data == "inv:cancel")
@router.callback_query(InviteStates.entering_location, F.data == "inv:cancel")
@router.callback_query(InviteStates.entering_rate, F.data == "inv:cancel")
@router.callback_query(InviteStates.entering_dress_code, F.data == "inv:cancel")
@router.callback_query(InviteStates.entering_task, F.data == "inv:cancel")
@router.callback_query(InviteStates.confirming, F.data == "inv:cancel")
async def cancel_event_creation(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Создание приглашения отменено.")  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "Возврат в панель администратора.", reply_markup=get_admin_keyboard(),
    )
    await callback.answer()


_MAX_FIELD_LEN = 300

# Step 1: Title
@router.message(InviteStates.entering_title)
async def enter_title(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("⚠️ Название слишком короткое.")
        return
    if len(text) > _MAX_FIELD_LEN:
        await message.answer(f"⚠️ Название слишком длинное (максимум {_MAX_FIELD_LEN} символов).")
        return
    data = await state.get_data()
    event = data.get("event", {})
    event["title"] = text
    await state.update_data(event=event)
    await state.set_state(InviteStates.entering_date)
    await message.answer(
        "Шаг 2/7: Введите дату мероприятия (ДД.ММ.ГГГГ):",
        reply_markup=get_required_field_keyboard(),
    )


# Step 2: Date
@router.message(InviteStates.entering_date)
async def enter_date(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    parsed = validate_date(text)
    if not parsed:
        await message.answer("⚠️ Неверный формат. Введите дату ДД.ММ.ГГГГ:")
        return
    data = await state.get_data()
    event = data.get("event", {})
    event["event_date"] = parsed
    await state.update_data(event=event)
    await state.set_state(InviteStates.entering_time)
    await message.answer(
        "Шаг 3/7: Введите время (ЧЧ:ММ):",
        reply_markup=get_skip_keyboard(),
    )


# Step 3: Time (optional)
@router.callback_query(InviteStates.entering_time, F.data == "inv:skip")
async def skip_time(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(InviteStates.entering_location)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Шаг 4/7: Введите место проведения (локацию):",
        reply_markup=get_required_field_keyboard(),
    )
    await callback.answer()


@router.message(InviteStates.entering_time)
async def enter_time(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    parsed = validate_time(text)
    if not parsed:
        await message.answer("⚠️ Неверный формат. Введите время ЧЧ:ММ:")
        return
    data = await state.get_data()
    event = data.get("event", {})
    event["event_time"] = parsed
    await state.update_data(event=event)
    await state.set_state(InviteStates.entering_location)
    await message.answer(
        "Шаг 4/7: Введите место проведения (локацию):",
        reply_markup=get_required_field_keyboard(),
    )


# Step 4: Location
@router.message(InviteStates.entering_location)
async def enter_location(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("⚠️ Локация слишком короткая.")
        return
    if len(text) > _MAX_FIELD_LEN:
        await message.answer(f"⚠️ Локация слишком длинная (максимум {_MAX_FIELD_LEN} символов).")
        return
    data = await state.get_data()
    event = data.get("event", {})
    event["location"] = text
    await state.update_data(event=event)
    await state.set_state(InviteStates.entering_rate)
    await message.answer(
        "Шаг 5/7: Введите ставку оплаты (например, «5000₽»):",
        reply_markup=get_skip_keyboard(),
    )


# Step 5: Rate (optional)
@router.callback_query(InviteStates.entering_rate, F.data == "inv:skip")
async def skip_rate(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(InviteStates.entering_dress_code)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Шаг 6/7: Введите требования к дресс-коду:",
        reply_markup=get_skip_keyboard(),
    )
    await callback.answer()


@router.message(InviteStates.entering_rate)
async def enter_rate(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) > _MAX_FIELD_LEN:
        await message.answer(f"⚠️ Ставка слишком длинная (максимум {_MAX_FIELD_LEN} символов).")
        return
    data = await state.get_data()
    event = data.get("event", {})
    event["rate"] = text
    await state.update_data(event=event)
    await state.set_state(InviteStates.entering_dress_code)
    await message.answer(
        "Шаг 6/7: Введите требования к дресс-коду:",
        reply_markup=get_skip_keyboard(),
    )


# Step 6: Dress code (optional)
@router.callback_query(InviteStates.entering_dress_code, F.data == "inv:skip")
async def skip_dress_code(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(InviteStates.entering_task)
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Шаг 7/7: Опишите задачу (описание работы):",
        reply_markup=get_skip_keyboard(),
    )
    await callback.answer()


@router.message(InviteStates.entering_dress_code)
async def enter_dress_code(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) > _MAX_FIELD_LEN:
        await message.answer(f"⚠️ Описание дресс-кода слишком длинное (максимум {_MAX_FIELD_LEN} символов).")
        return
    data = await state.get_data()
    event = data.get("event", {})
    event["dress_code"] = text
    await state.update_data(event=event)
    await state.set_state(InviteStates.entering_task)
    await message.answer(
        "Шаг 7/7: Опишите задачу (описание работы):",
        reply_markup=get_skip_keyboard(),
    )


# Step 7: Task description (optional)
@router.callback_query(InviteStates.entering_task, F.data == "inv:skip")
async def skip_task(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_preview(callback, state)
    await callback.answer()


@router.message(InviteStates.entering_task)
async def enter_task(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) > _MAX_FIELD_LEN:
        await message.answer(f"⚠️ Описание задачи слишком длинное (максимум {_MAX_FIELD_LEN} символов).")
        return
    data = await state.get_data()
    event = data.get("event", {})
    event["task_description"] = text
    await state.update_data(event=event)
    await _show_preview_msg(message, state)


async def _show_preview(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    event = data.get("event", {})
    selected = data.get("selected_ids", [])
    await state.set_state(InviteStates.confirming)

    text = (
        "📋 <b>Предпросмотр приглашения:</b>\n\n"
        f"{format_event_card(event)}\n\n"
        f"📨 Будет отправлено: <b>{len(selected)}</b> контролерам"
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        text, parse_mode="HTML", reply_markup=get_confirm_invite_keyboard(),
    )


async def _show_preview_msg(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    event = data.get("event", {})
    selected = data.get("selected_ids", [])
    await state.set_state(InviteStates.confirming)

    text = (
        "📋 <b>Предпросмотр приглашения:</b>\n\n"
        f"{format_event_card(event)}\n\n"
        f"📨 Будет отправлено: <b>{len(selected)}</b> контролерам"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_confirm_invite_keyboard())


# ------------------------------------------------------------------
# Confirm and send
# ------------------------------------------------------------------

@router.callback_query(InviteStates.confirming, F.data == "inv:confirm")
async def confirm_and_send(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    event_data = data.get("event", {})
    selected_ids: list = data.get("selected_ids", [])
    admin_user = callback.from_user
    admin_id = admin_user.id
    
    # Ensure the admin is in the users table to satisfy FOREIGN KEY(created_by)
    await db.add_user(
        user_id=admin_id,
        username=admin_user.username,
        first_name=admin_user.first_name,
        last_name=admin_user.last_name,
    )
    
    await state.clear()
    await callback.answer()  # Answer immediately to avoid timeout

    status_msg = await callback.message.edit_text(  # type: ignore[union-attr]
        f"📤 Отправка приглашений ({len(selected_ids)} контролеров)..."
    )

    flow = InvitationFlowService(db)
    result = await flow.create_event_and_deliver(
        callback.bot,
        event_data=event_data,
        selected_controller_ids=list(selected_ids),
        created_by=admin_id,
    )

    event = await db.get_event(result.event_id)
    if not event:
        await status_msg.edit_text("❌ Ошибка создания мероприятия.")
        return

    summary = (
        f"✅ <b>Приглашения отправлены!</b>\n\n"
        f"✓ Успешно: {result.success}\n"
        f"✗ Не доставлено: {result.failed}"
    )
    if result.skipped_no_telegram:
        summary += f"\n⚠️ Без Telegram ID: {result.skipped_no_telegram}"

    await status_msg.edit_text(summary, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "Возврат в панель администратора.", reply_markup=get_admin_keyboard(),
    )
