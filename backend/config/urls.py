from django.contrib import admin
from django.urls import include, path, re_path
from portfolio import views
from visitor_analytics.views import collect

urlpatterns = [
    path("admin/analytics/", include("visitor_analytics.urls")),
    path("api/analytics/pageview/", collect, name="analytics_collect"),
    path("admin/system/", include("system_monitor.urls")),
    path("admin/camera/", views.camera_page, name="camera_page"),
    path("admin/camera/stream.mjpg", views.camera_stream, name="camera_stream"),
    path("admin/", admin.site.urls),
    path("api/content/", views.content, name="content"),
    path("healthz/", views.health, name="health"),
    re_path(r"^(?:about/?|projects/?|contact/?|technologies/?)?$", views.frontend, name="frontend"),
]
