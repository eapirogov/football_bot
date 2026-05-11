from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import Team

PAGE_SIZE = 8


def teams_page_kb(league_id: int, teams: list[Team], page: int, subscribed_ids: set[int]) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    chunk = teams[start : start + PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = []
    for t in chunk:
        marker = "✅ " if t.id in subscribed_ids else ""
        rows.append([
            InlineKeyboardButton(text=f"{marker}{t.name}", callback_data=f"toggle_team:{t.id}:{league_id}:{page}")
        ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"open_league_teams:{league_id}:{page - 1}"))
    if start + PAGE_SIZE < len(teams):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"open_league_teams:{league_id}:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="🔍 Поиск по имени", callback_data="search_team"),
        InlineKeyboardButton(text="◀️ Лиги", callback_data="teams_leagues:0"),
    ])
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
