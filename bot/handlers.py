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
    BotCommand, ReplyKeyboardRemove
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
NAME, LAST_NAME, COUNTRY, PHONE, CONFIRM, EDIT_MENU, EDIT_NAME, EDIT_LAST, EDIT_COUNTRY, EDIT_PHONE = range(10)

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
    resize_keyboard=True,
    one_time_keyboard=False,
)

# ================= EDIT FLOW (NEW) =================

def build_edit_inline_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ ویرایش نام", callback_data="edit_name")],
            [InlineKeyboardButton("✏️ ویرایش فامیلی", callback_data="edit_last")],
            [InlineKeyboardButton("🌍 ویرایش کشور", callback_data="edit_country")],
            [InlineKeyboardButton("📞 ویرایش شماره", callback_data="edit_phone")],
            [InlineKeyboardButton("↩️ برگشت به تایید", callback_data="edit_back")],
        ]
    )


async def edit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "edit_back":
        if context.user_data.get("existing_profile"):
            user = await get_or_create_user(query.from_user.id, query.from_user.username)
            await query.message.reply_text("برگشتیم به پروفایل:", reply_markup=build_edit_inline_keyboard())
            return EDIT_MENU

        confirm_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("✅ تایید"), KeyboardButton("❌ اصلاح")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await query.message.reply_text("خب، تایید می‌کنی یا اصلاح؟", reply_markup=confirm_keyboard)
        return CONFIRM

    if data == "edit_name":
        await query.message.reply_text("✏️ نام جدید را وارد کن:")
        return EDIT_NAME

    if data == "edit_last":
        await query.message.reply_text("✏️ فامیلی جدید را وارد کن:")
        return EDIT_LAST

    if data == "edit_country":
        countries = await get_available_countries()
        keyboard = [[KeyboardButton(c.name)] for c in countries]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await query.message.reply_text("🌍 کشور جدید را انتخاب کن:", reply_markup=reply_markup)
        return EDIT_COUNTRY

    if data == "edit_phone":
        contact_button = KeyboardButton(text='ارسال شماره تماس', request_contact=True)
        reply_markup = ReplyKeyboardMarkup([[contact_button]], one_time_keyboard=True, resize_keyboard=True)
        await query.message.reply_text("📞 شماره جدید را با دکمه زیر ارسال کن:", reply_markup=reply_markup)
        return EDIT_PHONE

    return EDIT_MENU


async def show_preview_and_ask_confirm(update_or_query_message, user, country_name, phone):
    preview_text = (
        "🧾 پیش‌نمایش اطلاعات شما:\n\n"
        f"👤 نام: {user.name or '—'}\n"
        f"👤 فامیلی: {user.last_name or '—'}\n"
        f"🌍 کشور: {country_name}\n"
        f"📞 شماره: {phone}\n\n"
        "✅ مطمئنی همین اطلاعات ثبت بشه؟"
    )
    confirm_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("✅ تایید"), KeyboardButton("❌ اصلاح")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update_or_query_message.reply_text(preview_text, reply_markup=confirm_keyboard)


async def edit_name_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    user.name = update.message.text.strip()
    await save_user(user)

    if context.user_data.get("existing_profile"):
        await show_profile(update, user)
        return EDIT_MENU

    phone = context.user_data.get("pending_phone") or user.phone or "—"
    country_name = await get_user_country_name(user)
    await show_preview_and_ask_confirm(update.message, user, country_name, phone)

    return CONFIRM



async def edit_last_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    user.last_name = update.message.text.strip()
    await save_user(user)

    if context.user_data.get("existing_profile"):
        await show_profile(update, user)
        return EDIT_MENU

    phone = context.user_data.get("pending_phone") or user.phone or "—"
    country_name = await get_user_country_name(user)
    await show_preview_and_ask_confirm(update.message, user, country_name, phone)
    return CONFIRM


async def edit_country_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    country_name_input = update.message.text.strip()

    try:
        country = await get_country_by_name(country_name_input)
    except Exception:
        await update.message.reply_text("❌ کشور پیدا نشد، دوباره انتخاب کن.")
        return EDIT_COUNTRY

    user.country = country
    await save_user(user)

    if context.user_data.get("existing_profile"):
        await show_profile(update, user)
        return EDIT_MENU

    phone = context.user_data.get("pending_phone") or user.phone or "—"
    country_name = await get_user_country_name(user)
    await show_preview_and_ask_confirm(update.message, user, country_name, phone)
    return CONFIRM


async def edit_phone_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.contact:
        await update.message.reply_text("❌ لطفاً شماره را با دکمه ارسال شماره تماس ارسال کن.")
        return EDIT_PHONE

    phone = update.message.contact.phone_number
    user = await get_or_create_user(
        update.effective_user.id,
        update.effective_user.username
    )

    if context.user_data.get("existing_profile"):
        await save_phone(user, phone)

        await update.message.reply_text("✅ دریافت شد.", reply_markup=main_menu_keyboard)

        await show_profile(update, user)
        return EDIT_MENU

    phone = update.message.contact.phone_number
    context.user_data["pending_phone"] = phone

    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    country_name = await get_user_country_name(user)
    await show_preview_and_ask_confirm(update.message, user, country_name, phone)
    return CONFIRM


