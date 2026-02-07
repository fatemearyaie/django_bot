import asyncio
import os
import django
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TestBot.settings.local")
django.setup()

from bot.handlers import build_application


def main():
    application = build_application(token=os.environ.get("API_TOKEN"))

    application.run_polling()

if __name__ == "__main__":
    main()
