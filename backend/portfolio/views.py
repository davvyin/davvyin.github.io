from django.conf import settings
from django.db import connection, DatabaseError
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from django.shortcuts import render
if settings.CAMERA_STREAM_MODE == "exclusive":
    from camera.exclusive import multipart_frames, start_stream, stop_stream
else:
    from camera.broadcast import multipart_frames, start_stream, stop_stream
from .models import Experience, Profile, Project, SiteText, SocialLink, Technology


@require_safe
@never_cache
def content(request):
    profile = Profile.objects.first()
    if profile is None:
        return JsonResponse({"error": "Site content is not initialized. Run database migrations."}, status=503)
    experiences = list(Experience.objects.filter(is_visible=True))

    def history(kind):
        return [{"id": item.pk, "Position": item.position, "Company": item.company,
                 "Location": item.location, "Type": item.type, "Duration": item.duration}
                for item in experiences if item.kind == kind]

    return JsonResponse({
        "personalDetails": {"name": profile.name, "tagline": profile.tagline,
                            "about": profile.about, "img": profile.image},
        "logos": {"logogradient": profile.logo, "logo": profile.logo},
        "contactDetails": {"email": profile.email, "phone": profile.phone},
        "socialMediaUrl": {item.platform: item.url for item in SocialLink.objects.filter(is_visible=True)},
        "codingChallengesUrl": profile.coding_challenges_url,
        "footerText": profile.footer_text,
        "siteCopy": dict(SiteText.objects.values_list("key", "text")),
        "workDetails": history("work"),
        "eduDetails": history("education"),
        "projectDetails": [{"id": p.pk, "title": p.title, "image": p.image,
                            "description": p.description, "techstack": p.techstack,
                            "previewLink": p.preview_link, "githubLink": p.github_link}
                           for p in Project.objects.filter(is_visible=True)],
        "technologies": list(Technology.objects.filter(is_visible=True).values("id", "name", "group", "image")),
    })


@require_safe
@never_cache
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


@require_safe
@never_cache
def frontend(request):
    index = settings.FRONTEND_DIR / "index.html"
    if not index.is_file():
        return HttpResponse("Frontend build missing. Run npm ci and npm run build, or use npm start for development.", status=503, content_type="text/plain")
    return FileResponse(index.open("rb"), content_type="text/html")


@staff_member_required
@never_cache
def camera_page(request):
    return render(request, "portfolio/camera.html")


@staff_member_required
@never_cache
def camera_stream(request):
    stream, release = start_stream()
    if stream is None:
        return HttpResponse(
            "The camera is unavailable. Check that it is connected and rpicam-vid is installed.",
            status=503,
            content_type="text/plain",
        )
    response = StreamingHttpResponse(
        multipart_frames(stream, release),
        content_type="multipart/x-mixed-replace; boundary=frame",
    )
    response["X-Accel-Buffering"] = "no"
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    # Also stop the camera if the client disconnects before reading the stream.
    response._resource_closers.append(lambda: stop_stream(stream, release))
    return response
