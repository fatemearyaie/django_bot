
from html import escape
from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters


from asgiref.sync import sync_to_async
from django.db.models import Avg
from Trade.models.models import TradeOffer, TradeRequest

@sync_to_async
def get_system_avg_rates_by_currency():
    qs = (
        TradeOffer.objects
        .select_related("request")
        .filter(status=TradeOffer.Status.ACCEPTED)
        .values("request__currency")
        .annotate(avg_price=Avg("unit_price_irt"))
    )
    out = {row["request__currency"]: row["avg_price"] for row in qs}
    return out
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
            + "\n".join(lines)
            + "\n\n\n"
              "<b>🌍 نرخ ارز آنلاین</b>\n"
              '<a href="https://fa.navasan.net/">www.fa.navasan.net/</a>'
              '<a href="https://www.bonbast.com">www.bonbast.com</a>'
              '<a href="https://www.tgju.org">www.tgju.org</a>'
    )

    await msg.reply_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def get_useful_links_handlers():
    return [
        CommandHandler("useful", useful_links_and_rates_entry),
        MessageHandler(filters.TEXT & filters.Regex(rf"^{BTN_USEFUL}$"), useful_links_and_rates_entry),
    ]