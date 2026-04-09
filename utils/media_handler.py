import asyncio
import logging
from typing import Any, Dict, List, Union
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

class MediaGroupMiddleware(BaseMiddleware):
    """
    Middleware for collecting media group (albums).
    Wait for a short latency and then pass all messages in the album to the handler as 'album' parameter.
    """
    def __init__(self, latency: float = 0.6):
        self.latency = latency
        self.album_cache: Dict[str, List[Message]] = {}
        super().__init__()

    async def __call__(
        self,
        handler: Any,
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not isinstance(event, Message) or event.media_group_id is None:
            return await handler(event, data)

        # First message in album
        if event.media_group_id not in self.album_cache:
            self.album_cache[event.media_group_id] = [event]
            
            # Wait for all messages in the media group to arrive
            await asyncio.sleep(self.latency)
            
            # After waiting, retrieve the full album and clear cache
            album = self.album_cache.pop(event.media_group_id, [])
            if not album:
                return # Should not happen, but for safety
            
            # Add album to data for the handler
            data["album"] = album
            return await handler(event, data)
        else:
            # Subsequent messages in the same album
            self.album_cache[event.media_group_id].append(event)
            return # Stop execution for other messages in the album
