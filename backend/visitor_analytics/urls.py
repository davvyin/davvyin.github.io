from django.urls import path
from . import views

app_name = "visitor_analytics"
urlpatterns = [path("", views.dashboard, name="dashboard")]
