import asyncio
import logging
import os
from pathlib import Path
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
RATES_FILE = Path(os.getenv("RATES_FILE", "/var/www/17exchange/rates.js")).expanduser()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found in .env")

if not ADMIN_IDS_RAW:
    raise RuntimeError("ADMIN_IDS not found in .env")

ADMIN_IDS = {int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip()}

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def build_rates_js(rub_to_cny: float, rub_to_usdt: float, usdt_to_rub: float) -> str:
    updated_at = datetime.now().strftime("%d.%m.%Y %H:%M")
    return f"""/*
  Этот файл обновляется Telegram-ботом.
*/

window.APP_RATES = {{
  rubToCny: {rub_to_cny},
  rubToUsdt: {rub_to_usdt},
  usdtToRub: {usdt_to_rub},
  updatedAt: '{updated_at}',
}};
"""


def parse_rates_file(content: str) -> dict[str, float | str]:
    def find_value(key: str) -> str:
        marker = f"{key}:"
        start = content.find(marker)
        if start == -1:
            raise ValueError(f"Key not found: {key}")
        start += len(marker)
        end = content.find(",", start)
        if end == -1:
            end = content.find("\n", start)
        return content[start:end].strip().strip("'").strip('"')

    return {
        "rubToCny": float(find_value("rubToCny")),
        "rubToUsdt": float(find_value("rubToUsdt")),
        "usdtToRub": float(find_value("usdtToRub")),
        "updatedAt": find_value("updatedAt"),
    }


def read_rates() -> dict[str, float | str]:
    if not RATES_FILE.exists():
        raise FileNotFoundError(f"Rates file not found: {RATES_FILE}")
    content = RATES_FILE.read_text(encoding="utf-8")
    return parse_rates_file(content)


def write_rates(rub_to_cny: float, rub_to_usdt: float, usdt_to_rub: float) -> None:
    RATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    RATES_FILE.write_text(
        build_rates_js(rub_to_cny, rub_to_usdt, usdt_to_rub),
        encoding="utf-8",
    )


def help_text() -> str:
    return (
        "Команды:\\n\\n"
        "/rates — показать текущие курсы\\n"
        "/setrates <rubToCny> <rubToUsdt> <usdtToRub> — обновить все 3 курса\\n"
        "Пример:\\n"
        "/setrates 12.08 95.4 93.9\\n\\n"
        "/setcny <число> — обновить только RUB → CNY\\n"
        "/setbuyusdt <число> — обновить только RUB → USDT\\n"
        "/setsellusdt <число> — обновить только USDT → RUB\\n\\n"
        "/path — показать путь к файлу курсов"
    )


async def deny(message: Message) -> None:
    await message.answer("Нет доступа.")


@dp.message(CommandStart())
async def command_start(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await deny(message)
        return
    await message.answer("Бот управления курсами 17 Exchange.\\n\\n" + help_text())


@dp.message(Command("help"))
async def command_help(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await deny(message)
        return
    await message.answer(help_text())


@dp.message(Command("path"))
async def command_path(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await deny(message)
        return
    await message.answer(f"Файл курсов:\\n{RATES_FILE}")


@dp.message(Command("rates"))
async def command_rates(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await deny(message)
        return
    try:
        rates = read_rates()
    except Exception as e:
        await message.answer(f"Ошибка чтения файла курсов:\\n{e}")
        return

    text = (
        "Текущие курсы:\\n\\n"
        f"RUB → CNY: {rates['rubToCny']}\\n"
        f"RUB → USDT: {rates['rubToUsdt']}\\n"
        f"USDT → RUB: {rates['usdtToRub']}\\n"
        f"Обновлено: {rates['updatedAt']}"
    )
    await message.answer(text)


@dp.message(Command("setrates"))
async def command_setrates(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await deny(message)
        return

    parts = message.text.split()
    if len(parts) != 4:
        await message.answer("Используй так:\\n/setrates 12.08 95.4 93.9")
        return

    try:
        rub_to_cny = float(parts[1].replace(",", "."))
        rub_to_usdt = float(parts[2].replace(",", "."))
        usdt_to_rub = float(parts[3].replace(",", "."))
    except ValueError:
        await message.answer("Ошибка: все значения должны быть числами.")
        return

    try:
        write_rates(rub_to_cny, rub_to_usdt, usdt_to_rub)
    except Exception as e:
        await message.answer(f"Ошибка записи файла курсов:\\n{e}")
        return

    await message.answer(
        "Курсы обновлены.\\n\\n"
        f"RUB → CNY: {rub_to_cny}\\n"
        f"RUB → USDT: {rub_to_usdt}\\n"
        f"USDT → RUB: {usdt_to_rub}"
    )


async def update_one_rate(message: Message, key: str, value: float) -> None:
    try:
        rates = read_rates()
        rub_to_cny = float(rates["rubToCny"])
        rub_to_usdt = float(rates["rubToUsdt"])
        usdt_to_rub = float(rates["usdtToRub"])

        if key == "rubToCny":
            rub_to_cny = value
        elif key == "rubToUsdt":
            rub_to_usdt = value
        elif key == "usdtToRub":
            usdt_to_rub = value

        write_rates(rub_to_cny, rub_to_usdt, usdt_to_rub)
    except Exception as e:
        await message.answer(f"Ошибка обновления курса:\\n{e}")
        return

    await message.answer(
        "Курс обновлён.\\n\\n"
        f"RUB → CNY: {rub_to_cny}\\n"
        f"RUB → USDT: {rub_to_usdt}\\n"
        f"USDT → RUB: {usdt_to_rub}"
    )


@dp.message(Command("setcny"))
async def command_setcny(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await deny(message)
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Используй: /setcny 12.08")
        return
    try:
        value = float(parts[1].replace(",", "."))
    except ValueError:
        await message.answer("Ошибка: значение должно быть числом.")
        return
    await update_one_rate(message, "rubToCny", value)


@dp.message(Command("setbuyusdt"))
async def command_setbuyusdt(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await deny(message)
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Используй: /setbuyusdt 95.4")
        return
    try:
        value = float(parts[1].replace(",", "."))
    except ValueError:
        await message.answer("Ошибка: значение должно быть числом.")
        return
    await update_one_rate(message, "rubToUsdt", value)


@dp.message(Command("setsellusdt"))
async def command_setsellusdt(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await deny(message)
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Используй: /setsellusdt 93.9")
        return
    try:
        value = float(parts[1].replace(",", "."))
    except ValueError:
        await message.answer("Ошибка: значение должно быть числом.")
        return
    await update_one_rate(message, "usdtToRub", value)


@dp.message()
async def fallback(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await deny(message)
        return
    await message.answer("Не понял команду.\\n\\n" + help_text())


async def main() -> None:
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
