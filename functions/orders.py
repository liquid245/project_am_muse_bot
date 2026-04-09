import datetime
import logging
import random
import string

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_CHAT_ID, ADMIN_TOPIC_ID
from utils.payment import generate_payment_qr
from utils.storage_manager import StorageManager

orders_router = Router()


class OrderForm(StatesGroup):
    name = State()
    phone = State()
    address = State()
    waiting_for_receipt = State()


def generate_order_id():
    """Генерирует короткий уникальный ID заказа."""
    timestamp = datetime.datetime.now().strftime("%H%M")
    random_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"{timestamp}-{random_suffix}"


def get_cancel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить заказ", callback_data="cancel_order")
    return builder.as_markup()


async def initiate_order_flow(message: types.Message, state: FSMContext, item_id: str):
    """Запускает опросник оформления заказа для указанного товара."""
    storage_manager = StorageManager()
    catalog = storage_manager.get_catalog()
    item = next((i for i in catalog.get("items", []) if str(i["id"]) == item_id), None)

    if not item or item.get("stock", 0) <= 0:
        return False, "Извините, этот товар закончился."

    await state.update_data(
        order_item_id=item_id,
        order_item_title=item.get("title", "Без названия"),
        order_item_price=item.get("price", 0),
    )
    await state.set_state(OrderForm.name)
    await message.answer("Пожалуйста, введите ваше ФИО для оформления заказа:")
    return True, None


@orders_router.callback_query(F.data == "cancel_order")
async def cancel_order(callback_query: types.CallbackQuery, state: FSMContext):
    """Отмена заказа и восстановление остатка товара."""
    data = await state.get_data()
    item_id = data.get("order_item_id")

    if item_id:
        storage_manager = StorageManager()
        try:
            catalog = storage_manager.get_catalog()
            items = catalog.get("items", [])
            target_item = next(
                (i for i in items if str(i.get("id")) == str(item_id)), None
            )

            if target_item:
                target_item["stock"] = target_item.get("stock", 0) + 1
                if target_item["stock"] > 0:
                    target_item["status"] = "available"
                storage_manager.update_catalog(target_item)
                logging.info(f"Товар {item_id} возвращен на склад после отмены заказа.")
        except Exception as e:
            logging.error(f"Ошибка при возврате товара на склад: {e}")

    await state.clear()
    await callback_query.message.answer(
        "Заказ отменен. Вы можете вернуться в каталог /start."
    )
    await callback_query.answer()


@orders_router.callback_query(F.data.startswith("order_"))
async def process_order_init(callback_query: types.CallbackQuery, state: FSMContext):
    """Начало сценария заказа (опросник)."""
    item_id = callback_query.data.replace("order_", "")

    success, error_message = await initiate_order_flow(
        callback_query.message, state, item_id
    )
    if not success:
        return await callback_query.answer(
            error_message or "Извините, этот товар недоступен.", show_alert=True
        )
    await callback_query.answer()


@orders_router.message(F.text.startswith("/order_"))
async def process_order_command(message: types.Message, state: FSMContext):
    item_id = message.text.replace("/order_", "", 1).strip()
    if not item_id:
        return await message.answer("Пожалуйста, укажите идентификатор товара после команды.")

    await state.clear()
    success, error_message = await initiate_order_flow(message, state, item_id)
    if not success and error_message:
        await message.answer(error_message)


