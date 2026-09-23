from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from .validators import http_url, image_url


class Profile(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False,
                                         validators=[MinValueValidator(1), MaxValueValidator(1)])
    name = models.CharField(max_length=200)
    tagline = models.CharField(max_length=300, blank=True)
    about = models.TextField()
    image = models.CharField(max_length=1000, validators=[image_url])
    logo = models.CharField(max_length=1000, validators=[image_url])
    email = models.CharField(max_length=254, help_text="Display text; obfuscated addresses are supported.")
    phone = models.CharField(max_length=80, blank=True)
    coding_challenges_url = models.URLField(max_length=1000, validators=[http_url], blank=True)
    footer_text = models.CharField(max_length=200)

    class Meta:
        verbose_name = "site profile"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="single_site_profile")]

    def __str__(self):
        return self.name


class OrderedContent(models.Model):
    order = models.PositiveIntegerField(default=0, help_text="Smaller numbers appear first.")
    is_visible = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["order", "pk"]


class SocialLink(OrderedContent):
    platform = models.CharField(max_length=20, unique=True, choices=[
        ("linkdein", "LinkedIn"), ("github", "GitHub"), ("instagram", "Instagram"),
    ])
    url = models.URLField(max_length=1000, validators=[http_url])

    def __str__(self):
        return self.get_platform_display()


class Experience(OrderedContent):
    kind = models.CharField(max_length=10, choices=[("work", "Work"), ("education", "Education")])
    position = models.CharField(max_length=250)
    company = models.CharField(max_length=250)
    location = models.CharField(max_length=200, blank=True)
    type = models.CharField(max_length=80, blank=True)
    duration = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.position} — {self.company}"


class Project(OrderedContent):
    title = models.CharField(max_length=250)
    image = models.CharField(max_length=1000, blank=True, validators=[image_url])
    description = models.TextField()
    techstack = models.CharField(max_length=500, blank=True)
    preview_link = models.URLField(max_length=1000, blank=True, validators=[http_url])
    github_link = models.URLField(max_length=1000, blank=True, validators=[http_url])

    def __str__(self):
        return self.title


class Technology(OrderedContent):
    name = models.CharField(max_length=100)
    group = models.CharField(max_length=10, choices=[("stack", "Tech stack"), ("tool", "Tools")])
    image = models.CharField(max_length=1000, validators=[image_url])

    class Meta(OrderedContent.Meta):
        verbose_name_plural = "technologies"

    def __str__(self):
        return self.name
