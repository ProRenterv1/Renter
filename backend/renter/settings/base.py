from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
for possible_base in (BASE_DIR, BASE_DIR.parent):
    env_file = possible_base / ".env"
    if env_file.exists():
        environ.Env.read_env(env_file)
        break

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-secret")
DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "http://localhost:8000"])

INSTALLED_APPS = [
    "rest_framework_simplejwt",
    "django_filters",
    "anymail",
    "bookings.apps.BookingsConfig",
    "payments.apps.PaymentsConfig",
    "users",
    "listings",
    "storage",
    "notifications",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "storages",
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

ROOT_URLCONF = "renter.urls"
WSGI_APPLICATION = "renter.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgresql://postgres:admin@localhost:5432/renter",
    )
}

STATIC_URL = "/dj-static/"
STATIC_ROOT = BASE_DIR / "static"
MEDIA_URL = "/dj-media/"
MEDIA_ROOT = BASE_DIR / "media"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
}

CORS_ALLOW_ALL_ORIGINS = True


AUTH_USER_MODEL = "users.User"
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "AUTH_COOKIE": "access",
    "AUTH_COOKIE_SECURE": True,
    "AUTH_COOKIE_HTTP_ONLY": True,
    "AUTH_COOKIE_SAMESITE": "Lax",
}

# --- Email / SMS ---
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="anymail.backends.sendgrid.EmailBackend",
)

ANYMAIL = {
    "SENDGRID_API_KEY": env("ANYMAIL_SENDGRID_API_KEY", default=None),
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@example.com")

TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID", default=None)
TWILIO_AUTH_TOKEN = env("TWILIO_AUTH_TOKEN", default=None)
TWILIO_FROM_NUMBER = env("TWILIO_FROM_NUMBER", default=None)

# --- S3 ---
USE_S3 = env.bool("USE_S3", default=False)

# Read AWS vars with safe defaults; only required if USE_S3=true
AWS_ACCESS_KEY_ID        = env("AWS_ACCESS_KEY_ID", default=None)
AWS_SECRET_ACCESS_KEY    = env("AWS_SECRET_ACCESS_KEY", default=None)
AWS_S3_REGION_NAME       = env("AWS_S3_REGION_NAME", default="us-east-1")
AWS_STORAGE_BUCKET_NAME  = env("AWS_STORAGE_BUCKET_NAME", default=None)
AWS_S3_ENDPOINT_URL      = env("AWS_S3_ENDPOINT_URL", default=None)
AWS_S3_FORCE_PATH_STYLE  = env.bool("AWS_S3_FORCE_PATH_STYLE", default=False)

S3_UPLOADS_PREFIX        = env("S3_UPLOADS_PREFIX", default="uploads/listings")
S3_MAX_UPLOAD_BYTES      = env.int("S3_MAX_UPLOAD_BYTES", default=15 * 1024 * 1024)

MEDIA_BASE_URL           = env("MEDIA_BASE_URL", default="")

from django.core.exceptions import ImproperlyConfigured

if USE_S3:
    if not AWS_STORAGE_BUCKET_NAME:
        raise ImproperlyConfigured("AWS_STORAGE_BUCKET_NAME is required when USE_S3=true")

    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    # Optional tuning
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    # Path-style/endpoint support (e.g., MinIO/LocalStack)
    if AWS_S3_ENDPOINT_URL:
        AWS_S3_ADDRESSING_STYLE = "path" if AWS_S3_FORCE_PATH_STYLE else "auto"
else:
    # Local filesystem for dev/tests/CI
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

# --- AV ---
AV_ENABLED              = env.bool("AV_ENABLED", default=True)
AV_ENGINE               = env("AV_ENGINE", default="clamd")
AV_DUMMY_INFECT_MARKER  = env("AV_DUMMY_INFECT_MARKER", default="EICAR")

# --- Celery / Broker (overridable in tests)
REDIS_URL               = env("REDIS_URL", default="redis://redis:6379/0")
CELERY_BROKER_URL       = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND   = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FRONTEND_ORIGIN = env("FRONTEND_ORIGIN", default="http://localhost:5173")

# --- Geocoding ---
GOOGLE_MAPS_API_KEY       = env("GOOGLE_MAPS_API_KEY", default=None)
GEOCODE_CACHE_TTL         = env.int("GEOCODE_CACHE_TTL", default=7 * 24 * 60 * 60)
GEOCODE_REQUEST_TIMEOUT   = env.float("GEOCODE_REQUEST_TIMEOUT", default=5.0)

# --- Booking fees ---
# Percentage surcharges expressed as Decimal fractions, e.g. 0.10 == 10%
BOOKING_RENTER_FEE_RATE = Decimal(
    env("BOOKING_RENTER_FEE_RATE", default="0.10")
)  # 10% renter-facing service fee

BOOKING_OWNER_FEE_RATE = Decimal(
    env("BOOKING_OWNER_FEE_RATE", default="0.05")
)  # 5% owner payout fee

# --- Stripe ---
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_ENV = env("STRIPE_ENV", default="dev")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", default="")
