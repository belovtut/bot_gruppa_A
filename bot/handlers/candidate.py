"""Candidate-facing handlers: invitation responses, profile registration, profile view."""
import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import SETTINGS
from database import Database
from bot.services.candidate_invitations import CandidateInvitationService
from bot.services.notifications import notify_admins
from bot.services.staff import notify_admins_staff_reply
from database.models import DeclineReason, ExperienceType, InvitationStatus, Language, Specialization, WorkArea

from bot.keyboards import (
    get_admin_keyboard,
    get_cancel_keyboard,
    get_decline_reasons_keyboard,
    get_invitation_buttons,
    get_main_menu_keyboard,
    get_my_invitations_keyboard,
    get_profile_areas_keyboard,
    get_profile_confirm_keyboard,
    get_profile_experience_keyboard,
    get_profile_languages_keyboard,
    get_profile_specializations_keyboard,
    get_staff_application_actions_keyboard,
)
from bot.utils import (
    age_from_birth_date,
    birth_date_to_display,
    format_controller_card,
    format_enum_list,
    format_event_card,
    format_db_timestamp_msk,
    validate_birth_date,
    validate_full_name,
    validate_phone_ru,
)
from .states import (
    DeclineCommentStates,
    ProfileStates,
    StaffApplicationCandidateStates,
)

logger = logging.getLogger(__name__)
router = Router(name="candidate")


# ======================================================================
# Universal /cancel for all candidate FSM states
# ======================================================================

