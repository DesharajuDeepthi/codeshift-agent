"""Django v4 compatible patterns — should not trigger any DJG rules."""
from django.urls import path, re_path

from django.utils.encoding import force_str, smart_str
from django.utils.translation import gettext, gettext_lazy

import datetime

value = force_str("hello")
label = smart_str("label")
message = gettext("Hello world")
lazy_label = gettext_lazy("Label")
tz = datetime.timezone(datetime.timedelta(0))

urlpatterns = [
    path("home/", views.home),
    re_path(r"^archive/", views.archive),
]
