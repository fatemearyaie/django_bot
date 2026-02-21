from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    BotCommand,
)
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatMemberStatus
from asgiref.sync import sync_to_async

from Users.models import CustomUser, Country


# ====== Channel Gate ======
REQUIRED_CHANNEL = "@excoinmarket"
CHANNEL_JOIN_URL = f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}"


# ====== States ======
(
    NAME, LAST_NAME, COUNTRY, PHONE,
    CONFIRM,
    EDIT_MENU, EDIT_NAME, EDIT_LAST, EDIT_COUNTRY, EDIT_PHONE
) = range(10)


# ====== Keyboards ======
def build_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("➕ثبت درخواست جدید")],
            [KeyboardButton("📥درخواست‌های من"), KeyboardButton("📬پیشنهادهای من")],
            [KeyboardButton("🔗لینک های مفید و نرخ ارز")],
            [KeyboardButton("👤پروفایل"), KeyboardButton("⁉️درباره ما")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def build_register_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 ثبت نام", callback_data="start_register")]
    ])


def build_edit_inline_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ ویرایش نام", callback_data="edit_name")],
            [InlineKeyboardButton("✏️ ویرایش فامیلی", callback_data="edit_last")],
            [InlineKeyboardButton("🌍 ویرایش کشور", callback_data="edit_country")],
            [InlineKeyboardButton("📞 ویرایش شماره", callback_data="edit_phone")],
            [InlineKeyboardButton("↩️ برگشت", callback_data="edit_back")],
        ]
    )


def build_confirm_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("✅ تایید"), KeyboardButton("❌ اصلاح")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def build_contact_keyboard():
    contact_button = KeyboardButton(text="ارسال شماره تماس", request_contact=True)
    return ReplyKeyboardMarkup([[contact_button]], one_time_keyboard=True, resize_keyboard=True)


# ====== DB Services (Async Safe) ======
@sync_to_async
def get_user_by_tg_id(tg_id: int):
    return CustomUser.objects.filter(telegram_id=tg_id).first()


@sync_to_async
def get_or_create_user(tg_id: int, tg_username: str | None):
    user, created = CustomUser.objects.get_or_create(
        telegram_id=tg_id,
        defaults={
            "telegram_username": tg_username,
            "username": tg_username or f"user_{tg_id}",
        },
    )
    if tg_username and user.telegram_username != tg_username:
        user.telegram_username = tg_username
        user.save(update_fields=["telegram_username"])
    return user


@sync_to_async
def save_user(user: CustomUser):
    user.save()


@sync_to_async
def get_available_countries():
    return list(Country.objects.filter(is_available=True))


@sync_to_async
def get_country_by_name(name: str):
    return Country.objects.get(name=name)


@sync_to_async
def get_user_country_name(user: CustomUser):
    return user.country.name if user.country else "نامشخص"


@sync_to_async
def save_phone(user: CustomUser, phone: str):
    user.phone = phone
    user.save(update_fields=["phone"])


def is_profile_complete(user: CustomUser) -> bool:
    return bool(user and user.name and user.last_name and user.country_id and user.phone)