# ================= USER SERVICE =================
@sync_to_async
def get_user_by_tg_id(tg_id):
    return CustomUser.objects.filter(telegram_id=tg_id).first()

def is_profile_complete(user: CustomUser) -> bool:
    return bool(user and user.name and user.last_name and user.country_id and user.phone)

async def show_profile(update: Update, user: CustomUser):
    country_name = await get_user_country_name(user)
    text = (
        "👤 پروفایل شما:\n\n"
        f"👤 نام: {user.name or '—'}\n"
        f"👤 فامیلی: {user.last_name or '—'}\n"
        f"🌍 کشور: {country_name}\n"
        f"📞 شماره: {user.phone or '—'}\n\n"
        "برای ویرایش، یکی از گزینه‌های زیر را انتخاب کن:"
    )
    await update.message.reply_text(text, reply_markup=build_edit_inline_keyboard())

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
        reply_markup=main_menu_keyboard
    )

# ================= PROFILE ENTRY =================
async def profile(update, context):
    tg = update.effective_user

    existing_user = await get_user_by_tg_id(tg.id)

    if existing_user and is_profile_complete(existing_user):
        context.user_data["existing_profile"] = True
        context.user_data["pending_phone"] = existing_user.phone
        await show_profile(update, existing_user)
        return EDIT_MENU

    user = await get_or_create_user(tg.id, tg.username)
    context.user_data["existing_profile"] = False
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

    contact_button = KeyboardButton(
        text='ارسال شماره تماس',
        request_contact=True,
    )
    reply_markup = ReplyKeyboardMarkup(
        [[contact_button]],
        one_time_keyboard=True,
        resize_keyboard=True
    )
    await update.message.reply_text(
        "شماره تماس خودت رو ارسال کن!",
        reply_markup=reply_markup
    )
    return PHONE


# ================= PHONE HANDLER=================
async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(
        update.effective_user.id,
        update.effective_user.username
    )

    if not update.message or not update.message.contact:
        await update.message.reply_text("❌ لطفاً شماره رو با دکمه «ارسال شماره تماس» ارسال کن.")
        return PHONE

    phone = update.message.contact.phone_number

    context.user_data["pending_phone"] = phone

    country_name = await get_user_country_name(user)

    preview_text = (
        "🧾 پیش‌نمایش اطلاعات شما:\n\n"
        f"👤 نام: {user.name or '—'}\n"
        f"👤 فامیلی: {user.last_name or '—'}\n"
        f"🌍 کشور: {country_name}\n"
        f"📞 شماره: {phone}\n\n"
        "✅ مطمئنی همین اطلاعات ثبت بشه؟"
    )

    confirm_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("✅ تایید"), KeyboardButton("❌ اصلاح")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text(preview_text, reply_markup=confirm_keyboard)
    return CONFIRM


# ================= CONFIRM HANDLER=================
async def confirm_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(
        update.effective_user.id,
        update.effective_user.username
    )

    text = (update.message.text or "").strip()

    if text == "✅ تایید":
        pending_phone = context.user_data.get("pending_phone")
        if not pending_phone:
            await update.message.reply_text("❌ شماره‌ای برای تایید پیدا نکردم. دوباره شماره را ارسال کن.")
            contact_button = KeyboardButton(text='ارسال شماره تماس', request_contact=True)
            reply_markup = ReplyKeyboardMarkup([[contact_button]], one_time_keyboard=True, resize_keyboard=True)
            await update.message.reply_text("شماره تماس خودت رو ارسال کن!", reply_markup=reply_markup)
            return PHONE

        await save_phone(user, pending_phone)
        context.user_data.pop("pending_phone", None)

        country_name = await get_user_country_name(user)

        await update.message.reply_text(
            f"✅ اطلاعات شما ذخیره شد لطفا منتظر تایید پروفایل خود بمانید:\n"
            f"👤 نام: {user.name}\n"
            f"👤 فامیلی: {user.last_name}\n"
            f"🌍 کشور: {country_name}\n"
            f"شماره:{user.phone}\n",
            reply_markup=main_menu_keyboard
        )
        return ConversationHandler.END

    if text == "❌ اصلاح":
        await update.message.reply_text(
            "کدوم بخش رو می‌خوای اصلاح کنی؟",
            reply_markup=build_edit_inline_keyboard()
        )
        return EDIT_MENU

    await update.message.reply_text("❌ لطفاً یکی از گزینه‌ها را انتخاب کن: ✅ تایید یا ❌ اصلاح")
    return CONFIRM


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

    application.post_init = post_init

    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("profile", profile),
            MessageHandler(filters.Regex("^👤پروفایل$"), profile)
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_last_name)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country_selected)],
            PHONE: [MessageHandler(filters.CONTACT, get_phone)],

            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_profile)],

            EDIT_MENU: [CallbackQueryHandler(edit_menu_callback, pattern=r"^edit_(name|last|country|phone|back)$")],
            EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name_text)],
            EDIT_LAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_last_text)],
            EDIT_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_country_text)],
            EDIT_PHONE: [MessageHandler(filters.CONTACT, edit_phone_contact)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
        name="registration_conversation",
        allow_reentry=True,
    )
    application.add_handler(conv_handler)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search))

    application.add_handler(MessageHandler(filters.Regex("^👤پروفایل$"), profile))

    return application
