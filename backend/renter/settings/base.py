import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY","dev-secret")
DEBUG = os.getenv("DJANGO_DEBUG","True")=="True"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS","localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
 "django.contrib.admin","django.contrib.auth","django.contrib.contenttypes",
 "django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles",
 "rest_framework","corsheaders","storages",
 "core",
]

MIDDLEWARE = [
 "corsheaders.middleware.CorsMiddleware",
 "django.middleware.security.SecurityMiddleware",
 "django.contrib.sessions.middleware.SessionMiddleware",
 "django.middleware.common.CommonMiddleware",
 "django.middleware.csrf.CsrfViewMiddleware",
 "django.contrib.auth.middleware.AuthenticationMiddleware",
 "django.contrib.messages.middleware.MessageMiddleware",
 "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],  # you can add BASE_DIR / "templates" later if you create one
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ROOT_URLCONF = "renter.urls"
WSGI_APPLICATION = "renter.wsgi.application"

DATABASES = { "default": dj_database_url.parse(os.getenv("DATABASE_URL","sqlite:///db.sqlite3"), conn_max_age=600) }

STATIC_URL = "/dj-static/"
STATIC_ROOT = BASE_DIR / "static"
MEDIA_URL  = "/dj-media/"
MEDIA_ROOT = BASE_DIR / "media"

REST_FRAMEWORK = {
 "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
 "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
}

CORS_ALLOW_ALL_ORIGINS = True

REDIS_URL = os.getenv("REDIS_URL","redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL