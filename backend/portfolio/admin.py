from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User
from .models import Experience, Profile, Project, SiteText, SocialLink, Technology

admin.site.site_header = "Portfolio administration"
admin.site.site_title = "Portfolio admin"
admin.site.index_title = "Manage your website"
admin.site.index_template = "portfolio/admin_index.html"


class SuperuserAccountManagement:
    """Only owners can grant permissions or change users/groups, even if a
    staff account is accidentally assigned auth model-edit permissions.
    """

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class ManagedUserAdmin(SuperuserAccountManagement, UserAdmin):
    pass


@admin.register(Group)
class ManagedGroupAdmin(SuperuserAccountManagement, GroupAdmin):
    pass


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


@admin.register(SiteText)
class SiteTextAdmin(admin.ModelAdmin):
    list_display = ("get_key_display", "text")
    search_fields = ("key", "text")
    list_per_page = 50
