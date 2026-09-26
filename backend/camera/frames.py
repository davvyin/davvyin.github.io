"""Helpers for parsing and framing the camera's MJPEG output."""

FRAME_BOUNDARY = b"frame"


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


def multipart_frame(frame):
    return (
        b"--" + FRAME_BOUNDARY + b"\r\n"
        b"Content-Type: image/jpeg\r\n"
        + f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
        + frame
        + b"\r\n"
    )
