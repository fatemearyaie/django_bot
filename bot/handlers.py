import os
from re import search

import django
from django.template.context_processors import request

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from Users.models import CustomUser, Country
from asgiref.sync import sync_to_async

# ================= STATE DEFINITIONS =================
NAME, LAST_NAME, COUNTRY, CITY, PHONE = range(5)

# ================= KEYBOARD DEFINITIONS =================
main_menu_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("➕ثبت درخواست جدید")],
        [KeyboardButton("🔍جست و جو")],
        [
            KeyboardButton("📥درخواست‌های من"),
            KeyboardButton("📬پیشنهادهای من")
        ],
        [KeyboardButton("🔗لینک های مفید و نرخ ارز")],
        [
            KeyboardButton("👤پروفایل"),
            KeyboardButton("⁉️درباره ما")
        ]
    ],
    resize_keyboard = True,
    one_time_keyboard = False,
)

# ================= USER SERVICE =================
@sync_to_async
def get_or_create_user(tg_id, tg_username):
    user, created = CustomUser.objects.get_or_create(
        telegram_id=tg_id,
        defaults={
            "telegram_username": tg_username,
            "username": tg_username or f"user_{tg_id}",
        },
    )
    if tg_username and user.username != tg_username:
        user.telegram_username = tg_username
        user.save(update_fields=["telegram_username"])
    return user


@sync_to_async
def save_user(user):
    user.save()


@sync_to_async
def get_available_countries():
    return list(Country.objects.filter(is_available=True))


@sync_to_async
def get_country_by_name(name):
    return Country.objects.get(name=name)


@sync_to_async
def save_city(user, city_name):
    user.city = city_name
    user.save()


@sync_to_async
def get_user_country_name(user):
    if user.country:
        return user.country.name
    return "نامشخص"

@sync_to_async
def save_phone(user, phone):
    user.phone = phone
    user.save()


# ================= START HANDLER =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    await get_or_create_user(tg.id, tg.username)
    await update.message.reply_text(
        f"👋 سلام {tg.username} ! خوش آمدی.",
        reply_markup = main_menu_keyboard
    )

async def profile(update, context):
    tg = update.effective_user
    await get_or_create_user(tg.id, tg.username)

    await update.message.reply_text("لطفا اسم خودت رو وارد کن")

    return NAME
# ================= NAME HANDLER =================
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(
        update.effective_user.id,
        update.effective_user.username,
    )
    user.name = update.message.text.strip()
    await save_user(user)

    await update.message.reply_text("👤 فامیلی خودت رو وارد کن:")
    return LAST_NAME


# ================= LAST NAME HANDLER =================
async def get_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(
        update.effective_user.id,
        update.effective_user.username,
    )
    user.last_name = update.message.text.strip()
    await save_user(user)

    countries = await get_available_countries()
    keyboard = [[KeyboardButton(c.name)] for c in countries]
    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        one_time_keyboard=True,
        resize_keyboard=True,
    )

    await update.message.reply_text(
        "🌍 کشور خودت رو انتخاب کن:",
        reply_markup=reply_markup,
    )
    return COUNTRY


# ================= COUNTRY HANDLER =================
async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(
        update.effective_user.id,
        update.effective_user.username,
    )
    country_name = update.message.text.strip()

    country = await get_country_by_name(country_name)
    user.country = country
    await save_user(user)


    await update.message.reply_text("🏙 شهر خودت رو وارد کن:",
                                    reply_markup=ReplyKeyboardRemove())
    return CITY


# ================= CITY HANDLER =================
async def get_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(
        update.effective_user.id,
        update.effective_user.username,
    )
    city_name = update.message.text.strip()
    await save_city(user, city_name)

    contact_button = KeyboardButton(
        text='ارسال شماره تماس',
        request_contact=True,
    )
    reply_markup = ReplyKeyboardMarkup(
        [[contact_button]],
        one_time_keyboard = True,
        resize_keyboard = True
    )
    await update.message.reply_text(
        "شماره تماس خودت رو ارسال کن!",
        reply_markup = reply_markup
    )
    return PHONE


async def get_phone(update:Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(
        update.effective_user.id,
        update.effective_user.username
    )
    phone = update.message.contact.phone_number
    await save_phone(user, phone)

    country_name = await get_user_country_name(user)

    await update.message.reply_text(
        f"✅ اطلاعات شما ذخیره شد:\n"
        f"👤 نام: {user.name}\n"
        f"👤 فامیلی: {user.last_name}\n"
        f"🌍 کشور: {country_name}\n"
        f"🏙 شهر: {user.city}\n"
        f"شماره:{user.phone}\n",
        reply_markup = main_menu_keyboard
    )

    return ConversationHandler.END


# ================= CANCEL HANDLER =================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ ثبت اطلاعات لغو شد.")
    return ConversationHandler.END



async def post_init(application: Application):
    commands = [
        BotCommand("new_request", "درخواست جدید"),
        BotCommand("requests", "درخواست های من"),
        BotCommand("offers", "پیشنهادهای من"),
        BotCommand("search", "جست و جو"),
        BotCommand("profile", "پروفایل"),
    ]
    await application.bot.set_my_commands(commands)


# ================= BUILD APPLICATION =================
def build_application(token):
    application = Application.builder().token(token).build()

    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("profile", profile),
                      MessageHandler(filters.Regex("^👤پروفایل$"), profile)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_last_name)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country_selected)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_city)],
            PHONE: [MessageHandler(filters.CONTACT, get_phone)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
        name="registration_conversation",
        allow_reentry=True,
    )
    application.add_handler(conv_handler)



    application.add_handler(CommandHandler("start",start))
    application.add_handler(CommandHandler("search", search))

    application.add_handler(MessageHandler(filters.Regex("^👤پروفایل$"), profile))
    return application
