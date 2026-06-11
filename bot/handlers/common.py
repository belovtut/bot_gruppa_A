"""Common handlers: /start, FAQ, vacancies, contacts, about, main-menu navigation."""
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from bot.deps import is_admin
from database import Database
from bot.keyboards import (
    get_admin_keyboard,
    get_faq_keyboard,
    get_main_menu_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name="common")


async def _safe_faq_edit(callback: CallbackQuery, text: str) -> None:
    """Edit FAQ message safely; ignore Telegram no-op edit error."""
    if not callback.message:
        return
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_faq_keyboard(),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise


# ------------------------------------------------------------------
# /start
# ------------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    """Handle /start — greet user, save to DB, show appropriate menu."""
    user = message.from_user
    if not user:
        return
    await db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    # Auto-link known controller profile by matching username on first contact.
    linked = await db.link_controller_telegram_by_username(user.id, user.username)
    if linked:
        logger.info(
            "Linked controller telegram_id=%s by username=%s",
            user.id,
            user.username,
        )

    if is_admin(user.id):
        await message.answer(
            "👋 Добро пожаловать, администратор!\n\n"
            "Используйте панель ниже для управления ботом и базой контролеров.",
            reply_markup=get_admin_keyboard(),
        )
        return

    # Check if user is a registered controller
    ctrl = await db.get_controller_by_telegram_id(user.id)
    is_ctrl = ctrl is not None

    await message.answer(
        "👋 Добро пожаловать в бот по трудоустройству КРС!\n\n"
        "Здесь вы найдете информацию о вакансиях контролеров-распорядителей "
        "и сможете задать интересующие вас вопросы.\n\n"
        "Используйте кнопки меню ниже для навигации.",
        reply_markup=get_main_menu_keyboard(is_controller=is_ctrl),
    )


# ------------------------------------------------------------------
# FAQ
# ------------------------------------------------------------------

@router.message(F.text == "📋 Часто задаваемые вопросы")
async def show_faq(message: Message) -> None:
    await message.answer(
        "📋 <b>Часто задаваемые вопросы</b>\n\nВыберите интересующий вас вопрос:",
        parse_mode="HTML",
        reply_markup=get_faq_keyboard(),
    )


@router.callback_query(F.data == "faq_krs")
async def faq_krs(callback: CallbackQuery) -> None:
    await _safe_faq_edit(
        callback,
        "📌 <b>Что такое КРС?</b>\n\n"
        "КРС — Контролер-Распорядитель — это специалист, который:\n\n"
        "• Осуществляет контроль за соблюдением установленных правил и норм\n"
        "• Координирует работу персонала на объекте\n"
        "• Обеспечивает порядок и безопасность\n"
        "• Взаимодействует с посетителями и клиентами\n"
        "• Решает организационные вопросы\n\n"
        "Это ответственная работа, требующая внимательности и коммуникабельности.",
    )
    await callback.answer()


@router.callback_query(F.data == "faq_requirements")
async def faq_requirements(callback: CallbackQuery) -> None:
    await _safe_faq_edit(
        callback,
        "📌 <b>Требования к кандидатам</b>\n\n"
        "<b>Обязательные требования:</b>\n"
        "• Возраст от 18 лет\n"
        "• Гражданство РФ\n"
        "• Отсутствие судимости\n"
        "• Ответственность и пунктуальность\n\n"
        "<b>Желательно:</b>\n"
        "• Опыт работы с людьми\n"
        "• Коммуникабельность\n"
        "• Стрессоустойчивость\n"
        "• Умение работать в команде\n\n"
        "Готовность к обучению обязательна!",
    )
    await callback.answer()


@router.callback_query(F.data == "faq_schedule")
async def faq_schedule(callback: CallbackQuery) -> None:
    await _safe_faq_edit(
        callback,
        "📌 <b>График работы</b>\n\n"
        "Мы предлагаем гибкий график работы:\n\n"
        "• Различные форматы смен\n"
        "• Возможность выбора удобного расписания\n"
        "• Возможность подработки на мероприятиях\n\n"
        "График обсуждается индивидуально под каждое мероприятие!",
    )
    await callback.answer()


