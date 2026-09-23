from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

http_url = URLValidator(schemes=["http", "https"])


def image_url(value):
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return
    try:
        http_url(value)
    except ValidationError:
        raise ValidationError("Use an http(s) image URL or a site-relative path starting with one slash.")
