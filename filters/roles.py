from aiogram.filters import BaseFilter
from aiogram.types import Message
from config import ADMIN_IDS

class IsAdmin(BaseFilter):
    """Фильтр для проверки ролей администраторов."""
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in ADMIN_IDS

class IsUser(BaseFilter):
    """Фильтр для проверки ролей обычных пользователей."""
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id not in ADMIN_IDS
