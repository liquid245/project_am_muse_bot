import datetime
import logging

from aiogram import types, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.functions.utils import get_catalog_data, update_catalog_data, lock

orders_router = Router()

ORDER_CHAT_ID = -1003497103344  # User provided chat ID
ORDER_TOPIC_ID = 43  # User provided topic ID


class OrderForm(StatesGroup):
    name = State()
    phone = State()
    address = State()


@orders_router.callback_query(lambda c: c.data and c.data.startswith("order_"))
async def process_order(callback_query: types.CallbackQuery, state: FSMContext):
    item_id = callback_query.data.split("_")[1]
    await state.update_data(item_id=item_id)
    await state.set_state(OrderForm.name)
    await callback_query.message.answer("Введите ваше ФИО:")
    await callback_query.answer()


@orders_router.message(OrderForm.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(OrderForm.phone)
    await message.answer("Введите ваш номер телефона:")


@orders_router.message(OrderForm.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(OrderForm.address)
    await message.answer("Введите ваш адрес:")


@orders_router.message(OrderForm.address)
async def process_address(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    async with lock:
        catalog_data = await get_catalog_data()
        if catalog_data is None:
            await message.answer("Ошибка получения каталога.")
            return

        item_id = data["item_id"]
        logging.info(f"Processing order for item_id: {item_id}")
        item_title = ""
        item_price = 0
        item_in_stock = False
        for item in catalog_data["items"]:
            if item["id"] == item_id:
                logging.info(f"Found item in catalog. Stock: {item.get('stock')}")
                if item["stock"] > 0:
                    item_title = item["title"]
                    item_price = item["price"]
                    item["stock"] -= 1
                    if item["stock"] == 0:
                        item["status"] = "sold"
                    item_in_stock = True
                break

        if not item_in_stock:
            await message.answer("Извините, этот товар закончился.")
            return

        # Prepare order message for manager
        order_details = f"""
        ***НОВЫЙ ЗАКАЗ***

        **Товар:** {item_title} (ID: {item_id})
        **Цена:** {item_price} руб.
        **Количество:** 1
        **Покупатель:** {data["name"]} (ID: {message.from_user.id})
        **Телефон:** {data["phone"]}
        **Адрес:** {data["address"]}
        **Дата заказа:** {datetime.date.today().isoformat()}
        """

        if await update_catalog_data(catalog_data):
            await message.answer("Ваш заказ принят!")
            # Notify manager in the specified chat and topic
            try:
                # Need to get bot instance here to send message
                await message.bot.send_message(
                    chat_id=ORDER_CHAT_ID,
                    message_thread_id=ORDER_TOPIC_ID,
                    text=order_details,
                    parse_mode="Markdown",
                )
                logging.info(
                    f"Order {item_id} sent to manager chat {ORDER_CHAT_ID}, topic {ORDER_TOPIC_ID}"
                )
            except Exception as e:
                logging.error(f"Error sending order message to manager: {e}")
                await message.answer("Ошибка при отправке деталей заказа менеджеру.")
        else:
            await message.answer("Ошибка обновления каталога.")
