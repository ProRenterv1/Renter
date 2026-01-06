import os

os.environ.setdefault("USE_S3", "false")
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"
from .base import *

DEBUG = True
USE_S3 = False  # ensure local storage in tests
AWS_STORAGE_BUCKET_NAME = "test-bucket"
AWS_ACCESS_KEY_ID = "fake-access"
AWS_SECRET_ACCESS_KEY = "fake-secret"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
STORAGE_SKIP_TASK_EXECUTION = True
SECRET_KEY = os.environ.get("SECRET_KEY", "test-secret-key")

# Prefer TEST_DATABASE_URL if provided; otherwise always fall back to local SQLite so pytest
# does not need a running Postgres container/host (regardless of DATABASE_URL in .env).
# if not env.db("DATABASE_URL", default=None):
DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test.db",
        }
    }

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Disable API throttling in tests to avoid flaky rate limits.
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon": "100000/hour",
    "user": "100000/hour",
    "operator": "100000/hour",
}
