from django.db import models
from django.utils import timezone


class PageView(models.Model):
    event_id = models.UUIDField(unique=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    ip_address = models.GenericIPAddressField()
    path = models.CharField(max_length=64)
    referrer = models.CharField(max_length=253, blank=True)
    browser = models.CharField(max_length=24)
    device = models.CharField(max_length=16)

    class Meta:
        default_permissions = ()
        indexes = [models.Index(fields=["ip_address", "occurred_at"], name="analytics_ip_time")]
