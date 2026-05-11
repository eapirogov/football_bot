from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import League

PAGE_SIZE = 8


def leagues_page_kb(leagues: list[League], page: int, subscribed_ids: set[int], action: str = "leagues") -> InlineKeyboardMarkup:
    """Build paginated league list. action: 'leagues' (toggle) or 'pick_league' (jump to teams)."""
    start = page * PAGE_SIZE
    chunk = leagues[start : start + PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = []
    for lg in chunk:
        marker = "✅ " if lg.id in subscribed_ids else ""
        if action == "leagues":
            cb = f"toggle_league:{lg.id}:{page}"
        else:
            cb = f"open_league_teams:{lg.id}:0"
        rows.append([InlineKeyboardButton(text=f"{marker}{lg.name} ({lg.country})", callback_data=cb)])

    nav: list[InlineKeyboardButton] = []
    prefix = "leagues" if action == "leagues" else "teams_leagues"
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:{page - 1}"))
    if start + PAGE_SIZE < len(leagues):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
