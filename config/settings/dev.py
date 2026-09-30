from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS += ["django_extensions"]  # noqa: F405

# Simpler/faster password hashing for local dev & tests
if env("USE_SQLITE_FOR_DEV", default=False, cast=bool):  # noqa: F405
    DATABASES = {  # noqa: F405
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)  # noqa: F405
