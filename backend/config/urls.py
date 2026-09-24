from django.contrib import admin
from django.urls import path, re_path
from portfolio import views

urlpatterns = [
    path("admin/camera/", views.camera_page, name="camera_page"),
    path("admin/camera/stream.mjpg", views.camera_stream, name="camera_stream"),
    path("admin/", admin.site.urls),
    path("api/content/", views.content, name="content"),
    path("healthz/", views.health, name="health"),
    re_path(r"^(?:about/?|projects/?|contact/?|technologies/?)?$", views.frontend, name="frontend"),
]
