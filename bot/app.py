from telegram.ext import ApplicationBuilder
from django.conf import settings


def build_application():
    return (ApplicationBuilder().token(settings.API_TOKEN).build())
