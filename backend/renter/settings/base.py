from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import environ
from celery.schedules import crontab

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
ENABLE_OPERATOR = env.bool("ENABLE_OPERATOR", default=False)
OPS_ALLOWED_HOSTS = env.list("OPS_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
ENABLE_DJANGO_ADMIN = env.bool("ENABLE_DJANGO_ADMIN", default=False)

INSTALLED_APPS = [
    "rest_framework_simplejwt",
    "django_filters",
    "anymail",
    "operator_core",
    "operator_users",
    "operator_listings",
    "operator_bookings",
    "operator_finance",
    "operator_settings",
    "operator_disputes",
    "operator_promotions",
    "bookings.apps.BookingsConfig",
    "payments.apps.PaymentsConfig",
    "disputes",
    "chat.apps.ChatConfig",
    "identity",
    "users",
    "listings",
    "storage",
    "notifications",
    "reviews",
    "promotions.apps.PromotionsConfig",
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
    "operator_core.middleware.OpsOnlyRouteGatingMiddleware",
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
"DEFAULT_THROTTLE_CLASSES":[
    "rest_framework.throttling.AnonRateThrottle",
    "rest_framework.throttling.UserRateThrottle",
    "rest_framework.throttling.ScopedRateThrottle",
],
"DEFAULT_THROTTLE_RATES":{
    "anon": "100/hour",
    "user": "1000/hour",
    "operator": "6000/hour",
}
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

# ClamAV daemon connection settings
CLAMD_UNIX_SOCKET = env("CLAMD_UNIX_SOCKET", default=None)
CLAMD_HOST        = env("CLAMD_HOST", default="clamav")
CLAMD_PORT        = env.int("CLAMD_PORT", default=3310)

# --- Celery / Broker (overridable in tests)
REDIS_URL= env("REDIS_URL", default="redis://redis:6379/0")
CELERY_BROKER_URL= env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND= env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_BEAT_SCHEDULE = globals().get("CELERY_BEAT_SCHEDULE", {})
CELERY_BEAT_SCHEDULE.update(
    {
        "bookings_auto_expire_stale_daily": {
            "task": "bookings.auto_expire_stale_bookings",
            "schedule": crontab(hour=3, minute=0),
        },
        "bookings_auto_release_deposits_hourly": {
            "task": "bookings.auto_release_deposits",
            "schedule": crontab(minute=0),  # every hour on the hour
        },
        "bookings_authorize_start_day_deposits": {
            "task": "bookings.enqueue_deposit_authorizations",
            "schedule": crontab(minute="*/15"),  # every 15 minutes
        },
        "disputes_auto_flag_unanswered_rebuttals_hourly": {
            "task": "disputes.auto_flag_unanswered_rebuttals",
            "schedule": crontab(minute=0),  # every hour on the hour
        },
        "disputes_auto_close_missing_evidence_hourly": {
            "task": "disputes.auto_close_missing_evidence",
            "schedule": crontab(minute=15),
        },
        "disputes_rebuttal_reminders_hourly": {
            "task": "disputes.send_rebuttal_reminders",
            "schedule": crontab(minute=30),
        },
        "listings_purge_soft_deleted_nightly": {
            "task": "listings.purge_soft_deleted_listings",
            "schedule": crontab(hour=4, minute=0),
        },
        "notifications_detect_missing": {
            "task": "notifications.detect_missing_notifications",
            "schedule": crontab(hour=2, minute=15),
        },
        "operator_health_ping_minutely": {
            "task": "operator_health_ping",
            "schedule": crontab(),  # every minute
        },
    }
)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FRONTEND_ORIGIN = env("FRONTEND_ORIGIN", default="http://localhost:5173")

# --- Geocoding ---
GOOGLE_MAPS_API_KEY= env("GOOGLE_MAPS_API_KEY", default=None)
GEOCODE_CACHE_TTL= env.int("GEOCODE_CACHE_TTL", default=7 * 24 * 60 * 60)
GEOCODE_REQUEST_TIMEOUT= env.float("GEOCODE_REQUEST_TIMEOUT", default=5.0)

# --- Promotions ---
PROMOTION_PRICE_CENTS = env.int("PROMOTION_PRICE_CENTS", default=500)

# --- Booking fees ---
# Percentage surcharges expressed as Decimal fractions, e.g. 0.10 == 10%
BOOKING_RENTER_FEE_RATE = Decimal(
    env("BOOKING_RENTER_FEE_RATE", default="0.10")
)  # 10% renter-facing service fee

BOOKING_OWNER_FEE_RATE = Decimal(
    env("BOOKING_OWNER_FEE_RATE", default="0.05")
)  # 5% owner payout fee

# Instant payout fee: percentage of available balance charged for instant payouts
INSTANT_PAYOUT_FEE_RATE = Decimal(
    env("INSTANT_PAYOUT_FEE_RATE", default="0.03")
)  # 3% default instant payout fee

# --- Stripe ---
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_ENV = env("STRIPE_ENV", default="dev")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
CONNECT_BUSINESS_NAME = env("CONNECT_BUSINESS_NAME", default="Renter")
CONNECT_BUSINESS_URL = env("CONNECT_BUSINESS_URL", default=FRONTEND_ORIGIN)
CONNECT_BUSINESS_PRODUCT_DESCRIPTION = env(
    "CONNECT_BUSINESS_PRODUCT_DESCRIPTION",
    default="Peer-to-peer rentals platform",
)
CONNECT_BUSINESS_MCC = env("CONNECT_BUSINESS_MCC", default="7399")

# --- Identity / verification limits ---
UNVERIFIED_MAX_REPLACEMENT_CAD = Decimal(
    env("UNVERIFIED_MAX_REPLACEMENT_CAD", default="1000")
)
UNVERIFIED_MAX_DEPOSIT_CAD = Decimal(env("UNVERIFIED_MAX_DEPOSIT_CAD", default="700"))
UNVERIFIED_MAX_BOOKING_DAYS = env.int(
    "UNVERIFIED_MAX_BOOKING_DAYS",
    default=3,
)
VERIFIED_MAX_BOOKING_DAYS = env.int(
    "VERIFIED_MAX_BOOKING_DAYS",
    default=5,
)
