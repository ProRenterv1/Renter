from .base import *

DEBUG = True
USE_S3 = False  # ensure local storage in tests

SECRET_KEY = os.environ.get("SECRET_KEY", "test-secret-key")

# SQLite for CI speed/simplicity if DATABASE_URL absent
if not os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test.db",
        }
    }

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}