@router.message(StateFilter(ProfileStates), Command("cancel"))
async def cancel_registration_cmd(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    ctrl = await db.get_controller_by_telegram_id(message.from_user.id)  # type: ignore[union-attr]
    await message.answer(
        "❌ Регистрация отменена.",
        reply_markup=get_main_menu_keyboard(is_controller=ctrl is not None),
    )


@router.message(StateFilter(DeclineCommentStates), Command("cancel"))
async def cancel_decline_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отказ от приглашения отменён.")


@router.message(StateFilter(StaffApplicationCandidateStates), Command("cancel"))
async def cancel_candidate_reply_cmd(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    ctrl = await db.get_controller_by_telegram_id(message.from_user.id)  # type: ignore[union-attr]
    await message.answer(
        "Отправка сообщения отменена.",
        reply_markup=get_main_menu_keyboard(is_controller=ctrl is not None),
    )


# ======================================================================
# Invitation responses
# ======================================================================

@router.callback_query(F.data.startswith("ir:a:"))
async def accept_invitation(callback: CallbackQuery, db: Database) -> None:
    """Candidate accepts an invitation."""
    inv_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    svc = CandidateInvitationService(db)
    outcome = await svc.accept(inv_id)
    if outcome == "missing":
        await callback.answer("Приглашение не найдено.", show_alert=True)
        return
    if outcome == "closed":
        await callback.answer("Вы уже ответили на это приглашение.", show_alert=True)
        return

    details = outcome
    original = callback.message.html_text if callback.message else ""  # type: ignore[union-attr]
    await callback.message.edit_text(  # type: ignore[union-attr]
        original + "\n\n✅ <b>Вы приняли приглашение!</b>\n"
        "Статус: Предварительно одобрено.",
        parse_mode="HTML",
    )
    await callback.answer("Приглашение принято!")

    await notify_admins(
        callback.bot,
        (
            f"✅ <b>Приглашение принято!</b>\n\n"
            f"👤 {details.get('controller_name', '—')}\n"
            f"📌 {details.get('event_title', '—')} ({details.get('event_date', '')})"
        ),
    )


@router.callback_query(F.data.startswith("ir:d:"))
async def decline_invitation(callback: CallbackQuery) -> None:
    """Show decline reason selection."""
    inv_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Пожалуйста, укажите причину отказа:",
        reply_markup=get_decline_reasons_keyboard(inv_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ir:t:"))
async def think_invitation(callback: CallbackQuery, db: Database) -> None:
    """Candidate wants time to think."""
    inv_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    svc = CandidateInvitationService(db)
    outcome = await svc.mark_thinking(inv_id)
    if outcome == "missing":
        await callback.answer("Приглашение не найдено.", show_alert=True)
        return
    if outcome == "closed":
        await callback.answer("Вы уже ответили на это приглашение.", show_alert=True)
        return

    hours = SETTINGS.reminder_hours
    original = callback.message.html_text if callback.message else ""  # type: ignore[union-attr]
    await callback.message.edit_text(  # type: ignore[union-attr]
        original + f"\n\n🤔 <b>Вы взяли время на раздумье.</b>\n"
        f"Напомним вам через {hours} ч.",
        parse_mode="HTML",
    )
    await callback.answer()


# ------------------------------------------------------------------
# Decline reason callbacks
# ------------------------------------------------------------------

@router.callback_query(F.data.startswith("dr:"))
async def handle_decline_reason(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    inv_id = int(parts[1])
    reason_code = parts[2]

    inv = await db.get_invitation(inv_id)
    if not inv:
        await callback.answer("Приглашение не найдено.", show_alert=True)
        return

    if reason_code == DeclineReason.OTHER:
        # Ask for a free-text comment
        await state.set_state(DeclineCommentStates.entering_comment)
        await state.update_data(decline_inv_id=inv_id)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Опишите причину отказа:"
        )
        await callback.answer()
        return

    svc = CandidateInvitationService(db)
    label = svc.decline_reason_label(reason_code)
    outcome = await svc.decline_with_reason(inv_id, reason_code=reason_code)
    if outcome == "missing":
        await callback.answer("Приглашение не найдено.", show_alert=True)
        return
    if outcome == "closed":
        await callback.answer("Вы уже ответили на это приглашение.", show_alert=True)
        return
    details = outcome

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"❌ <b>Приглашение отклонено.</b>\nПричина: {label}",
        parse_mode="HTML",
    )
    await callback.answer("Приглашение отклонено.")

    await notify_admins(
        callback.bot,
        (
            f"❌ <b>Приглашение отклонено</b>\n\n"
            f"👤 {details.get('controller_name', '—')}\n"
            f"📌 {details.get('event_title', '—')}\n"
            f"Причина: {label}"
        ),
    )


@router.message(DeclineCommentStates.entering_comment)
async def enter_decline_comment(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    inv_id = data.get("decline_inv_id")
    await state.clear()

    if not inv_id:
        await message.answer("Ошибка: приглашение не найдено.")
        return

    comment = (message.text or "").strip()
    svc = CandidateInvitationService(db)
    outcome = await svc.decline_with_reason(
        inv_id,
        reason_code=DeclineReason.OTHER.value,
        decline_comment=comment,
    )
    if outcome in ("missing", "closed"):
        await message.answer("Ошибка: приглашение недоступно.")
        return
    details = outcome

    await message.answer(
        "❌ <b>Приглашение отклонено.</b>\nВаш комментарий сохранён.",
        parse_mode="HTML",
    )

    await notify_admins(
        message.bot,
        (
            f"❌ <b>Приглашение отклонено</b>\n\n"
            f"👤 {details.get('controller_name', '—')}\n"
            f"📌 {details.get('event_title', '—')}\n"
            f"Причина: Другая — {comment}"
        ),
    )


# ======================================================================
# Profile registration (self-registration)
# ======================================================================

@router.message(F.text == "✍️ Стать контролером")
@router.message(F.text == "✍️ Хочу стать КРС")
@router.message(Command("register"))
async def start_registration(message: Message, state: FSMContext, db: Database) -> None:
    user = message.from_user
    if not user:
        return

    existing_controller = await db.get_controller_by_telegram_id(user.id)
    if existing_controller:
        await message.answer(
            "Вы уже состоите в штате КРС.\n"
            "Используйте «👤 Мой профиль» для просмотра данных."
        )
        return

    existing = await db.get_active_staff_application_by_user(user.id)
    if existing:
        await message.answer(
            "Ваша заявка уже отправлена и находится в обработке.\n"
            "Мы свяжемся с вами после рассмотрения." 
        )
        return

    await state.set_state(ProfileStates.entering_name)
    await state.update_data(pr_specs=[], pr_exps=[], pr_areas=[], pr_langs=[])
    await message.answer(
        "👤 <b>Анкета кандидата в штат КРС</b>\n\n"
        "Шаг 1/7: Введите ваше полное ФИО (например: Иванов Иван Иванович):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(ProfileStates.entering_name, F.text == "❌ Отмена")
@router.message(ProfileStates.entering_birth_date, F.text == "❌ Отмена")
@router.message(ProfileStates.entering_phone, F.text == "❌ Отмена")
@router.message(ProfileStates.choosing_areas, F.text == "❌ Отмена")
@router.message(ProfileStates.choosing_specializations, F.text == "❌ Отмена")
@router.message(ProfileStates.choosing_experience, F.text == "❌ Отмена")
@router.message(ProfileStates.choosing_languages, F.text == "❌ Отмена")
async def cancel_registration(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    ctrl = await db.get_controller_by_telegram_id(message.from_user.id)  # type: ignore[union-attr]
    await message.answer(
        "❌ Регистрация отменена.",
        reply_markup=get_main_menu_keyboard(is_controller=ctrl is not None),
    )


@router.message(ProfileStates.entering_name)
async def reg_name(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    normalized = validate_full_name(text)
    if not normalized:
        await message.answer(
            "⚠️ Введите полное ФИО без инициалов.\n"
            "Пример: Иванов Иван Иванович"
        )
        return
    await state.update_data(pr_name=normalized)
    await state.set_state(ProfileStates.entering_birth_date)
    await message.answer("Шаг 2/7: Введите дату рождения в формате ДД.ММ.ГГГГ:")


@router.message(ProfileStates.entering_birth_date)
async def reg_birth_date(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    birth_iso = validate_birth_date(text)
    if not birth_iso:
        await message.answer(
            "⚠️ Неверная дата рождения.\n"
            "Используйте формат ДД.ММ.ГГГГ, возраст кандидата должен быть от 18 до 80 лет."
        )
        return
    await state.update_data(pr_birth_date=birth_iso)
    await state.set_state(ProfileStates.entering_phone)
    await message.answer("Шаг 3/7: Введите номер телефона в формате +79201234567:")


@router.message(ProfileStates.entering_phone)
async def reg_phone(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    phone = validate_phone_ru(text)
    if not phone:
        await message.answer("⚠️ Неверный формат номера. Пример: +79201234567")
        return
    await state.update_data(pr_phone=phone)
    await state.set_state(ProfileStates.choosing_specializations)
    data = await state.get_data()
    await message.answer(
        "Шаг 4/7: Выберите предпочтительные Вам специализации:",
        reply_markup=get_profile_specializations_keyboard(data.get("pr_specs", [])),
    )


@router.callback_query(ProfileStates.choosing_specializations, F.data.startswith("pr:s:"))
async def reg_spec_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    val = callback.data.split(":")[2]  # type: ignore[union-attr]
    if val == "done":
        if not data.get("pr_specs", []):
            await callback.answer("Выберите одну или несколько предпочтительных Вам специализаций", show_alert=True)
            return
        await state.set_state(ProfileStates.choosing_experience)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Шаг 5/7: Выберите типы мероприятий, на которых Вы уже работали стюардом:",
            reply_markup=get_profile_experience_keyboard(data.get("pr_exps", [])),
        )
        await callback.answer()
        return

    specs: list = data.get("pr_specs", [])
    if val in specs:
        specs.remove(val)
    else:
        specs.append(val)
    await state.update_data(pr_specs=specs)
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_profile_specializations_keyboard(specs),
    )
    await callback.answer()


@router.callback_query(ProfileStates.choosing_experience, F.data.startswith("pr:e:"))
async def reg_exp_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    val = callback.data.split(":")[2]  # type: ignore[union-attr]
    if val == "done":
        if not data.get("pr_exps", []):
            await callback.answer("Выберите хотя бы один тип мероприятий", show_alert=True)
            return
        await state.set_state(ProfileStates.choosing_areas)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Шаг 6/7: Выберите районы, где вам удобно работать:",
            reply_markup=get_profile_areas_keyboard(data.get("pr_areas", [])),
        )
        await callback.answer()
        return

    exps: list = data.get("pr_exps", [])
    if val in exps:
        exps.remove(val)
    else:
        exps.append(val)
    await state.update_data(pr_exps=exps)
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_profile_experience_keyboard(exps),
    )
    await callback.answer()


@router.callback_query(ProfileStates.choosing_areas, F.data.startswith("pr:area:"))
async def reg_area_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    val = callback.data.split(":")[2]  # type: ignore[union-attr]
    if val == "done":
        if not data.get("pr_areas", []):
            await callback.answer("Выберите хотя бы один район", show_alert=True)
            return
        await state.set_state(ProfileStates.choosing_languages)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "Шаг 7/7: Выберите языки, которыми владеете:",
            reply_markup=get_profile_languages_keyboard(data.get("pr_langs", [])),
        )
        await callback.answer()
        return

    areas: list = data.get("pr_areas", [])
    if val in areas:
        areas.remove(val)
    else:
        areas.append(val)
    await state.update_data(pr_areas=areas)
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_profile_areas_keyboard(areas),
    )
    await callback.answer()


@router.callback_query(ProfileStates.choosing_languages, F.data.startswith("pr:l:"))
async def reg_lang_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    val = callback.data.split(":")[2]  # type: ignore[union-attr]
    if val == "done":
        if not data.get("pr_langs", []):
            await callback.answer("Выберите хотя бы один язык", show_alert=True)
            return
        await _show_registration_summary(callback, state)
        await callback.answer()
        return

    langs: list = data.get("pr_langs", [])
    if val in langs:
        langs.remove(val)
    else:
        langs.append(val)
    await state.update_data(pr_langs=langs)
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=get_profile_languages_keyboard(langs),
    )
    await callback.answer()


async def _show_registration_summary(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileStates.confirming)
    data = await state.get_data()

    birth_date = birth_date_to_display(data.get("pr_birth_date"))
    age = age_from_birth_date(data.get("pr_birth_date"))
    age_str = f" ({age} лет)" if age is not None else ""

    text = (
        "📋 <b>Ваша заявка:</b>\n\n"
        f"👤 ФИО: {data.get('pr_name', '—')}\n"
        f"🎂 Дата рождения: {birth_date}{age_str}\n"
        f"📱 Телефон: {data.get('pr_phone') or '—'}\n"
        f"🎯 Специализации: {format_enum_list(data.get('pr_specs', []), Specialization)}\n"
        f"🏢 Опыт: {format_enum_list(data.get('pr_exps', []), ExperienceType)}\n"
        f"📍 Районы: {format_enum_list(data.get('pr_areas', []), WorkArea)}\n"
        f"🌐 Языки: {format_enum_list(data.get('pr_langs', []), Language)}\n"
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        text, parse_mode="HTML", reply_markup=get_profile_confirm_keyboard(),
    )


@router.callback_query(ProfileStates.confirming, F.data == "pr:confirm")
async def confirm_registration(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    await state.clear()

    user = callback.from_user
    app_id = await db.create_staff_application(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=data.get("pr_name", ""),
        birth_date=data.get("pr_birth_date"),
        phone=data.get("pr_phone"),
        specializations=data.get("pr_specs", []),
        experience_types=data.get("pr_exps", []),
        preferred_areas=data.get("pr_areas", []),
        languages=data.get("pr_langs", []),
    )

    birth_disp = birth_date_to_display(data.get("pr_birth_date"))
    age = age_from_birth_date(data.get("pr_birth_date"))
    age_str = f" ({age} лет)" if age is not None else ""

    admin_text = (
        f"📥 <b>Новая заявка в штат</b>\n\n"
        f"🆔 Заявка: #{app_id}\n"
        f"👤 ФИО: {escape(data.get('pr_name', '—'))}\n"
        f"🎂 Дата рождения: {escape(birth_disp)}{escape(age_str)}\n"
        f"📱 Телефон: {escape(data.get('pr_phone') or '—')}\n"
        f"👤 Telegram: @{user.username or '—'} (ID: {user.id})\n"
        f"🎯 Специализации: {escape(format_enum_list(data.get('pr_specs', []), Specialization))}\n"
        f"🏢 Опыт: {escape(format_enum_list(data.get('pr_exps', []), ExperienceType))}\n"
        f"📍 Районы: {escape(format_enum_list(data.get('pr_areas', []), WorkArea))}\n"
        f"🌐 Языки: {escape(format_enum_list(data.get('pr_langs', []), Language))}"
    )

    for admin_id in SETTINGS.admin_ids:
        try:
            await callback.bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                parse_mode="HTML",
                reply_markup=get_staff_application_actions_keyboard(app_id, user.id, user.username),
            )
        except Exception as exc:
            logger.warning("Failed to notify admin %s about staff application %s: %s", admin_id, app_id, exc)

    await callback.message.edit_text(  # type: ignore[union-attr]
        "✅ <b>Анкета отправлена!</b>\n\n"
        "Ваша заявка передана ответственному за подбор персонала.\n"
        "Мы свяжемся с вами по указанному телефону в течение 14 рабочих дней.",
        parse_mode="HTML",
    )
    await callback.message.answer(  # type: ignore[union-attr]
        "Главное меню:", reply_markup=get_main_menu_keyboard(is_controller=False),
    )
    await callback.answer()


@router.callback_query(ProfileStates.confirming, F.data == "pr:cancel")
async def cancel_registration_confirm(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    ctrl = await db.get_controller_by_telegram_id(callback.from_user.id)
    await callback.message.edit_text("❌ Регистрация отменена.")  # type: ignore[union-attr]
    await callback.message.answer(  # type: ignore[union-attr]
        "Главное меню:", reply_markup=get_main_menu_keyboard(is_controller=ctrl is not None),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("app:reply:"))
async def candidate_start_reply(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    app_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    app = await db.get_staff_application(app_id)
    if not app or app.get("user_id") != callback.from_user.id:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    await state.set_state(StaffApplicationCandidateStates.entering_message)
    await state.update_data(reply_app_id=app_id)
    await callback.message.answer(
        "Введите сообщение администратору по вашей заявке:",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(StaffApplicationCandidateStates.entering_message, F.text == "❌ Отмена")
async def candidate_cancel_reply(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    ctrl = await db.get_controller_by_telegram_id(message.from_user.id)  # type: ignore[union-attr]
    await message.answer(
        "Отправка сообщения отменена.",
        reply_markup=get_main_menu_keyboard(is_controller=ctrl is not None),
    )


@router.message(StaffApplicationCandidateStates.entering_message)
async def candidate_send_reply(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Сообщение не может быть пустым.")
        return

    data = await state.get_data()
    app_id = data.get("reply_app_id")
    if not app_id:
        await state.clear()
        await message.answer("Ошибка: заявка не найдена.")
        return

    app = await db.get_staff_application(app_id)
    if not app:
        await state.clear()
        await message.answer("Заявка не найдена.")
        return

    await db.add_staff_application_message(
        application_id=app_id,
        sender_id=message.from_user.id,  # type: ignore[union-attr]
        sender_role="candidate",
        message_text=text,
    )
    await state.clear()

    history = await db.get_staff_application_messages(app_id, limit=20)
    history_lines = ["💬 <b>История диалога:</b>"]
    for item in reversed(history):
        role = "Админ" if item.get("sender_role") == "admin" else "Кандидат"
        created = format_db_timestamp_msk(item.get("created_at"))
        history_lines.append(
            f"\n<b>{role}</b> [{created}]\n"
            f"📢 {escape(item.get('message_text', ''))}"
        )
    thread_text = "\n".join(history_lines)

    notify = (
        f"📨 <b>Ответ от кандидата в штат по заявке #{app_id}</b>\n\n"
        f"👤 {escape(app.get('full_name', '—'))}\n"
        f"📢 {escape(text)}\n\n"
        f"{thread_text}"
    )
    for admin_id in SETTINGS.admin_ids:
        try:
            await message.bot.send_message(
                chat_id=admin_id,
                text=notify,
                parse_mode="HTML",
                reply_markup=get_staff_application_actions_keyboard(
                    app_id,
                    app.get("user_id", 0),
                    app.get("username"),
                ),
            )
        except Exception as exc:
            logger.warning("Failed to notify admin %s about candidate reply: %s", admin_id, exc)

    await message.answer(
        "✅ Сообщение отправлено администратору.",
        reply_markup=get_main_menu_keyboard(is_controller=False),
    )


# ======================================================================
# View own profile
# ======================================================================

@router.message(F.text == "👤 Мой профиль")
async def view_my_profile(message: Message, db: Database) -> None:
    user = message.from_user
    if not user:
        return
    ctrl = await db.get_controller_by_telegram_id(user.id)
    if not ctrl:
        await message.answer(
            "Вы не зарегистрированы как контролер.\n"
            "Используйте «✍️ Хочу стать КРС» для отправки анкеты."
        )
        return
    text = format_controller_card(ctrl, short=False)
    await message.answer(text, parse_mode="HTML")


# ======================================================================
# View own invitations
# ======================================================================

@router.message(F.text == "📨 Мои приглашения")
async def view_my_invitations(message: Message, db: Database) -> None:
    user = message.from_user
    if not user:
        return
    ctrl = await db.get_controller_by_telegram_id(user.id)
    if not ctrl:
        await message.answer("Вы не зарегистрированы как контролер.")
        return

    invitations = await db.get_controller_invitations(ctrl["id"])
    if not invitations:
        await message.answer("📨 У вас пока нет приглашений.")
        return

    await message.answer(
        "📨 <b>Ваши приглашения:</b>",
        parse_mode="HTML",
        reply_markup=get_my_invitations_keyboard(invitations),
    )


@router.callback_query(F.data.startswith("mi:"))
async def view_invitation_detail(callback: CallbackQuery, db: Database) -> None:
    inv_id = int(callback.data.split(":")[1])  # type: ignore[union-attr]
    details = await db.get_invitation_with_details(inv_id)
    if not details:
        await callback.answer("Приглашение не найдено.", show_alert=True)
        return

    status_label = InvitationStatus(details["status"]).label if details["status"] in [s.value for s in InvitationStatus] else details["status"]
    event_info = {
        "title": details.get("event_title", "—"),
        "event_date": details.get("event_date", "—"),
        "event_time": details.get("event_time"),
        "location": details.get("event_location", "—"),
        "rate": details.get("rate"),
        "dress_code": details.get("dress_code"),
        "task_description": details.get("task_description"),
    }
    text = f"{format_event_card(event_info)}\n\nСтатус: {status_label}"

    # If still actionable, show buttons
    if details["status"] in (InvitationStatus.SENT, InvitationStatus.THINKING):
        await callback.message.edit_text(  # type: ignore[union-attr]
            text, parse_mode="HTML",
            reply_markup=get_invitation_buttons(inv_id),
        )
    else:
        await callback.message.edit_text(text, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()
