import os
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import async_to_sync
from telegram.error import TelegramError

BOT_USERNAME = "excoinmarket_bot"

def build_currency_selector_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 دلار", url=f"https://t.me/{BOT_USERNAME}?start=cur_USD"),
            InlineKeyboardButton("💶 یورو", url=f"https://t.me/{BOT_USERNAME}?start=cur_EUR"),
        ],
        [
            InlineKeyboardButton("💷 درهم", url=f"https://t.me/{BOT_USERNAME}?start=cur_AED"),
        ],
    ])

def publish_currency_selector_to_channel(channel_chat_id: int) -> bool:
    token = os.environ.get("API_TOKEN")
    if not token:
        print("API_TOKEN not set")
        return False

    bot = Bot(token=token)

    text = (
        "📌 *درخواست‌های فعال بر اساس ارز*\n\n"
        "یکی از ارزها رو انتخاب کن تا داخل ربات، لیست درخواست‌های فعال همون ارز رو ببینی."
    )

    try:
        msg = async_to_sync(bot.send_message)(
            chat_id=channel_chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=build_currency_selector_keyboard(),
            disable_web_page_preview=True,
        )
        print("Currency selector message_id:", msg.message_id)
        return True

    except TelegramError as e:
        print("TELEGRAM send ERROR:", repr(e))
        return False