@router.callback_query(F.data == "faq_conditions")
async def faq_conditions(callback: CallbackQuery) -> None:
    await _safe_faq_edit(
        callback,
        "📌 <b>Условия работы</b>\n\n"
        "<b>Мы предлагаем:</b>\n\n"
        "💰 Конкурентная ставка за мероприятие\n"
        "📋 Официальное трудоустройство\n"
        "🎓 Бесплатное обучение\n"
        "📈 Рейтинговая система и карьерный рост\n"
        "👥 Работа на крупных мероприятиях (концерты, конференции, спорт)\n",
    )
    await callback.answer()


@router.callback_query(F.data == "faq_how_to_apply")
async def faq_how_to_apply(callback: CallbackQuery) -> None:
    await _safe_faq_edit(
        callback,
        "📌 <b>Как устроиться на работу?</b>\n\n"
        "<b>Процесс трудоустройства:</b>\n\n"
        "1️⃣ Отправьте анкету через кнопку «✍️ Хочу стать КРС»\n"
        "2️⃣ Заполните профиль: ФИО, опыт работы, удобные локации\n"
        "3️⃣ Дождитесь рассмотрения анкеты ответственным администратором\n"
        "4️⃣ После одобрения с вами свяжутся по телефону\n\n"
        "📞 По вопросам обращайтесь через раздел «Контакты».",
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: CallbackQuery, db: Database) -> None:
    if not callback.message or not callback.from_user:
        await callback.answer()
        return

    ctrl = await db.get_controller_by_telegram_id(callback.from_user.id)
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=None,
    )
    await callback.message.answer(
        "Используйте кнопки ниже:",
        reply_markup=get_main_menu_keyboard(is_controller=ctrl is not None),
    )
    await callback.answer()


# Ignore no-op callback
@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


# ------------------------------------------------------------------
# Static menu items
# ------------------------------------------------------------------

@router.message(F.text == "💼 О вакансиях КРС")
async def show_vacancies(message: Message) -> None:
    await message.answer(
        "💼 <b>Вакансии КРС (Контролер-Распорядитель)</b>\n\n"
        "Мы приглашаем на работу контролеров-распорядителей!\n\n"
        "<b>Направления:</b>\n"
        "• Контролер на входе\n"
        "• Распорядитель в зале\n"
        "• VIP-сопровождение\n\n"
        "<b>Типы мероприятий:</b>\n"
        "• Концерты\n• Конференции\n• Спортивные события\n• Корпоративы\n\n"
        "<b>Мы предлагаем:</b>\n"
        "• Конкурентную оплату\n• Гибкий график\n• Рейтинговую систему\n\n"
        "Отправьте анкету через кнопку «✍️ Хочу стать КРС» для рассмотрения вашей кандидатуры!",
        parse_mode="HTML",
    )


@router.message(F.text == "📞 Контакты")
async def show_contacts(message: Message) -> None:
    await message.answer(
        "📞 <b>Контактная информация</b>\n\n"
        "📧 Email: st@gruppa-a.com\n"
        "📱 Телефон: 8 (800) 555-42-12\n"
        "🕐 Режим работы: Пн-Пт 8:00-17:00, перерыв 13:00–14:00\n\n"
        "Также вы можете задать вопросы прямо в этом боте!",
        parse_mode="HTML",
    )


@router.message(F.text == "ℹ️ О боте")
async def show_about(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>О боте</b>\n\n"
        "Бот для подбора контролеров-распорядителей (КРС) на мероприятия.\n\n"
        "<b>Возможности:</b>\n"
        "• Информация о вакансиях и FAQ\n"
        "• Регистрация в базе контролеров\n"
        "• Получение приглашений на мероприятия\n"
        "• Управление профилем и историей участия\n\n"
        "Используйте кнопки меню для навигации.",
        parse_mode="HTML",
    )


# ------------------------------------------------------------------
# Back to main menu
# ------------------------------------------------------------------

@router.message(F.text == "🔙 Главное меню")
async def back_to_main_menu(message: Message, db: Database) -> None:
    user = message.from_user
    if not user:
        return
    ctrl = await db.get_controller_by_telegram_id(user.id)
    await message.answer(
        "Главное меню:",
        reply_markup=get_main_menu_keyboard(is_controller=ctrl is not None),
    )
