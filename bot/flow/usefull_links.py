from html import escape

from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from django.db.models import Avg
from Trade.models.models import TradeOffer

BTN_USEFUL = "🔗لینک های مفید و نرخ ارز"


@sync_to_async
def get_system_avg_rates_by_currency():
    qs = (
        TradeOffer.objects
        .select_related("request")
        .filter(
            status=TradeOffer.Status.ACCEPTED,
            unit_price_irt__isnull=False,
            request__currency__isnull=False,
        )
        .values("request__currency")
        .annotate(avg_price=Avg("unit_price_irt"))
    )
    return {row["request__currency"]: row["avg_price"] for row in qs}


def _fmt_avg(v):
    try:
        if v is None:
            return "—"
        return f"{int(v):,} تومان"
    except Exception:
        return "—"


@sync_to_async
def get_global_avg_deals_by_currency():
    """
    میانگین معاملات کل سیستم بر اساس ارز (از روی TradeOffer های ACCEPTED)
    خروجی نمونه: {"USD": 12345, "EUR": 67890, "AED": None}
    """
    data = (
        TradeOffer.objects
        .select_related("request")
        .filter(
            status=TradeOffer.Status.ACCEPTED,
            unit_price_irt__isnull=False,
            request__currency__isnull=False,
        )
        .values("request__currency")
        .annotate(avg_price=Avg("unit_price_irt"))
    )

    out = {row["request__currency"]: row["avg_price"] for row in data}

    # برای اینکه همیشه هر سه ارز وجود داشته باشند
    for cur in ["USD", "EUR", "AED"]:
        out.setdefault(cur, None)

    return out


async def useful_links_and_rates_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    # ✅ این الان واقعا محاسبه می‌کنه
    avgs = await get_global_avg_deals_by_currency()
    # (اگر خواستی همون یکی تابع رو استفاده کنی: avgs = await get_system_avg_rates_by_currency())

    cur_fa = {"USD": "دلار", "EUR": "یورو", "AED": "درهم"}

    lines = []
    for cur in ["USD", "EUR", "AED"]:
        label = escape(cur_fa.get(cur, cur))
        avg = escape(_fmt_avg(avgs.get(cur)))
        lines.append(f"⚡️ {label} ({escape(cur)}): {avg}")

    text = (
        "<b>🔗 </b>دسترسی سریع به لینک‌های مفید \n\n"
        '🚩  <a href="https://www.bonbast.com/">bonbast.com</a>\n\n'
        '🚩  <a href="https://www.tgju.org/">tgju.org</a>\n\n'
        "<b>📊 میانگین معاملات کل سیستم</b>\n\n"
        + "\n\n".join(lines)
        + "\n\n\n\n"

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