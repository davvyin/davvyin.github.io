"""Camera capture command shared by streaming backends."""

import shutil


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
