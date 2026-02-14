
import os
from datetime import timedelta
from pathlib import Path
from decouple import config
from celery.schedules import crontab
from django.templatetags.static import static
from django.utils.translation import gettext_lazy as _
from pathlib import Path

from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent.parent


ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [

    'unfold',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'Users',
    'Trade',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'TestBot.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates']
        ,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'TestBot.wsgi.application'


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'fa'
TIME_ZONE = 'Asia/Tehran'



STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')



AUTH_USER_MODEL = 'Users.CustomUser'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'




UNFOLD = {
    "DASHBOARD_CALLBACK": "TestBot.admin.dashboard.dashboard_context",
    "SCRIPTS": [lambda request: static("admin/js/chart.umd.min.js")],
    "STYLES": [lambda request: static("admin/css/rtl-actions-fix.css"),],



    "SITE_TITLE": "ExCoinMarket",
    "SITE_HEADER": "ExCoinMarket",
    "SITE_URL": "/",

    "THEME": None,
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,


    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": _("منوی ناوبری"),
                "separator": True,
                "collapsible": False,
                "items": [
                    {
                        "title": _("داشبورد"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                        "permission": lambda request: request.user.is_staff,
                    },
                ],
            },
            {
                "title": _("کاربران"),
                "separator": False,
                "collapsible": True,
                "items": [
                    {
                        "title": _("کاربران"),
                        "icon": "table_view",
                        "link": reverse_lazy("admin:Users_customuser_changelist"),
                    },
                    {
                        "title": _("کشور"),
                        "icon": "table_view",
                        "link": reverse_lazy("admin:Users_country_changelist"),
                    },
                ],
            },
            {
                "title": _("معاملات"),
                "separator": False,
                "collapsible": True,
                "items": [
                    {
                        "title": _("درخواست ها"),
                        "icon": "table_view",
                        "link": reverse_lazy("admin:Trade_traderequest_changelist"),
                    },
                    {
                        "title": _("پیشنهادها"),
                        "icon": "table_view",
                        "link": reverse_lazy("admin:Trade_tradeoffer_changelist"),
                    },
                ],
            },
        ],
    },

}
