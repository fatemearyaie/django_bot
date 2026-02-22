
from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from bot.handlers import build_main_menu_keyboard
from Trade.services.stat_service import get_global_avg_deals_by_currency


BTN_USEFUL = "🔗لینک های مفید و نرخ ارز"


def _fmt_avg(v: int | None) -> str:
    return f"{v:,} تومان/واحد" if isinstance(v, int) else "—"


async def useful_links_and_rates_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    avgs = await sync_to_async(get_global_avg_deals_by_currency)()

    cur_fa = {"USD": "دلار", "EUR": "یورو", "AED": "درهم"}
    lines = []
    for cur, avgp in avgs.items():
        lines.append(f"• {cur_fa.get(cur, cur)} ({cur}): {_fmt_avg(avgp)}")

    text = (
        "🔗 لینک‌های مفید و نرخ ارز\n\n"
        "📊 *میانگین معاملات کل سیستم* (فقط معاملات تایید شده)\n"
        + "\n".join(lines)
        + "\n\n"
        "—\n"
        "🔹\n️ سامانه خرید و فروش ارز"
        "@FExPal_channel"
        "🔹 نرخ لحظه ای ارز :"
        "www.bonbast.com"
        "https://fa.navasan.net/"
        "www.tgju.org"
    )

    await msg.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=build_main_menu_keyboard(),
        disable_web_page_preview=True,
    )


def get_useful_links_handlers():
    return [
        CommandHandler("useful", useful_links_and_rates_entry),
        MessageHandler(filters.Regex(rf"^{BTN_USEFUL}$"), useful_links_and_rates_entry),
    ]