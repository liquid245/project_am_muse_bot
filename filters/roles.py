from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, InlineQuery

from config import ADMIN_IDS

# TelegramObject, у которого есть from_user — работает и для message, и для callback_query
EventWithUser = Union[Message, CallbackQuery, InlineQuery]


class IsAdmin(BaseFilter):
    """Фильтр для проверки ролей администраторов.

    Принимает любое событие с from_user: message, callback_query, inline_query.
    Проверять только по message нельзя — на callback-хендлерах фильтр падал или пропускал.
    """

    async def __call__(self, event: EventWithUser) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in ADMIN_IDS)


class IsUser(BaseFilter):
    """Фильтр для проверки ролей обычных пользователей."""

    async def __call__(self, event: EventWithUser) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id not in ADMIN_IDS)
