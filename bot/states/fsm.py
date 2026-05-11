from aiogram.fsm.state import State, StatesGroup


class TeamSearch(StatesGroup):
    waiting_for_query = State()
