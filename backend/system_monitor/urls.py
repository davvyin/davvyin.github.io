from django.urls import path

from . import views

app_name = "system_monitor"
urlpatterns = [
    path("", views.index, name="index"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/<path:path>", views.dashboard, name="proxy"),
]
