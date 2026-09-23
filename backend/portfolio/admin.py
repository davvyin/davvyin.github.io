from django.contrib import admin
from .models import Experience, Profile, Project, SocialLink, Technology

admin.site.site_header = "Portfolio administration"
admin.site.site_title = "Portfolio admin"
admin.site.index_title = "Manage your website"


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return super().has_add_permission(request) and not Profile.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class OrderedAdmin(admin.ModelAdmin):
    list_editable = ("order", "is_visible")
    list_filter = ("is_visible",)


@admin.register(Project)
class ProjectAdmin(OrderedAdmin):
    list_display = ("title", "order", "is_visible")
    search_fields = ("title", "description", "techstack")


@admin.register(Experience)
class ExperienceAdmin(OrderedAdmin):
    list_display = ("position", "company", "kind", "order", "is_visible")
    list_filter = ("kind", "is_visible")
    search_fields = ("position", "company")


@admin.register(Technology)
class TechnologyAdmin(OrderedAdmin):
    list_display = ("name", "group", "order", "is_visible")
    list_filter = ("group", "is_visible")
    search_fields = ("name",)


@admin.register(SocialLink)
class SocialLinkAdmin(OrderedAdmin):
    list_display = ("platform", "url", "order", "is_visible")