@orders_router.message(OrderForm.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(OrderForm.phone)
    await message.answer("Введите ваш номер телефона:")


@orders_router.message(OrderForm.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(OrderForm.address)
    await message.answer("Введите ваш адрес доставки:")


@orders_router.message(OrderForm.address)
async def process_address(message: types.Message, state: FSMContext):
    data = await state.get_data()
    address = message.text
    item_id = data.get("order_item_id")
    item_title = data.get("order_item_title")
    total_price = data.get("order_item_price", 0)
    order_id = generate_order_id()

    storage_manager = StorageManager()
    try:
        # Атомарное обновление каталога: уменьшаем количество (бронирование)
        catalog = storage_manager.get_catalog()
        items = catalog.get("items", [])

        target_item = None
        for item in items:
            if str(item.get("id")) == str(item_id):
                if item.get("stock", 0) > 0:
                    item["stock"] -= 1
                    if item["stock"] == 0:
                        item["status"] = "sold"
                    target_item = item
                break

        if not target_item:
            await state.clear()
            return await message.answer(
                "К сожалению, пока вы оформляли, товар закончился."
            )

        # Сохраняем обновленный каталог
        storage_manager.update_catalog(target_item)

        await state.update_data(
            address=address, order_id=order_id, total_price=total_price
        )

        # Инструкция по оплате
        qr_buffer = await generate_payment_qr(order_id, item_title, total_price)

        caption = (
            "💳 **Ваш заказ оформлен!**\n\n"
            f"Сумма к оплате: `{total_price}` руб.\n\n"
            "Для оплаты отсканируйте этот QR-код прямо из приложения вашего банка (Сбербанк, Тинькофф и др.). Все данные, сумма и номер заказа заполнятся автоматически.\n\n"
            "📸 **Важно:** После оплаты отправьте скриншот чека в этот чат для подтверждения."
        )

        await state.set_state(OrderForm.waiting_for_receipt)
        payment_message = await message.bot.send_photo(
            chat_id=message.chat.id,
            photo=types.BufferedInputFile(
                qr_buffer.getvalue(), filename=f"order_{order_id}_qr.png"
            ),
            caption=caption,
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard(),
        )
        await state.update_data(payment_message_id=payment_message.message_id)

    except Exception as e:
        logging.error(f"Ошибка при оформлении заказа: {e}")
        await message.answer(
            "❌ Произошла ошибка при оформлении заказа. Пожалуйста, попробуйте позже."
        )
        await state.clear()


@orders_router.message(OrderForm.waiting_for_receipt, F.photo | F.document)
async def process_receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    payment_message_id = data.get("payment_message_id")

    # Сохраняем file_id чека
    if message.photo:
        receipt_file_id = message.photo[-1].file_id
    else:
        receipt_file_id = message.document.file_id

    if payment_message_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=payment_message_id,
                reply_markup=None,
            )
        except Exception as edit_error:
            logging.warning(f"Не удалось скрыть кнопку отмены: {edit_error}")

    # Формируем полный отчет для админа
    order_details = (
        f"‼️ <b>Проверьте подлинность чека об оплате!</b>\n\n"
        f"🆔 <b>Заказ:</b> #{data['order_id']}\n"
        f"📦 <b>Товар:</b> {data['order_item_title']} (ID: <code>{data['order_item_id']}</code>)\n"
        f"💰 <b>Сумма:</b> {data['total_price']} руб.\n"
        f"👤 <b>Покупатель:</b> {data['name']} (ID: <code>{message.from_user.id}</code>)\n"
        f"📞 <b>Телефон:</b> <code>{data['phone']}</code>\n"
        f"🏠 <b>Адрес:</b> {data['address']}\n"
        f"📅 <b>Дата:</b> {datetime.date.today().isoformat()}"
    )

    # Уведомляем админа
    try:
        if message.photo:
            await message.bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=receipt_file_id,
                caption=order_details,
                message_thread_id=ADMIN_TOPIC_ID,
                parse_mode="HTML",
            )
        else:
            await message.bot.send_document(
                chat_id=ADMIN_CHAT_ID,
                document=receipt_file_id,
                caption=order_details,
                message_thread_id=ADMIN_TOPIC_ID,
                parse_mode="HTML",
            )

        await message.answer(
            "✅ Спасибо! Ваш заказ и чек переданы мастеру. Мы свяжемся с вами после проверки."
        )
        await state.clear()

    except Exception as e:
        logging.error(f"Ошибка при уведомлении админа об оплате: {e}")
        await message.answer(
            "❌ Произошла ошибка при отправке чека. Пожалуйста, попробуйте отправить еще раз или свяжитесь с мастером напрямую."
        )


@orders_router.message(OrderForm.waiting_for_receipt)
async def process_receipt_wrong_type(message: types.Message):
    await message.answer("Пожалуйста, отправьте скриншот чека в виде фото или файла.")
