"""Private MJPEG streaming helpers for a Raspberry Pi camera."""

import shutil
import subprocess
import threading


FRAME_BOUNDARY = b"frame"
_STREAM_LOCK = threading.Lock()


def camera_command():
    executable = shutil.which("rpicam-vid")
    if not executable:
        return None
    return [
        executable,
        "--nopreview",
        "--timeout",
        "0",
        "--codec",
        "mjpeg",
        "--width",
        "1280",
        "--height",
        "720",
        "--framerate",
        "15",
        "--output",
        "-",
    ]


def jpeg_frames(stream):
    """Split concatenated JPEG images from rpicam-vid's stdout."""
    buffer = bytearray()
    while True:
        chunk = stream.read(4096)
        if not chunk:
            return
        buffer.extend(chunk)
        while True:
            start = buffer.find(b"\xff\xd8")
            if start < 0:
                # Keep one byte in case a marker is split across reads.
                buffer[:] = buffer[-1:]
                break
            if start:
                del buffer[:start]
            end = buffer.find(b"\xff\xd9", 2)
            if end < 0:
                break
            frame = bytes(buffer[: end + 2])
            del buffer[: end + 2]
            yield frame


def _release_once():
    released = False
    guard = threading.Lock()

    def release():
        nonlocal released
        with guard:
            if not released:
                released = True
                _STREAM_LOCK.release()

    return release


def start_stream():
    """Start the sole camera stream; return (process, release) or (None, None)."""
    command = camera_command()
    if command is None or not _STREAM_LOCK.acquire(blocking=False):
        return None, None
    release = _release_once()
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
            yield (
                b"--" + FRAME_BOUNDARY + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
                + frame
                + b"\r\n"
            )
    finally:
        stop_stream(process, release)
