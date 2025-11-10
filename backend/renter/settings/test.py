import os

os.environ.setdefault("USE_S3", "false") 
from .base import *

DEBUG = True
USE_S3 = False  # ensure local storage in tests
AWS_STORAGE_BUCKET_NAME = "test-bucket"
AWS_ACCESS_KEY_ID = "fake-access"
AWS_SECRET_ACCESS_KEY = "fake-secret"
CELERY_TASK_ALWAYS_EAGER=True 
CELERY_TASK_EAGER_PROPAGATES=True
STORAGE_SKIP_TASK_EXECUTION=True
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