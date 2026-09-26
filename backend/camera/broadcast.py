"""Share one live MJPEG capture among multiple independent HTTP viewers.

The reader keeps only the newest frame. A slow client skips frames rather than
building an unbounded queue, keeping latency and memory use bounded.
"""

import subprocess
import threading

from .command import camera_command
from .frames import jpeg_frames, multipart_frame


class _Subscription:
    def __init__(self, broadcaster, generation):
        self.broadcaster = broadcaster
        self.generation = generation
        self.sequence = 0

    def next_frame(self):
        return self.broadcaster.next_frame(self)


class _Broadcaster:
    def __init__(self):
        self.condition = threading.Condition()
        self.process = None
        self.reader = None
        self.generation = 0
        self.sequence = 0
        self.latest_frame = None
        self.subscribers = 0

    def subscribe(self):
        command = camera_command()
        if command is None:
            return None
        with self.condition:
            if self.process is None:
                try:
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        bufsize=0,
                    )
                except OSError:
                    return None
                self.generation += 1
                generation = self.generation
                self.process = process
                self.sequence = 0
                self.latest_frame = None
                self.reader = threading.Thread(
                    target=self._read_frames,
                    args=(process, generation),
                    name="camera-mjpeg-reader",
                    daemon=True,
                )
                self.reader.start()
            self.subscribers += 1
            return _Subscription(self, self.generation)

    def _read_frames(self, process, generation):
        try:
            for frame in jpeg_frames(process.stdout):
                with self.condition:
                    if generation != self.generation or process is not self.process:
                        return
                    self.sequence += 1
                    self.latest_frame = frame
                    self.condition.notify_all()
        finally:
            with self.condition:
                self.condition.notify_all()

    def next_frame(self, subscription):
        with self.condition:
            self.condition.wait_for(
                lambda: (
                    subscription.generation != self.generation
                    or (self.sequence > subscription.sequence and self.latest_frame is not None)
                    or self.process is None
                    or self.process.poll() is not None
                ),
                timeout=5,
            )
            if subscription.generation != self.generation or self.process is None:
                return None
            if self.latest_frame is None or self.sequence <= subscription.sequence:
                return None
            subscription.sequence = self.sequence
            return self.latest_frame

    def unsubscribe(self, subscription):
        process = None
        reader = None
        with self.condition:
            if subscription.generation != self.generation:
                return
            self.subscribers = max(0, self.subscribers - 1)
            if self.subscribers == 0 and self.process is not None:
                process = self.process
                reader = self.reader
                self.process = None
                self.reader = None
                self.latest_frame = None
                self.generation += 1
                self.condition.notify_all()
        if process is not None:
            _stop_process(process)
            if reader is not None and reader is not threading.current_thread():
                reader.join(timeout=2)


def _stop_process(process):
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


_BROADCASTER = _Broadcaster()


def start_stream():
    """Subscribe a viewer; return (subscription, release) or (None, None)."""
    subscription = _BROADCASTER.subscribe()
    if subscription is None:
        return None, None
    released = False
    guard = threading.Lock()

    def release():
        nonlocal released
        with guard:
            if released:
                return
            released = True
        _BROADCASTER.unsubscribe(subscription)

    return subscription, release


def stop_stream(subscription, release):
    release()


def multipart_frames(subscription, release):
    try:
        while True:
            frame = subscription.next_frame()
            if frame is None:
                return
            yield multipart_frame(frame)
    finally:
        release()