# ====== Channel membership check ======
async def is_member_of_required_channel(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception:
        return False


# ====== Send helper (fix ReplyKeyboard in callbacks) ======
async def send_text(update: Update, text: str, reply_markup=None):
    if update.message:
        return await update.message.reply_text(text, reply_markup=reply_markup)
    if update.callback_query:
        return await update.effective_chat.send_message(text, reply_markup=reply_markup)
    return None


# ====== UI helpers ======
async def show_profile(update: Update, user: CustomUser):
    country_name = await get_user_country_name(user)
    text = (
        "👤 پروفایل شما:\n\n"
        f"👤 نام: {user.name or '—'}\n"
        f"👤 فامیلی: {user.last_name or '—'}\n"
        f"🌍 کشور: {country_name}\n"
        f"📞 شماره: {user.phone or '—'}\n\n"
        "برای ویرایش یکی از گزینه‌ها را بزن:"
    )
    await send_text(update, text, reply_markup=build_edit_inline_keyboard())


async def show_preview_and_ask_confirm(update: Update, user: CustomUser, country_name: str, phone: str):
    preview_text = (
        "🧾 پیش‌نمایش اطلاعات شما:\n\n"
        f"👤 نام: {user.name or '—'}\n"
        f"👤 فامیلی: {user.last_name or '—'}\n"
        f"🌍 کشور: {country_name}\n"
        f"📞 شماره: {phone}\n\n"
        "✅ مطمئنی همین اطلاعات ثبت بشه؟"
    )
    await send_text(update, preview_text, reply_markup=build_confirm_keyboard())


# ====== Entry: /profile or 👤پروفایل ======
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    existing = await get_user_by_tg_id(tg.id)

    if existing and is_profile_complete(existing):
        context.user_data["existing_profile"] = True
        context.user_data["pending_phone"] = existing.phone
        await show_profile(update, existing)
        return EDIT_MENU

    await get_or_create_user(tg.id, tg.username)
    context.user_data["existing_profile"] = False
    await send_text(update, "لطفاً اسم خودت رو وارد کن:", reply_markup=ReplyKeyboardRemove())
    return NAME


# ====== Start register inline button callback ======
async def start_register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["existing_profile"] = False
    await update.effective_chat.send_message("لطفاً اسم خودت رو وارد کن:", reply_markup=ReplyKeyboardRemove())
    return NAME


# ====== Registration Steps ======
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    user.name = (update.message.text or "").strip()
    await save_user(user)

    await send_text(update, "👤 فامیلی خودت رو وارد کن:")
    return LAST_NAME


async def get_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    user.last_name = (update.message.text or "").strip()
    await save_user(user)

    countries = await get_available_countries()
    keyboard = [[KeyboardButton(c.name)] for c in countries]
    await send_text(
        update,
        "🌍 کشور خودت رو انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return COUNTRY


async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    country_name = (update.message.text or "").strip()

    try:
        country = await get_country_by_name(country_name)
    except Exception:
        await send_text(update, "❌ کشور پیدا نشد، دوباره انتخاب کن.")
        return COUNTRY

    user.country = country
    await save_user(user)

    await send_text(update, "شماره تماس خودت رو ارسال کن!", reply_markup=build_contact_keyboard())
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)

    if not update.message or not update.message.contact:
        await send_text(update, "❌ لطفاً شماره رو فقط با دکمه «ارسال شماره تماس» ارسال کن.", reply_markup=build_contact_keyboard())
        return PHONE

    phone = update.message.contact.phone_number
    context.user_data["pending_phone"] = phone

    country_name = await get_user_country_name(user)
    await show_preview_and_ask_confirm(update, user, country_name, phone)
    return CONFIRM


# ====== Confirm Step ======
async def confirm_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    text = (update.message.text or "").strip()

    if text == "❌ اصلاح":
        await send_text(update, "کدوم بخش رو می‌خوای اصلاح کنی؟", reply_markup=build_edit_inline_keyboard())
        return EDIT_MENU

    if text != "✅ تایید":
        await send_text(update, "❌ لطفاً یکی از گزینه‌ها را بزن: ✅ تایید یا ❌ اصلاح", reply_markup=build_confirm_keyboard())
        return CONFIRM

    pending_phone = context.user_data.get("pending_phone")
    if not pending_phone:
        await send_text(update, "❌ شماره‌ای برای ثبت ندارم. دوباره شماره را ارسال کن.")
        await send_text(update, "شماره تماس خودت رو ارسال کن!", reply_markup=build_contact_keyboard())
        return PHONE

    ok = await is_member_of_required_channel(context.bot, update.effective_user.id)
    if not ok:
        join_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 عضویت در کانال", url=CHANNEL_JOIN_URL)],
            [InlineKeyboardButton("✅ عضو شدم، بررسی کن", callback_data="check_join")],
        ])
        await send_text(
            update,
            "❌ تا عضو کانال نشی نمی‌تونی از خدمات ربات استفاده کنی.\n"
            "اول عضو شو، بعد روی «✅ عضو شدم، بررسی کن» بزن.",
            reply_markup=join_keyboard,
        )
        return CONFIRM

    await save_phone(user, pending_phone)
    context.user_data.pop("pending_phone", None)

    await send_text(
        update,
        "✅ اطلاعات شما ذخیره شد. لطفاً منتظر تایید ادمین باشید.",
        reply_markup=build_main_menu_keyboard()
    )
    return ConversationHandler.END


# ====== check_join callback ======
async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ok = await is_member_of_required_channel(context.bot, query.from_user.id)
    if not ok:
        await update.effective_chat.send_message("❌ هنوز عضو کانال نیستی. اول عضو شو بعد دوباره بزن.")
        return CONFIRM

    user = await get_or_create_user(query.from_user.id, query.from_user.username)
    pending_phone = context.user_data.get("pending_phone")

    if not pending_phone:
        await update.effective_chat.send_message("❌ شماره‌ای برای ثبت ندارم. لطفاً دوباره شماره را ارسال کن.")
        await update.effective_chat.send_message("شماره تماس خودت رو ارسال کن!", reply_markup=build_contact_keyboard())
        return PHONE

    await save_phone(user, pending_phone)
    context.user_data.pop("pending_phone", None)

    await update.effective_chat.send_message(
        "✅ اطلاعات شما ذخیره شد. لطفاً منتظر تایید ادمین باشید.",
        reply_markup=build_main_menu_keyboard()
    )
    return ConversationHandler.END


