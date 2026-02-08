from django.apps import AppConfig


class TradeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = 'Trade'

    def ready(self):
        import Trade.signals.trade_signals