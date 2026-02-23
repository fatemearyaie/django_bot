
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.flow.currency_request import get_currency_requests_handlers
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
from bot.flow.usefull_links import get_useful_links_handlers


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

ABOUT_TEXT = """
با سلام و احترام

به اطلاع می‌رساند روال فعالیت این پلتفرم به صورت تبادلی انجام می‌شود. در هر معامله یک طرف خریدار و طرف دیگر فروشنده است و این پلتفرم به عنوان واسط، تضمین‌کننده اصل مبلغ برای هر دو طرف خواهد بود.

فرآیند انجام معامله بدین صورت است که در *مرحله نخست*، معادل ریالی از خریدار دریافت شده و وجه مذکور به صورت امانت نزد پلتفرم نگهداری می‌شود تا زمانی که ارز مورد نظر توسط فروشنده پرداخت و به حساب خریدار واریز گردد. پس از تأیید دریافت ارز از سوی خریدار، مبلغ ریالی به فروشنده پرداخت خواهد شد.

با این سازوکار، خریدار اطمینان خواهد داشت که وجه پرداختی وی نزد پلتفرم محفوظ است و در صورت عدم انجام تعهد از سوی فروشنده، مبلغ به طور کامل مسترد می‌گردد. همچنین فروشنده نیز اطمینان دارد که پرداخت ریالی از سوی خریدار انجام شده و سپس نسبت به انتقال ارز اقدام می‌نماید.

پس از ورود به ربات، لازم است مراحل عضویت را به طور کامل طی نمایید.

در مرحله بعد، می‌توانید درخواست خود را در کانال ثبت کرده یا از میان درخواست‌های موجود، مورد متناسب با شرایط خود را انتخاب و پیشنهاد مربوطه را ارسال نمایید. کلیه این فرآیندها از طریق سیستم رباتی مدیریت و ثبت می‌گردد.

پس از حصول توافق میان طرفین، هماهنگی‌های نهایی توسط ادمین رسمی معرفی‌شده در کانال انجام خواهد شد.

هدف این مجموعه، تضمین اصل مبلغ برای طرفین و فراهم‌سازی بستری امن، شفاف و مطمئن جهت انجام تبادلات ارزی بدون بروز مشکل است.

⚠️ تأکید می‌گردد تحت هیچ شرایطی بدون هماهنگی مستقیم با ادمین‌های رسمی معرفی‌شده در کانال، اقدام به انجام پرداخت ننمایید.

امید است با همکاری و همراهی شما کاربران گرامی، امکان انجام تبادلات در فضایی امن، منظم و قابل اعتماد فراهم گردد.
"""


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


async def about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        ABOUT_TEXT,
        parse_mode="Markdown",
    )

def build_application(token: str):
    application = Application.builder().token(token).build()
    application.post_init = post_init

    application.add_handler(build_offer_conversation(), group=0)
    application.add_handler(CommandHandler("start", start), group=1)
    application.add_handler(build_registration_conversation(), group=2)

    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex("^⁉️درباره ما$"), about_handler)
    )
    for h in get_currency_requests_handlers():
        application.add_handler(h)

    application.add_handler(get_trade_request_conversation())

    for h in get_my_requests_handlers():
        application.add_handler(h)

    application.add_handler(CallbackQueryHandler(offer_accept_cb, pattern=r"^offer_accept:\d+$"))
    application.add_handler(CallbackQueryHandler(offer_reject_cb, pattern=r"^offer_reject:\d+$"))
    application.add_handler(CallbackQueryHandler(offer_user_info_cb, pattern=r"^offer_user:\d+$"))

    for h in get_my_offers_handlers():
        application.add_handler(h)
    for h in get_useful_links_handlers():
        application.add_handler(h)



    return application
