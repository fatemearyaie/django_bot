import json
from datetime import timedelta
from django.db.models import Sum, BigIntegerField, Value, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal
from django.db.models import Count, Case, When, IntegerField
from django.db.models.functions import TruncMonth, TruncYear
from django.utils import timezone

from Users.models import CustomUser
from Trade.models.models import TradeRequest, TradeOffer


def _this_month_bounds():
    now = timezone.localtime(timezone.now())
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    return start, next_month


def _this_year_bounds():
    now = timezone.localtime(timezone.now())
    start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, start.replace(year=start.year + 1)


def _users_daily_series_last_n_days(n_days: int = 90):
    today = timezone.localdate()
    start = today - timedelta(days=n_days - 1)

    rows = (
        CustomUser.objects
        .filter(date_joined__gte=start, date_joined__lte=today)
        .values("date_joined")
        .annotate(value=Count("id"))
    )
    by_day = {r["date_joined"]: int(r["value"]) for r in rows}

    labels, values = [], []
    d = start
    while d <= today:
        labels.append(d.strftime("%Y-%m-%d"))
        values.append(by_day.get(d, 0))
        d += timedelta(days=1)

    return {"labels": labels, "values": values}


def _users_monthly_series_last_n_months(n_months: int = 12):
    today = timezone.localdate()
    current = today.replace(day=1)

    months = []
    for _ in range(n_months):
        months.append(current)
        if current.month == 1:
            current = current.replace(year=current.year - 1, month=12)
        else:
            current = current.replace(month=current.month - 1)

    months.reverse()

    rows = (
        CustomUser.objects
        .filter(date_joined__gte=months[0], date_joined__lte=today)
        .annotate(bucket=TruncMonth("date_joined"))
        .values("bucket")
        .annotate(value=Count("id"))
    )

    # bucket برای DateField معمولاً date برمی‌گرداند، نه datetime => .date() نزن
    by_month = {r["bucket"]: int(r["value"]) for r in rows}

    labels, values = [], []
    for m in months:
        labels.append(m.strftime("%Y-%m"))
        values.append(by_month.get(m, 0))

    return {"labels": labels, "values": values}


def _users_yearly_series_last_n_years(n_years: int = 5):
    today = timezone.localdate()
    start_year = today.year - (n_years - 1)

    rows = (
        CustomUser.objects
        .filter(date_joined__year__gte=start_year)
        .annotate(bucket=TruncYear("date_joined"))
        .values("bucket")
        .annotate(value=Count("id"))
    )

    # bucket ممکن است date یا datetime باشد؛ سال را با getattr امن می‌گیریم
    by_year = {}
    for r in rows:
        b = r["bucket"]
        y = getattr(b, "year", None)
        if y is not None:
            by_year[int(y)] = int(r["value"])

    labels, values = [], []
    for y in range(start_year, today.year + 1):
        labels.append(str(y))
        values.append(by_year.get(y, 0))

    return {"labels": labels, "values": values}


def dashboard_context(request, context):
    month_start_dt, month_next_dt = _this_month_bounds()
    year_start_dt, year_next_dt = _this_year_bounds()
    today_date = timezone.localdate()

    users_agg = CustomUser.objects.aggregate(
        today=Count(Case(When(date_joined=today_date, then=1), output_field=IntegerField())),
        month=Count(Case(When(date_joined__gte=month_start_dt, date_joined__lt=month_next_dt, then=1),
                         output_field=IntegerField())),
        year=Count(Case(When(date_joined__gte=year_start_dt, date_joined__lt=year_next_dt, then=1),
                        output_field=IntegerField())),
        total=Count("id"),
    )

    trade_requests_agg = TradeRequest.objects.aggregate(
        month=Count(Case(When(created_at__gte=month_start_dt, created_at__lt=month_next_dt, then=1),
                         output_field=IntegerField())),
        year=Count(Case(When(created_at__gte=year_start_dt, created_at__lt=year_next_dt, then=1),
                        output_field=IntegerField())),
        total=Count("id"),
    )

    offers_agg = TradeOffer.objects.aggregate(
        month=Count(Case(When(created_at__gte=month_start_dt, created_at__lt=month_next_dt, then=1),
                         output_field=IntegerField())),
        year=Count(Case(When(created_at__gte=year_start_dt, created_at__lt=year_next_dt, then=1),
                        output_field=IntegerField())),
        total=Count("id"),
    )
    # -------- TOTAL AMOUNTS --------

    # مجموع مبلغ ریکوئست‌ها (DecimalField)
    trade_requests_amount = TradeRequest.objects.aggregate(
        total_amount=Coalesce(
            Sum("amount"),
            Value(Decimal("0.0")),
            output_field=DecimalField(max_digits=12, decimal_places=3),
        )
    )

    # مجموع مبلغ آفرها (BigIntegerField)
    offers_amount = TradeOffer.objects.aggregate(
        total_amount=Coalesce(
            Sum("unit_price_irt"),
            Value(0),
            output_field=BigIntegerField(),
        )
    )


    users_daily = _users_daily_series_last_n_days(90)
    users_monthly = _users_monthly_series_last_n_months(12)
    users_yearly = _users_yearly_series_last_n_years(5)

    context["kpis"] = {
        "users": users_agg,
        "trade_requests": trade_requests_agg,
        "offers": offers_agg,
    }

    context["amounts"] = {
        "trade_requests_total": trade_requests_amount["total_amount"],
        "offers_total": offers_amount["total_amount"],
    }

    context["charts"] = {
        "users_series": json.dumps(
            {"daily": users_daily, "monthly": users_monthly, "yearly": users_yearly},
            ensure_ascii=False,
        )
    }

    return context
