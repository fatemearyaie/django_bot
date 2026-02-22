# Trade/services/stats_service.py

from django.db.models import Avg
from Trade.models.models import TradeOffer, TradeRequest


def get_global_avg_deals_by_currency():
    currencies = [c[0] for c in TradeRequest.Currency.choices]

    qs = (
        TradeOffer.objects
        .filter(status=TradeOffer.Status.ACCEPTED)
        .values("request__currency")
        .annotate(avg_price=Avg("unit_price_irt"))
    )
    mp = {row["request__currency"]: row["avg_price"] for row in qs}

    def _to_int(v):
        return int(v) if v is not None else None

    return {cur: _to_int(mp.get(cur)) for cur in currencies}