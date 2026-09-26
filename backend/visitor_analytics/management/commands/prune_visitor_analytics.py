from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from visitor_analytics.models import PageView


class Command(BaseCommand):
    help = "Delete visitor page views older than ANALYTICS_RETENTION_DAYS (default 90)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=settings.ANALYTICS_RETENTION_DAYS)
        old = PageView.objects.filter(occurred_at__lt=cutoff)
        if options["dry_run"]:
            self.stdout.write(f"Would delete {old.count()} page views older than {cutoff.isoformat()}.")
            return
        count, _ = old.delete()
        self.stdout.write(f"Deleted {count} page views older than {cutoff.isoformat()}.")
