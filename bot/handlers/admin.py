"""Admin-panel handlers: /admin, broadcast, stats, add controller."""
import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import SETTINGS
from bot.deps import is_admin
from database import Database
from bot.services.broadcast import run_broadcast_copy
from bot.services.staff import (
    format_dialog_history,
    format_staff_application_card,
    send_admin_reply_to_candidate,
)
from bot.keyboards import (
    get_admin_keyboard,
    get_candidate_application_reply_keyboard,
    get_cancel_keyboard,
    get_profile_areas_keyboard,
    get_profile_confirm_keyboard,
    get_staff_application_actions_keyboard,
    get_staff_applications_keyboard,
    get_profile_experience_keyboard,
    get_profile_languages_keyboard,
    get_profile_specializations_keyboard,
    get_staff_dialog_keyboard,
)
from database.models import ExperienceType, Language, Specialization, WorkArea
from bot.utils import (
    age_from_birth_date,
    birth_date_to_display,
    format_enum_list,
    validate_birth_date,
    validate_full_name,
    validate_phone_ru,
)
from .states import AddControllerStates, BroadcastStates, StaffApplicationAdminStates

logger = logging.getLogger(__name__)
router = Router(name="admin")


# ------------------------------------------------------------------
# /admin
# ------------------------------------------------------------------

@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к административной панели.")
        return
    await message.answer("🔐 Панель администратора", reply_markup=get_admin_keyboard())


# ------------------------------------------------------------------
# Broadcast
# ------------------------------------------------------------------

