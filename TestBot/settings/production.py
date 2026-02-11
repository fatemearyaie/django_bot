import os
from decouple import config
from .base import *
from corsheaders.defaults import default_headers

ALLOWED_HOSTS=['82.115.20.47','api.excoinmarket.shop','excoinmarket.shop','localhost','127.0.0.1','0.0.0.0']


DEBUG = config("DEBUG")
SECRET_KEY = config("SECRET_KEY")

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config("POSTGRES_DB"),
        "USER":config("POSTGRES_USER"),
        "PASSWORD":config("POSTGRES_PASSWORD"),
        "HOST":config("POSTGRES_HOST"),
        "PORT":config("POSTGRES_PORT","5432"),
    }
}



CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGIN = [
    'https://api.excoinmarket.shop',
]
CORS_ALLOW_HEADERS = list(default_headers) + ['x-csrftoken']


# --- Security hardening ---
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')