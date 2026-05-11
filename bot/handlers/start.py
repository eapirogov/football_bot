from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bot.db.base import async_session_maker
from bot.db.models import User
from bot.keyboards.main_menu import main_menu_kb

router = Router()

WELCOME = (
    "👋 Привет! Это бот футбольного расписания.\n\n"
    "Подпишись на любимые <b>команды</b> или целые <b>лиги</b>, "
    "и я буду напоминать о матчах за 20 минут до начала и присылать результаты с детальной статистикой.\n\n"
    "Выбери раздел ниже:"
)

HELP = (
    "<b>Как пользоваться:</b>\n\n"
    "<b>Подписки</b>\n"
    "• 🏆 <b>Лиги</b> — подписаться на все матчи лиги\n"
    "• ⚽ <b>Команды</b> — подписаться на конкретную команду\n"
    "• ⭐ <b>Мои подписки</b> — список активных подписок и отписка\n\n"
    "<b>Матчи</b>\n"
    "• 📅 <b>Матчи</b> — ближайшие матчи по подпискам\n"
    "• 📋 <b>Результаты</b> — последние завершённые матчи\n"
    "• 📊 <b>Таблицы</b> — турнирная таблица любой лиги\n\n"
    "<b>Уведомления</b>\n"
    "• За N минут до матча — напоминание о начале\n"
    "• После матча — итоговый счёт и кнопка статистики\n\n"
    "<b>Настройки</b>\n"
    "• ⚙️ Включить/выключить уведомления\n"
    "• Время напоминания: за 10, 15, 20, 30 или 60 минут\n"
    "• Часовой пояс: время матчей отображается в твоём поясе\n\n"
    "<b>Команды</b>\n"
    "/start — главное меню\n"
    "/upcoming — ближайшие матчи\n"
    "/results — последние результаты\n"
    "/table — турнирные таблицы\n"
    "/settings — настройки\n"
    "/help — эта справка"
)


async def upsert_user(user_id: int, username: str | None) -> None:
    async with async_session_maker() as session:
        stmt = pg_insert(User).values(id=user_id, username=username)
        stmt = stmt.on_conflict_do_update(index_elements=[User.id], set_={"username": stmt.excluded.username})
        await session.execute(stmt)
        await session.commit()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await upsert_user(message.from_user.id, message.from_user.username)
    await message.answer(WELCOME, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == "menu")
async def cb_menu(query: CallbackQuery) -> None:
    await query.message.edit_text(WELCOME, reply_markup=main_menu_kb(), parse_mode="HTML")
    await query.answer()


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == "help")
async def cb_help(query: CallbackQuery) -> None:
    await query.message.edit_text(HELP, reply_markup=main_menu_kb(), parse_mode="HTML")
    await query.answer()