@router.message(F.text == "📨 Рассылка всем")
async def start_broadcast(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой функции.")
        return
    await state.set_state(BroadcastStates.waiting_for_message)
    await message.answer(
        "📝 Отправьте сообщение для рассылки всем пользователям бота.\n"
        "Поддерживаются текст, фото, видео и другие типы сообщений.\n\n"
        "Для отмены отправьте /cancel",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(BroadcastStates.waiting_for_message, Command("cancel"))
@router.message(BroadcastStates.waiting_for_message, F.text == "❌ Отмена")
async def cancel_broadcast(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ Рассылка отменена.", reply_markup=get_admin_keyboard())


@router.message(BroadcastStates.waiting_for_message)
async def process_broadcast(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    user_ids = await db.get_all_user_ids()

    status_msg = await message.answer(
        f"📤 Начинаю рассылку для {len(user_ids)} пользователей..."
    )

    result = await run_broadcast_copy(
        message, db, delay_seconds=SETTINGS.broadcast_delay
    )

    await status_msg.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"✓ Успешно: {result.success}\n✗ Не доставлено: {result.failed}"
    )
    await message.answer("Возврат в панель администратора.", reply_markup=get_admin_keyboard())


# ------------------------------------------------------------------
# Statistics
# ------------------------------------------------------------------

@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message, db: Database) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return
    user_count = await db.get_user_count()
    ctrl_count = await db.get_controller_count()
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей бота: {user_count}\n"
        f"🛂 Контролеров в базе: {ctrl_count}",
        parse_mode="HTML",
    )


# ------------------------------------------------------------------
# Staff applications
# ------------------------------------------------------------------


@router.message(F.text == "📥 Заявки в штат")
async def show_staff_applications(message: Message, db: Database) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return

    apps = await db.list_staff_applications()
    await message.answer(
        "📥 <b>Заявки в штат</b>",
        parse_mode="HTML",
        reply_markup=get_staff_applications_keyboard(apps),
    )


@router.callback_query(F.data == "sa:list")
async def show_staff_applications_list(callback: CallbackQuery, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    apps = await db.list_staff_applications()
    await callback.message.edit_text(  # type: ignore[union-attr]
        "📥 <b>Заявки в штат</b>",
        parse_mode="HTML",
        reply_markup=get_staff_applications_keyboard(apps),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sa:view:"))
async def view_staff_application(callback: CallbackQuery, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    app_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    app = await db.get_staff_application(app_id)
    if not app:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    messages = await db.get_staff_application_messages(app_id, limit=5)
    text = format_staff_application_card(app, messages)
    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        parse_mode="HTML",
        reply_markup=get_staff_application_actions_keyboard(app_id, app["user_id"], app.get("username")),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sa:del:"))
async def delete_staff_application(callback: CallbackQuery, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    app_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    app = await db.get_staff_application(app_id)
    if not app:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    await db.set_staff_application_status(app_id, "deleted")
    try:
        await callback.bot.send_message(
            chat_id=app["user_id"],
            text=(
                "ℹ️ Ваша заявка закрыта.\n"
                "При необходимости вы можете отправить новую анкету позже."
            ),
        )
    except Exception as exc:
        logger.warning("Failed to notify candidate %s about deleted app %s: %s", app["user_id"], app_id, exc)

    apps = await db.list_staff_applications()
    await callback.message.edit_text(  # type: ignore[union-attr]
        "🗑 Заявка удалена.\n\n📥 <b>Заявки в штат</b>",
        parse_mode="HTML",
        reply_markup=get_staff_applications_keyboard(apps),
    )
    await callback.answer("Заявка удалена")


@router.callback_query(F.data.startswith("sa:msg:"))
async def admin_start_message(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    app_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    app = await db.get_staff_application(app_id)
    if not app:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    messages = await db.get_staff_application_messages(app_id, limit=20)
    history = format_dialog_history(messages)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"💬 <b>История диалога с кандидатом</b>\n\n{history}",
        parse_mode="HTML",
        reply_markup=get_staff_dialog_keyboard(app_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sa:thread:"))
async def show_staff_thread(callback: CallbackQuery, db: Database) -> None:
    # Backward-compatible alias for old button callback.
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    app_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    app = await db.get_staff_application(app_id)
    if not app:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    messages = await db.get_staff_application_messages(app_id, limit=20)
    history = format_dialog_history(messages)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"💬 <b>История диалога с кандидатом</b>\n\n{history}",
        parse_mode="HTML",
        reply_markup=get_staff_dialog_keyboard(app_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sa:compose:"))
async def compose_staff_message(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    app_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    app = await db.get_staff_application(app_id)
    if not app:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    await state.set_state(StaffApplicationAdminStates.entering_message)
    await state.update_data(admin_reply_app_id=app_id)
    await callback.message.answer(
        "Введите сообщение кандидату:",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sa:approve:"))
async def approve_staff_application(callback: CallbackQuery, db: Database) -> None:
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    app_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    app = await db.get_staff_application(app_id)
    if not app:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    ctrl_id = await db.approve_staff_application(app_id)
    if ctrl_id is None:
        await callback.answer("Не удалось одобрить заявку.", show_alert=True)
        return

    try:
        await callback.bot.send_message(
            chat_id=app["user_id"],
            text=(
                "✅ Ваша заявка одобрена.\n"
                "Вы добавлены в базу КРС и будете получать приглашения на мероприятия."
            ),
        )
    except Exception as exc:
        logger.warning("Failed to notify candidate %s about approval: %s", app.get("user_id"), exc)

    apps = await db.list_staff_applications()
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Заявка #{app_id} одобрена и добавлена в базу КРС (ID анкеты: {ctrl_id}).\n\n"
        "📥 <b>Заявки в штат</b>",
        parse_mode="HTML",
        reply_markup=get_staff_applications_keyboard(apps),
    )
    await callback.answer("Заявка одобрена")


@router.message(StaffApplicationAdminStates.entering_message, F.text == "❌ Отмена")
async def cancel_staff_message(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отправка сообщения отменена.", reply_markup=get_admin_keyboard())


@router.message(StaffApplicationAdminStates.entering_message)
async def admin_send_staff_message(message: Message, state: FSMContext, db: Database) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ У вас нет доступа.")
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Сообщение не может быть пустым.")
        return

    data = await state.get_data()
    app_id = data.get("admin_reply_app_id")
    if not app_id:
        await state.clear()
        await message.answer("Ошибка: заявка не найдена.", reply_markup=get_admin_keyboard())
        return

    app = await db.get_staff_application(app_id)
    if not app:
        await state.clear()
        await message.answer("Заявка не найдена.", reply_markup=get_admin_keyboard())
        return

    await db.add_staff_application_message(
        application_id=app_id,
        sender_id=message.from_user.id,  # type: ignore[union-attr]
        sender_role="admin",
        message_text=text,
    )
    history = await db.get_staff_application_messages(app_id, limit=20)
    await state.clear()
    thread_text = format_dialog_history(history)

    delivered = await send_admin_reply_to_candidate(
        message.bot,
        candidate_chat_id=app["user_id"],
        text=text,
        thread_text=thread_text,
        reply_markup=get_candidate_application_reply_keyboard(app_id),
    )
    if not delivered:
        await message.answer("Сообщение не доставлено кандидату.", reply_markup=get_admin_keyboard())
        return

    await message.answer(
        "✅ Сообщение отправлено кандидату.",
        reply_markup=get_admin_keyboard(),
    )


# ------------------------------------------------------------------
# Add controller (admin FSM)
# ------------------------------------------------------------------

@router.message(F.text == "➕ Добавить контролера")
async def add_controller_start(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return
    await state.set_state(AddControllerStates.entering_username)
    await state.update_data(specs=[], exps=[], areas=[], langs=[])
    await message.answer(
        "➕ <b>Добавление контролера</b>\n\n"
        "Введите username кандидата (например @username) или /skip, если неизвестен:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(AddControllerStates.entering_username, F.text == "❌ Отмена")
@router.message(AddControllerStates.entering_name, F.text == "❌ Отмена")
@router.message(AddControllerStates.entering_birth_date, F.text == "❌ Отмена")
@router.message(AddControllerStates.entering_phone, F.text == "❌ Отмена")
@router.message(AddControllerStates.entering_location, F.text == "❌ Отмена")
@router.message(AddControllerStates.entering_rating, F.text == "❌ Отмена")
@router.message(AddControllerStates.choosing_specializations, F.text == "❌ Отмена")
@router.message(AddControllerStates.choosing_experience, F.text == "❌ Отмена")
@router.message(AddControllerStates.choosing_areas, F.text == "❌ Отмена")
@router.message(AddControllerStates.choosing_languages, F.text == "❌ Отмена")
async def cancel_add_controller(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ Добавление отменено.", reply_markup=get_admin_keyboard())


@router.message(AddControllerStates.entering_username)
async def add_ctrl_username(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    username = None
    if text != "/skip":
        if not text.startswith("@") or len(text) < 3:
            await message.answer("⚠️ Введите username в формате @username или /skip")
            return
        username = text[1:]
    await state.update_data(username=username)
    await state.set_state(AddControllerStates.entering_name)
    await message.answer("Введите полное ФИО кандидата:")


@router.message(AddControllerStates.entering_name)
async def add_ctrl_name(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    full_name = validate_full_name(text)
    if not full_name:
        await message.answer("⚠️ Введите полное ФИО без инициалов (пример: Иванов Иван Иванович)")
        return
    await state.update_data(name=full_name)
    await state.set_state(AddControllerStates.entering_birth_date)
    await message.answer("Введите дату рождения (ДД.ММ.ГГГГ):")


@router.message(AddControllerStates.entering_birth_date)
async def add_ctrl_birth_date(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    birth_date = validate_birth_date(text)
    if not birth_date:
        await message.answer(
            "⚠️ Неверная дата рождения. Используйте формат ДД.ММ.ГГГГ (возраст 18-80)."
        )
        return
    await state.update_data(birth_date=birth_date)
    await state.set_state(AddControllerStates.entering_phone)
    await message.answer("Введите номер телефона в формате +79201234567:")


@router.message(AddControllerStates.entering_phone)
async def add_ctrl_phone(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    phone = validate_phone_ru(text)
    if not phone:
        await message.answer("⚠️ Неверный формат номера. Пример: +79201234567")
        return
    await state.update_data(phone=phone)
    await state.set_state(AddControllerStates.choosing_specializations)
    data = await state.get_data()
    await message.answer(
        "Выберите специализации контролера:",
        reply_markup=get_profile_specializations_keyboard(data.get("specs", [])),
    )


@router.callback_query(AddControllerStates.choosing_specializations, F.data.startswith("pr:s:"))
async def add_ctrl_spec_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    val = callback.data.split(":")[2]  # type: ignore[union-attr]
    if val == "done":
        await state.set_state(AddControllerStates.choosing_experience)
        data = await state.get_data()
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Выберите типы мероприятий (опыт):",
            reply_markup=get_profile_experience_keyboard(data.get("exps", [])),
        )
        await callback.answer()
        return
    data = await state.get_data()
    specs: list = data.get("specs", [])
    if val in specs:
        specs.remove(val)
    else:
        specs.append(val)
    await state.update_data(specs=specs)
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_profile_specializations_keyboard(specs),
    )
    await callback.answer()


@router.callback_query(AddControllerStates.choosing_experience, F.data.startswith("pr:e:"))
async def add_ctrl_exp_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    val = callback.data.split(":")[2]  # type: ignore[union-attr]
    if val == "done":
        await state.set_state(AddControllerStates.entering_location)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Введите локацию (район/город):"
        )
        await callback.answer()
        return
    data = await state.get_data()
    exps: list = data.get("exps", [])
    if val in exps:
        exps.remove(val)
    else:
        exps.append(val)
    await state.update_data(exps=exps)
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_profile_experience_keyboard(exps),
    )
    await callback.answer()


@router.message(AddControllerStates.entering_location)
async def add_ctrl_location(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("⚠️ Локация слишком короткая. Укажите район/город.")
        return
    await state.update_data(location=text)
    await state.set_state(AddControllerStates.choosing_areas)
    data = await state.get_data()
    await message.answer(
        "Выберите предпочтительные районы работы:",
        reply_markup=get_profile_areas_keyboard(data.get("areas", [])),
    )


@router.callback_query(AddControllerStates.choosing_areas, F.data.startswith("pr:area:"))
async def add_ctrl_area_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    val = callback.data.split(":")[2]  # type: ignore[union-attr]
    if val == "done":
        await state.set_state(AddControllerStates.choosing_languages)
        data = await state.get_data()
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Выберите языки:",
            reply_markup=get_profile_languages_keyboard(data.get("langs", [])),
        )
        await callback.answer()
        return
    data = await state.get_data()
    areas: list = data.get("areas", [])
    if val in areas:
        areas.remove(val)
    else:
        areas.append(val)
    await state.update_data(areas=areas)
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_profile_areas_keyboard(areas),
    )
    await callback.answer()


@router.callback_query(AddControllerStates.choosing_languages, F.data.startswith("pr:l:"))
async def add_ctrl_lang_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    val = callback.data.split(":")[2]  # type: ignore[union-attr]
    if val == "done":
        await state.set_state(AddControllerStates.entering_rating)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Введите рейтинг (от 0 до 5, например 4.5) или /skip:"
        )
        await callback.answer()
        return
    data = await state.get_data()
    langs: list = data.get("langs", [])
    if val in langs:
        langs.remove(val)
    else:
        langs.append(val)
    await state.update_data(langs=langs)
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_profile_languages_keyboard(langs),
    )
    await callback.answer()


@router.message(AddControllerStates.entering_rating)
async def add_ctrl_rating(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        rating = float(text)
        if not 0 <= rating <= 5:
            await message.answer("⚠️ Рейтинг должен быть от 0 до 5:")
            return
    except ValueError:
        await message.answer("⚠️ Введите число от 0 до 5, например 4.5")
        return
    await state.update_data(rating=rating)
    await state.set_state(AddControllerStates.confirming)

    data = await state.get_data()
    birth_disp = birth_date_to_display(data.get("birth_date"))
    age = age_from_birth_date(data.get("birth_date"))
    age_str = f" ({age} лет)" if age is not None else ""
    summary = (
        "📋 <b>Данные контролера:</b>\n\n"
        f"👤 Username: @{data.get('username') or '—'}\n"
        f"👤 ФИО: {data['name']}\n"
        f"🎂 Дата рождения: {birth_disp}{age_str}\n"
        f"📱 Телефон: {data.get('phone') or '—'}\n"
        f"🎯 Специализации: {format_enum_list(data.get('specs', []), Specialization)}\n"
        f"🏢 Опыт: {format_enum_list(data.get('exps', []), ExperienceType)}\n"
        f"📍 Локация: {data.get('location') or '—'}\n"
        f"📍 Районы: {format_enum_list(data.get('areas', []), WorkArea)}\n"
        f"🌐 Языки: {format_enum_list(data.get('langs', []), Language)}\n"
        f"⭐ Рейтинг: {data.get('rating', 0.0)}"
    )
    await message.answer(summary, parse_mode="HTML", reply_markup=get_profile_confirm_keyboard())


@router.callback_query(AddControllerStates.confirming, F.data == "pr:confirm")
async def add_ctrl_confirm(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    await state.clear()

    username = data.get("username")
    # Telegram ID cannot be fetched by phone via Bot API.
    telegram_id = None
    await db.add_controller(
        telegram_id=telegram_id,
        username=username,
        name=data["name"],
        birth_date=data.get("birth_date"),
        phone=data.get("phone"),
        specializations=data.get("specs", []),
        experience_types=data.get("exps", []),
        rating=data.get("rating", 0.0),
        location=data.get("location"),
        preferred_areas=data.get("areas", []),
        languages=data.get("langs", []),
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ КРС <b>{data['name']}</b> успешно добавлен в базу.\n"
        "ℹ️ Telegram ID не указан. При необходимости его можно добавить при редактировании анкеты.",
        parse_mode="HTML",
    )
    await callback.message.answer(  # type: ignore[union-attr]
        "Возврат в панель администратора.", reply_markup=get_admin_keyboard()
    )
    await callback.answer()


@router.callback_query(AddControllerStates.confirming, F.data == "pr:cancel")
async def add_ctrl_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Добавление отменено.")  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "Возврат в панель администратора.", reply_markup=get_admin_keyboard()
    )
    await callback.answer()




