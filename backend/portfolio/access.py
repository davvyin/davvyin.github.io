"""Permission checks shared by private admin tools."""
from functools import wraps
from time import monotonic
from types import SimpleNamespace

from django.contrib.auth import get_user
from django.contrib.auth.views import redirect_to_login
from django.db import DatabaseError
from django.http import HttpResponseForbidden
from django.urls import reverse


def admin_tool_required(permission):
    def decorate(view):
        @wraps(view)
        def protected(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated or not user.is_active:
                return redirect_to_login(request.get_full_path(), reverse("admin:login"))
            if not user.is_staff or not user.has_perm(permission):
                return HttpResponseForbidden("Your account does not have access to this admin tool.")
            return view(request, *args, **kwargs)
        return protected
    return decorate


def permission_checked_frames(request, frames, permission):
    """Revalidate a long-lived camera session as frames flow, every five seconds.

    Load a fresh session/user so logout, group changes, and permission revocation
    are not hidden by the request's cached user or permission set.
    """
    next_check = 0
    try:
        for frame in frames:
            now = monotonic()
            if now >= next_check:
                session = request.session.__class__(session_key=request.session.session_key)
                user = get_user(SimpleNamespace(session=session))
                if not (user.is_active and user.is_staff and user.has_perm(permission)):
                    break
                next_check = now + 5
            yield frame
    except DatabaseError:
        # Fail closed if access can no longer be verified.
        return
    finally:
        close = getattr(frames, "close", None)
        if close:
            close()