# ====== Edit Menu callback (Inline buttons) ======
async def edit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "edit_back":
        if context.user_data.get("existing_profile"):
            user = await get_or_create_user(query.from_user.id, query.from_user.username)
            await show_profile(update, user)
            return EDIT_MENU

        await update.effective_chat.send_message("خب تایید می‌کنی یا اصلاح؟", reply_markup=build_confirm_keyboard())
        return CONFIRM

    if data == "edit_name":
        await update.effective_chat.send_message("✏️ نام جدید را وارد کن:")
        return EDIT_NAME

    if data == "edit_last":
        await update.effective_chat.send_message("✏️ فامیلی جدید را وارد کن:")
        return EDIT_LAST

    if data == "edit_country":
        countries = await get_available_countries()
        keyboard = [[KeyboardButton(c.name)] for c in countries]
        await update.effective_chat.send_message(
            "🌍 کشور جدید را انتخاب کن:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
        )
        return EDIT_COUNTRY

    if data == "edit_phone":
        await update.effective_chat.send_message("📞 شماره جدید را با دکمه زیر ارسال کن:", reply_markup=build_contact_keyboard())
        return EDIT_PHONE

    return EDIT_MENU


# ====== Edit handlers ======
async def edit_name_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    user.name = (update.message.text or "").strip()
    await save_user(user)

    if context.user_data.get("existing_profile"):
        await show_profile(update, user)
        return EDIT_MENU

    phone = context.user_data.get("pending_phone") or user.phone or "—"
    country_name = await get_user_country_name(user)
    await show_preview_and_ask_confirm(update, user, country_name, phone)
    return CONFIRM


async def edit_last_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    user.last_name = (update.message.text or "").strip()
    await save_user(user)

    if context.user_data.get("existing_profile"):
        await show_profile(update, user)
        return EDIT_MENU

    phone = context.user_data.get("pending_phone") or user.phone or "—"
    country_name = await get_user_country_name(user)
    await show_preview_and_ask_confirm(update, user, country_name, phone)
    return CONFIRM


async def edit_country_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    country_name_input = (update.message.text or "").strip()

    try:
        country = await get_country_by_name(country_name_input)
    except Exception:
        await send_text(update, "❌ کشور پیدا نشد، دوباره انتخاب کن.")
        return EDIT_COUNTRY

    user.country = country
    await save_user(user)

    if context.user_data.get("existing_profile"):
        await show_profile(update, user)
        return EDIT_MENU

    phone = context.user_data.get("pending_phone") or user.phone or "—"
    country_name = await get_user_country_name(user)
    await show_preview_and_ask_confirm(update, user, country_name, phone)
    return CONFIRM


async def edit_phone_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.contact:
        await send_text(update, "❌ شماره را فقط با دکمه ارسال شماره تماس ارسال کن.", reply_markup=build_contact_keyboard())
        return EDIT_PHONE

    phone = update.message.contact.phone_number
    user = await get_or_create_user(update.effective_user.id, update.effective_user.username)

    if context.user_data.get("existing_profile"):
        await save_phone(user, phone)
        await send_text(update, "✅ شماره جدید ذخیره شد.", reply_markup=build_main_menu_keyboard())
        await show_profile(update, user)
        return EDIT_MENU

    context.user_data["pending_phone"] = phone
    country_name = await get_user_country_name(user)
    await show_preview_and_ask_confirm(update, user, country_name, phone)
    return CONFIRM


# ====== Cancel ======
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_text(update, "❌ لغو شد.", reply_markup=build_main_menu_keyboard())
    return ConversationHandler.END


# ====== post_init commands ======
async def post_init(app):
    commands = [
        BotCommand("new_request", "درخواست جدید"),
        BotCommand("requests", "درخواست های من"),
        BotCommand("offers", "پیشنهادهای من"),
        BotCommand("profile", "پروفایل"),
    ]
    await app.bot.set_my_commands(commands)


def build_registration_conversation():
    return ConversationHandler(
        entry_points=[
            CommandHandler("profile", profile),
            MessageHandler(filters.Regex(r"^👤پروفایل$"), profile),
            CallbackQueryHandler(start_register_callback, pattern=r"^start_register$"),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_last_name)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country_selected)],
            PHONE: [MessageHandler(filters.CONTACT, get_phone)],
            CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_profile),
                CallbackQueryHandler(check_join_callback, pattern=r"^check_join$"),
            ],
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
