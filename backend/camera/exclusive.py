"""Single-view MJPEG implementation retained as a simple fallback."""

import subprocess
import threading

from .command import camera_command
from .frames import jpeg_frames, multipart_frame

_STREAM_LOCK = threading.Lock()


def start_stream():
    """Start one camera stream; return (process, release) or (None, None)."""
    command = camera_command()
    if command is None or not _STREAM_LOCK.acquire(blocking=False):
        return None, None
    released = False
    release_guard = threading.Lock()

    def release():
        nonlocal released
        with release_guard:
            if not released:
                released = True
                _STREAM_LOCK.release()

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
    except OSError:
        release()
        return None, None
    return process, release


def stop_stream(process, release):
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
    finally:
        if process.stdout:
            process.stdout.close()
        release()


def multipart_frames(process, release):
    try:
        for frame in jpeg_frames(process.stdout):
            yield multipart_frame(frame)
    finally:
        stop_stream(process, release)
