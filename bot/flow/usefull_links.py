
from html import escape
from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

BTN_USEFUL = "🔗لینک های مفید و نرخ ارز"


def _fmt_avg(v):
    try:
        return f"{int(v):,} تومان/واحد"
    except Exception:
        return "—"


@sync_to_async
def get_global_avg_deals_by_currency():
    # فعلاً نمونه
    return {"USD": None, "EUR": None, "AED": None}


async def useful_links_and_rates_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    from bot.handlers import build_main_menu_keyboard  # برای circular نبودن

    avgs = await get_global_avg_deals_by_currency()

    cur_fa = {"USD": "دلار", "EUR": "یورو", "AED": "درهم"}

    lines = []
    for cur in ["USD", "EUR", "AED"]:
        label = escape(cur_fa.get(cur, cur))
        avg = escape(_fmt_avg(avgs.get(cur)))
        lines.append(f"• {label} ({escape(cur)}): {avg}")

    text = (
            "🔗 لینک‌های مفید و نرخ ارز\n\n"
            "<b>📊 میانگین معاملات کل سیستم</b>\n"
            + "<br>".join(lines)
            + "<br><br>"
              "<b>🌍 نرخ ارز آنلاین</b><br>"
              '• <a href="https://www.bonbast.com">www.bonbast.com</a>'
    )

    await msg.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=build_main_menu_keyboard(),
        disable_web_page_preview=True,
    )


def get_useful_links_handlers():
    return [
        CommandHandler("useful", useful_links_and_rates_entry),
        MessageHandler(filters.TEXT & filters.Regex(rf"^{BTN_USEFUL}$"), useful_links_and_rates_entry),
    ]