from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Лиги", callback_data="leagues:0")],
            [InlineKeyboardButton(text="⚽ Команды", callback_data="teams_leagues:0")],
            [InlineKeyboardButton(text="⭐ Мои подписки", callback_data="my")],
            [
                InlineKeyboardButton(text="📅 Матчи", callback_data="calendar:upcoming"),
                InlineKeyboardButton(text="📋 Результаты", callback_data="calendar:results"),
            ],
            [InlineKeyboardButton(text="📊 Таблицы", callback_data="standings:list")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        ]
    )
