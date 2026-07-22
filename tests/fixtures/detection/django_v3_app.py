"""Deprecated Django v3 patterns — each line triggers at least one DJG rule."""
from django.conf.urls import url

from django.utils.timezone import timezone


class Article(models.Model):
    title = models.CharField(max_length=200)


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "db.sqlite3",
        'CONN_MAX_AGE': 60,
    }
}

USE_L10N = True
CSRF_TRUSTED_ORIGINS = ["example.com"]

tz = timezone.utc

value1 = force_text(some_text)
value2 = smart_text(some_text)
msg = ugettext("Hello world")

form = modelform_factory(MyModel, fields="__all__", formfield_callback=my_cb)
