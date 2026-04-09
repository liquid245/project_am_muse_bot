import asyncio
import logging
import shutil
from io import BytesIO

try:
    import qrcode  # type: ignore
except ImportError:  # pragma: no cover - fallback when deps missing
    qrcode = None


async def _generate_with_qrcode(gost_str: str) -> BytesIO:
    if qrcode is None:
        raise ImportError("qrcode library is unavailable")

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(gost_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


async def _generate_with_cli(gost_str: str) -> BytesIO:
    qrencode_path = shutil.which("qrencode")
    if not qrencode_path:
        raise RuntimeError(
            "Не удалось сгенерировать QR-код: библиотека 'qrcode' не установлена, "
            "а утилита 'qrencode' недоступна."
        )

    process = await asyncio.create_subprocess_exec(
        qrencode_path,
        "-t",
        "PNG",
        "-o",
        "-",
        "-s",
        "10",
        "-m",
        "4",
        gost_str,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(
            f"qrencode завершился с ошибкой ({process.returncode}): {stderr.decode('utf-8', errors='ignore')}"
        )

    return BytesIO(stdout)


async def generate_payment_qr(order_id: str, item_title: str, price: int) -> BytesIO:
    """Генерирует QR-код оплаты по ГОСТ Р 56042-2014."""
    gost_str = (
        "ST00012"
        "|Name=МУХОРТОВА АНАСТАСИЯ СЕРГЕЕВНА"
        "|PersonalAcc=40817810838121626430"
        "|BankName=ПАО Сбербанк"
        "|BIC=044525225"
        "|CorrespAcc=30101810400000000225"
        "|PayeeINN=7707083893"
        f"|Sum={int(price * 100)}"
        f"|Purpose=Заказ {order_id} - {item_title}"
    )

    if qrcode is not None:
        try:
            return await _generate_with_qrcode(gost_str)
        except Exception as exc:  # pragma: no cover - fallback path
            logging.warning("qrcode generation failed, fallback to CLI: %s", exc)

    buffer = await _generate_with_cli(gost_str)
    buffer.seek(0)
    return buffer
