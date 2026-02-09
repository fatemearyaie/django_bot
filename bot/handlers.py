
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

from bot.flow.offer_manager import offer_accept_cb, offer_user_info_cb, offer_reject_cb
from bot.flow.registration import (
    post_init,
    build_registration_conversation,
    build_main_menu_keyboard,
    build_register_inline_keyboard,
    get_or_create_user,
    is_profile_complete,
)
from bot.flow.request import get_trade_request_conversation, get_my_requests_handlers
from bot.flow.offer import build_offer_conversation, get_my_offers_handlers


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    user = await get_or_create_user(tg.id, tg.username)

    if not is_profile_complete(user):
        await update.message.reply_text(
            f"👋 سلام {tg.username}!\nبرای استفاده از ربات، لطفاً ثبت‌نام کن 👇",
            reply_markup=build_register_inline_keyboard(),
        )
        return

    await update.message.reply_text(
        f"👋 سلام {tg.username}! خوش آمدی.",
        reply_markup=build_main_menu_keyboard(),
    )


def build_application(token: str):
    application = Application.builder().token(token).build()
    application.post_init = post_init

    application.add_handler(build_registration_conversation())


    application.add_handler(build_offer_conversation())
    application.add_handler(CommandHandler("start", start))

    application.add_handler(get_trade_request_conversation())

    for h in get_my_requests_handlers():
        application.add_handler(h)

    application.add_handler(CallbackQueryHandler(offer_accept_cb, pattern=r"^offer_accept:\d+$"))
    application.add_handler(CallbackQueryHandler(offer_reject_cb, pattern=r"^offer_reject:\d+$"))
    application.add_handler(CallbackQueryHandler(offer_user_info_cb, pattern=r"^offer_user:\d+$"))

    for h in get_my_offers_handlers():
        application.add_handler(h)

    return application
