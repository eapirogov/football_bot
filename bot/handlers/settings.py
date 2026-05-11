from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bot.db.base import async_session_maker
from bot.db.models import UserSettings

router = Router()

# Список доступных часовых поясов с понятными названиями
TIMEZONES: list[tuple[str, str]] = [
    ("Europe/Kaliningrad", "Калининград (UTC+2)"),
    ("Europe/Moscow",      "Москва (UTC+3)"),
    ("Europe/Samara",      "Самара (UTC+4)"),
    ("Asia/Yekaterinburg", "Екатеринбург / Пермь (UTC+5)"),
    ("Asia/Omsk",          "Омск (UTC+6)"),
    ("Asia/Krasnoyarsk",   "Красноярск (UTC+7)"),
    ("Asia/Irkutsk",       "Иркутск (UTC+8)"),
    ("Asia/Yakutsk",       "Якутск (UTC+9)"),
    ("Asia/Vladivostok",   "Владивосток (UTC+10)"),
    ("Asia/Magadan",       "Магадан (UTC+11)"),
    ("Asia/Kamchatka",     "Камчатка (UTC+12)"),
    ("Europe/London",      "Лондон (UTC+0/+1)"),
    ("Europe/Berlin",      "Берлин / Париж (UTC+1/+2)"),
]

_TZ_LABEL = {tz: label for tz, label in TIMEZONES}


async def _get_or_create(user_id: int) -> UserSettings:
    async with async_session_maker() as session:
        s = await session.get(UserSettings, user_id)
        if not s:
            stmt = pg_insert(UserSettings).values(user_id=user_id).on_conflict_do_nothing()
            await session.execute(stmt)
            await session.commit()
            s = await session.get(UserSettings, user_id)
        return s


def _settings_kb(s: UserSettings) -> InlineKeyboardMarkup:
    notif_label = "🔔 Уведомления: ВКЛ" if s.notifications_enabled else "🔕 Уведомления: ВЫКЛ"
    tz_label = _TZ_LABEL.get(s.timezone, s.timezone)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=notif_label, callback_data="settings:toggle_notif")],
            [InlineKeyboardButton(text=f"⏰ За {s.pre_match_minutes} мин до матча", callback_data="settings:cycle_pre")],
            [InlineKeyboardButton(text=f"🕐 {tz_label}", callback_data="settings:tz_menu")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        ]
    )


def _settings_text(s: UserSettings) -> str:
    notif_status = "включены" if s.notifications_enabled else "выключены"
    tz_label = _TZ_LABEL.get(s.timezone, s.timezone)
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"Уведомления: <b>{notif_status}</b>\n"
        f"Напоминание: за <b>{s.pre_match_minutes} минут</b> до матча\n"
        f"Часовой пояс: <b>{tz_label}</b>"
    )


def _tz_menu_kb(current_tz: str) -> InlineKeyboardMarkup:
    rows = []
    for tz, label in TIMEZONES:
        mark = "✅ " if tz == current_tz else ""
        rows.append([InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"settings:set_tz:{tz}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    s = await _get_or_create(message.from_user.id)
    await message.answer(_settings_text(s), reply_markup=_settings_kb(s), parse_mode="HTML")


@router.callback_query(F.data == "settings")
async def cb_settings(query: CallbackQuery) -> None:
    s = await _get_or_create(query.from_user.id)
    await query.message.edit_text(_settings_text(s), reply_markup=_settings_kb(s), parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data == "settings:toggle_notif")
async def cb_toggle_notif(query: CallbackQuery) -> None:
    async with async_session_maker() as session:
        s = await session.get(UserSettings, query.from_user.id)
        if not s:
            s = UserSettings(user_id=query.from_user.id)
            session.add(s)
        s.notifications_enabled = not s.notifications_enabled
        await session.commit()
        await session.refresh(s)
    await query.message.edit_text(_settings_text(s), reply_markup=_settings_kb(s), parse_mode="HTML")
    await query.answer("Сохранено")


_PRE_OPTIONS = [10, 15, 20, 30, 60]


@router.callback_query(F.data == "settings:cycle_pre")
async def cb_cycle_pre(query: CallbackQuery) -> None:
    async with async_session_maker() as session:
        s = await session.get(UserSettings, query.from_user.id)
        if not s:
            s = UserSettings(user_id=query.from_user.id)
            session.add(s)
        current = s.pre_match_minutes
        try:
            idx = _PRE_OPTIONS.index(current)
            s.pre_match_minutes = _PRE_OPTIONS[(idx + 1) % len(_PRE_OPTIONS)]
        except ValueError:
            s.pre_match_minutes = _PRE_OPTIONS[0]
        await session.commit()
        await session.refresh(s)
    await query.message.edit_text(_settings_text(s), reply_markup=_settings_kb(s), parse_mode="HTML")
    await query.answer(f"Напоминание за {s.pre_match_minutes} мин")


@router.callback_query(F.data == "settings:tz_menu")
async def cb_tz_menu(query: CallbackQuery) -> None:
    s = await _get_or_create(query.from_user.id)
    await query.message.edit_text(
        "🕐 <b>Выбери часовой пояс</b>",
        reply_markup=_tz_menu_kb(s.timezone),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(F.data.startswith("settings:set_tz:"))
async def cb_set_tz(query: CallbackQuery) -> None:
    tz = query.data.removeprefix("settings:set_tz:")
    if tz not in _TZ_LABEL:
        await query.answer("Неизвестный часовой пояс")
        return
    async with async_session_maker() as session:
        s = await session.get(UserSettings, query.from_user.id)
        if not s:
            s = UserSettings(user_id=query.from_user.id)
            session.add(s)
        s.timezone = tz
        await session.commit()
        await session.refresh(s)
    await query.message.edit_text(_settings_text(s), reply_markup=_settings_kb(s), parse_mode="HTML")
    await query.answer(f"Сохранено: {_TZ_LABEL[tz]}")
