from decouple import config
import os
from .base import *

DEBUG = config("DEBUG")
SECRET_KEY = config("SECRET_KEY")
API_TOKEN = config("API_TOKEN")

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
