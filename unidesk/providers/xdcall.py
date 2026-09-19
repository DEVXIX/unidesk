"""xD voice calls, held by the widget itself.

The whole call happens here: the ring, answering it, and the audio. Nothing is
handed to a browser, which is what "calls in the widget" has to mean if it is
to mean anything - a ring that opened a browser tab would be a notification
with extra steps.

How a call reaches you: xD has no socket for this. `GET /v1/calls/active` is
the whole mechanism - it answers `{"call": null}` or the one call you are in,
and the server's own comment calls that poll "the only thing a wedged client
can still reach". So this polls it, quickly while something is happening and
slowly while nothing is.

How the audio happens: `livekit.rtc` is a real client, not a wrapper around a
browser, and its PlatformAudio is WebRTC's own device module - it takes the
microphone, plays what arrives, and does echo cancellation, noise suppression
and gain control on the way through. That last part is not a luxury: capture
and play by hand and whatever the other person says is picked straight back up
and sent to them, so the call howls unless everybody is wearing headphones.

Three threads, and the rule that keeps them apart:

  * Qt's, which owns every property and signal here.
  * a polling thread, which only ever touches Qt through `_result`, a queued
    signal. Calling into Qt from a worker is what made the first version of the
    xD widget sit on "signing in" forever: a QTimer started off the GUI thread
    has no event loop to fire on.
  * an asyncio thread, where livekit lives. The Room is built inside that loop
    because it keeps whichever loop it was constructed on, and every event from
    the native side is delivered back to that one.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from .net import get_json, send_json
from .xd import API, SITE, _media, _read_session

TIMEOUT = 12

# How soon a ring can reach you is exactly this number, because the poll is the
# only notice xD gives. Six seconds was too long to wait for a telephone to
# start ringing. Only POST /v1/calls is throttled (ten a minute, for redials);
# asking whether anybody is calling is not, so this can afford to be brisk.
IDLE_POLL_MS = 3_000
LIVE_POLL_MS = 1_500

# The ring's own sample rate. The call's audio never passes through here -
# PlatformAudio owns the devices for that.
SAMPLE_RATE = 48_000


def _ring_tone() -> "object | None":
    """Half a second of the old two-tone ring, as float32 samples.

    Synthesised rather than shipped: it is two sine waves and an envelope, and
    a generated one cannot arrive as a missing file in a packaged build.
    """
    try:
        import numpy as np
    except ImportError:
        return None
    burst_len = int(SAMPLE_RATE * 0.35)
    gap = np.zeros(int(SAMPLE_RATE * 0.18), dtype=np.float32)
    t = np.arange(burst_len) / SAMPLE_RATE
    wave = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 480 * t)
    # Ramped edges. A square edge on a sine is a click, and a click at the top
    # of every ring is what makes one unbearable.
    edge = int(SAMPLE_RATE * 0.02)
    envelope = np.ones(burst_len, dtype=np.float32)
    envelope[:edge] = np.linspace(0, 1, edge)
    envelope[-edge:] = np.linspace(1, 0, edge)
    burst = (wave * envelope * 0.05).astype(np.float32)
    return np.concatenate([burst, gap, burst])



# How often a camera or a screen is sent. Fifteen is enough for a face and for
# somebody watching a window; higher costs bandwidth nobody notices the benefit
# of, and a screen grab already takes ~27 ms of that budget.
VIDEO_FPS = 15
# What a screen is scaled to before it goes out. A 4K desktop sent whole is
# 33 MB a frame before encoding, and the person watching it in a widget cannot
# see the difference.
SCREEN_WIDTH = 1280


class _Capture:
    """Something that produces frames, on its own thread, into a VideoSource.

    The frames go out as BGRA because that is what both sources already give:
    mss hands back BGRA straight from Windows, and OpenCV's BGR needs only an
    alpha channel added. Converting to I420 here would be work done twice -
    LiveKit's encoder does it anyway.
    """

    def __init__(self, source, rtc, width: int, height: int):
        self._source, self._rtc = source, rtc
        self._width, self._height = width, height
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        period = 1.0 / VIDEO_FPS
        try:
            for frame in self._frames():
                if self._stop.is_set():
                    break
                started = time.monotonic()
                try:
                    self._source.capture_frame(frame)
                except Exception:
                    break
                # Paced here rather than by the source: a video source is a
                # queue, not a clock, and feeding it as fast as the screen can
                # be grabbed only fills it.
                rest = period - (time.monotonic() - started)
                if rest > 0:
                    self._stop.wait(rest)
        except Exception as e:
            print(f"[unidesk] xD call video: {e}")

    def _frames(self):
        raise NotImplementedError


class _ScreenCapture(_Capture):
    """Your screen, scaled down, fifteen times a second."""

    @staticmethod
    def size():
        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[1]
        scale = min(1.0, SCREEN_WIDTH / monitor["width"])
        # Even dimensions: an encoder given an odd width has to pad it.
        return (int(monitor["width"] * scale) // 2 * 2, int(monitor["height"] * scale) // 2 * 2)

    def _frames(self):
        import cv2
        import mss
        import numpy as np

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            while not self._stop.is_set():
                shot = sct.grab(monitor)
                image = np.frombuffer(shot.raw, dtype=np.uint8).reshape(shot.height, shot.width, 4)
                if (shot.width, shot.height) != (self._width, self._height):
                    image = cv2.resize(image, (self._width, self._height), interpolation=cv2.INTER_AREA)
                yield self._rtc.VideoFrame(
                    self._width, self._height, self._rtc.VideoBufferType.BGRA, image.tobytes()
                )


class _WindowCapture(_Capture):
    """One window, asked to draw itself.

    Not the rectangle it occupies: see xdshare. A window that disappears ends
    the share rather than sending black - somebody closing what they were
    showing is the ordinary way a share ends.
    """

    def __init__(self, source, rtc, width: int, height: int, hwnd: int):
        super().__init__(source, rtc, width, height)
        self._hwnd = hwnd

    @staticmethod
    def size(hwnd: int):
        from . import xdshare

        width, height = xdshare.window_size(hwnd)
        if width <= 0:
            return (0, 0)
        scale = min(1.0, SCREEN_WIDTH / width)
        return (int(width * scale) // 2 * 2, int(height * scale) // 2 * 2)

    def _frames(self):
        import cv2
        import numpy as np

        from . import xdshare

        while not self._stop.is_set():
            got = xdshare.grab_window(self._hwnd)
            if got is None:
                return
            raw, width, height = got
            image = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)
            if (width, height) != (self._width, self._height):
                image = cv2.resize(image, (self._width, self._height), interpolation=cv2.INTER_AREA)
            yield self._rtc.VideoFrame(
                self._width, self._height, self._rtc.VideoBufferType.BGRA, image.tobytes()
            )


class _CameraCapture(_Capture):
    """Your webcam."""

    @staticmethod
    def size():
        return (640, 480)

    def _frames(self):
        import cv2
        import numpy as np

        # DirectShow rather than the default backend: on Windows the default
        # takes seconds to open a camera and sometimes never answers at all.
        camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not camera.isOpened():
            print("[unidesk] xD call: no camera")
            return
        try:
            while not self._stop.is_set():
                ok, frame = camera.read()
                if not ok:
                    break
                height, width = frame.shape[:2]
                if (width, height) != (self._width, self._height):
                    frame = cv2.resize(frame, (self._width, self._height), interpolation=cv2.INTER_AREA)
                bgra = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
                yield self._rtc.VideoFrame(
                    self._width, self._height, self._rtc.VideoBufferType.BGRA, bgra.tobytes()
                )
        finally:
            camera.release()


class CallFrames(QQuickImageProvider):
    """The last frame that arrived, for QML to draw.

    QML cannot be handed a buffer, and writing each frame to a file would be
    absurd at fifteen a second - so the frame is kept here and the widget asks
    for it by a url that changes every time one lands. The url has to change,
    or Qt serves the picture it already has.
    """

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._image = QImage()
        self._lock = threading.Lock()

    def put(self, image: QImage):
        with self._lock:
            self._image = image

    def requestImage(self, request_id, size, requested):
        with self._lock:
            image = self._image
        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image


class XDCall(QObject):
    """A call, from the ring to the last word of it."""

    changed = Signal()
    ringing = Signal()
    # Separate from `changed` on purpose: a frame lands fifteen times a second
    # and the whole call page must not rebind at that rate.
    videoChanged = Signal()
    _result = Signal(str, "QVariant")

    def __init__(self):
        super().__init__()
        self._call: dict = {}
        self._connected = False
        self._muted = False
        self._error = ""
        self._me = ""
        self._audio: "_Audio | None" = None
        self._ring_thread: threading.Thread | None = None
        self._ring_stop = threading.Event()
        self._last_uuid = ""
        self._declined: set[str] = set()
        self._since = 0.0
        self._share_name = ""
        self._frames = CallFrames()
        self._video_tick = 0
        self._video_kind = ""
        self._devices: dict | None = None
        self._input_id = ""
        self._output_id = ""
        # Ticks the duration while a call is up, and nothing the rest of the time.
        self._clock = QTimer(self, interval=1000, timeout=self.changed.emit)

        self._result.connect(self._on_result)
        self._poll = QTimer(self, interval=IDLE_POLL_MS, timeout=self.refresh)
        self._poll.start()

        # UNIDESK_FAKE_CALL=ringing|accepted: pretend somebody is calling, so the
        # card can be looked at without two accounts and a second machine.
        pretend = os.environ.get("UNIDESK_FAKE_CALL", "")
        if pretend:
            self._poll.stop()
            QTimer.singleShot(1200, lambda: self._absorb({
                "call": {
                    "uuid": "pretend",
                    "status": pretend,
                    "is_group": False,
                    "caller": {
                        "username": "chiikawa",
                        "display_name": "Amna ★",
                        "profile_picture": "https://github.com/DEVXIX.png?size=200",
                    },
                    "callee": {"username": "dev", "display_name": "dev"},
                }
            }))

    # ---- what QML reads ----------------------------------------------------------

    @Property("QVariant", notify=changed)
    def call(self):
        return self._call

    @Property(bool, notify=changed)
    def isRinging(self):
        """A call waiting to be answered - and one I did not start."""
        return bool(self._call) and self._call.get("status") == "ringing" and not self._call.get("mine")

    @Property(bool, notify=changed)
    def isOutgoing(self):
        return bool(self._call) and self._call.get("status") == "ringing" and bool(self._call.get("mine"))

    @Property(bool, notify=changed)
    def inCall(self):
        return bool(self._call) and self._call.get("status") == "accepted"

    @Property(bool, notify=changed)
    def connected(self):
        return self._connected

    @Property(bool, notify=changed)
    def muted(self):
        return self._muted

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(str, notify=changed)
    def duration(self):
        """How long this call has been up, as m:ss. Empty before it is answered."""
        if not self._since:
            return ""
        seconds = max(0, int(time.monotonic() - self._since))
        return f"{seconds // 60}:{seconds % 60:02d}"

    # ---- the devices, and how loud they are --------------------------------------

    def _enumerate(self) -> dict:
        """Microphones and speakers, asked once.

        Asking means creating a PlatformAudio, which takes the audio device
        module; two of those at once fight over the hardware. So this makes one,
        reads the lists, and closes it immediately - and never runs while a call
        holds one of its own.
        """
        if self._devices is not None:
            return self._devices
        found = {"inputs": [], "outputs": []}
        if self._audio is not None:
            return found
        try:
            from livekit import rtc

            platform_audio = rtc.PlatformAudio()
            try:
                found = {
                    "inputs": [{"id": d.id, "name": d.name} for d in platform_audio.recording_devices()],
                    "outputs": [{"id": d.id, "name": d.name} for d in platform_audio.playout_devices()],
                }
            finally:
                platform_audio.close()
        except Exception as e:
            print(f"[unidesk] xD call: could not list audio devices: {e}")
        self._devices = found
        return found

    @Property("QVariant", notify=changed)
    def inputs(self):
        return self._enumerate()["inputs"]

    @Property("QVariant", notify=changed)
    def outputs(self):
        return self._enumerate()["outputs"]

    @Property(str, notify=changed)
    def inputId(self):
        return self._input_id

    @Property(str, notify=changed)
    def outputId(self):
        return self._output_id

    @Slot(str)
    def setInput(self, device_id: str):
        self._input_id = str(device_id or "")
        if self._audio:
            self._audio.set_input(self._input_id)
        self.changed.emit()

    @Slot(str)
    def setOutput(self, device_id: str):
        self._output_id = str(device_id or "")
        if self._audio:
            self._audio.set_output(self._output_id)
        self.changed.emit()

    @Property(float, notify=changed)
    def volume(self):
        """How loud the call is.

        This is unidesk's own share of the mixer rather than the system volume:
        the call is the only thing unidesk plays, so its session volume is the
        call's volume, and turning it down does not quieten anything else.
        """
        session = self._own_session()
        if session is None:
            return 1.0
        try:
            return float(session.SimpleAudioVolume.GetMasterVolume())
        except Exception:
            return 1.0

    @Slot(float)
    def setVolume(self, value: float):
        session = self._own_session()
        if session is None:
            return
        try:
            session.SimpleAudioVolume.SetMasterVolume(max(0.0, min(1.0, float(value))), None)
        except Exception:
            pass
        self.changed.emit()

    def _own_session(self):
        try:
            import os as _os

            from pycaw.pycaw import AudioUtilities

            pid = _os.getpid()
            for session in AudioUtilities.GetAllSessions():
                if session.Process and session.Process.pid == pid:
                    return session
        except Exception:
            pass
        return None

    # ---- polling -----------------------------------------------------------------

    def _headers(self) -> dict:
        token = _read_session().get("token") or ""
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _work(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    @Slot()
    def refresh(self):
        headers = self._headers()
        if not headers:
            return

        def run():
            try:
                body = get_json(f"{API}/v1/calls/active", headers, timeout=TIMEOUT)
            except Exception:
                return
            self._result.emit("active", body if isinstance(body, dict) else {})

        self._work(run)

    def _on_result(self, kind: str, payload):
        """Everything a worker came back with, on the GUI thread."""
        data = payload if isinstance(payload, dict) else {}

        if kind == "active":
            self._absorb(data)
        elif kind == "frame":
            image = data.get("image")
            if isinstance(image, QImage):
                self._frames.put(image)
                self._video_tick += 1
                new_kind = str(data.get("kind") or "")
                if new_kind != self._video_kind:
                    self._video_kind = new_kind
                self.videoChanged.emit()
        elif kind == "video_gone":
            self._video_kind = ""
            self.videoChanged.emit()
        elif kind == "error":
            self._error = str(data.get("message") or "")
            self.changed.emit()

    def _absorb(self, data: dict):
        raw = data.get("call")
        call = raw if isinstance(raw, dict) else {}
        uuid = str(call.get("uuid") or "")

        # Somebody hung up, or there was never anything there.
        if not call or uuid in self._declined:
            if self._call:
                self._end_audio()
                self._call = {}
                self._last_uuid = ""
                self._stop_ring()
                self.changed.emit()
            self._poll.setInterval(IDLE_POLL_MS)
            return

        session_user = (_read_session().get("user") or "").lower()
        caller = call.get("caller") if isinstance(call.get("caller"), dict) else {}
        mine = str(caller.get("username") or "").lower() == session_user
        other = call.get("callee") if mine else caller
        other = other if isinstance(other, dict) else {}

        shaped = {
            "uuid": uuid,
            "status": str(call.get("status") or ""),
            "isGroup": bool(call.get("is_group")),
            "mine": mine,
            "name": str(other.get("display_name") or other.get("name") or other.get("username") or "someone"),
            "handle": str(other.get("username") or ""),
            "avatar": _media(other.get("profile_picture") or other.get("avatar_url")),
        }
        fresh = shaped != self._call
        self._call = shaped
        self._poll.setInterval(LIVE_POLL_MS)

        # The ring is raised once per call, not once per poll.
        if shaped["status"] == "ringing" and not mine and uuid != self._last_uuid:
            self._last_uuid = uuid
            self._start_ring()
            self.ringing.emit()
        if shaped["status"] != "ringing":
            self._stop_ring()

        # Accepted, and the server has handed over a seat: take it.
        url, token = data.get("livekit_url"), data.get("livekit_token")
        if shaped["status"] == "accepted" and isinstance(url, str) and isinstance(token, str) and not self._audio:
            self._start_audio(url, token)
        if shaped["status"] == "accepted" and not self._since:
            self._since = time.monotonic()
            self._clock.start()

        if fresh:
            self.changed.emit()

    # ---- the ring ----------------------------------------------------------------

    def _start_ring(self):
        if self._ring_thread and self._ring_thread.is_alive():
            return
        tone = _ring_tone()
        if tone is None:
            return
        self._ring_stop.clear()

        def run():
            try:
                import sounddevice as sd
            except Exception:
                return
            # Half a minute and then it gives up: a ring that never stops is a
            # ring somebody turns off for good.
            until = time.monotonic() + 30
            while not self._ring_stop.is_set() and time.monotonic() < until:
                try:
                    sd.play(tone, SAMPLE_RATE, blocking=False)
                except Exception:
                    return
                self._ring_stop.wait(3.0)
            try:
                sd.stop()
            except Exception:
                pass

        self._ring_thread = threading.Thread(target=run, daemon=True)
        self._ring_thread.start()

    def _stop_ring(self):
        self._ring_stop.set()

    # ---- answering, refusing, hanging up -----------------------------------------

    def _post(self, path: str, body: dict | None = None, then=None):
        headers = self._headers()
        if not headers:
            return

        def run():
            try:
                status, answer = send_json(f"{API}{path}", body or {}, headers, timeout=TIMEOUT)
            except Exception as e:
                self._result.emit("error", {"message": f"xD would not take that: {e}"})
                return
            if status >= 400:
                said = answer.get("message") if isinstance(answer, dict) else None
                self._result.emit("error", {"message": str(said or f"xD said no ({status}).")})
                return
            if then:
                then()

        self._work(run)

    @Slot()
    def answer(self):
        uuid = self._call.get("uuid")
        if not uuid:
            return
        self._stop_ring()
        if uuid == "pretend":
            # UNIDESK_FAKE_CALL: nothing to accept server-side, so it simply
            # becomes an accepted call with no audio behind it. Enough to look
            # at the page; not enough to talk to anybody.
            self._call = dict(self._call, status="accepted")
            self._since = time.monotonic()
            self._connected = True
            self._clock.start()
            self.changed.emit()
            return
        # The seat arrives on the next poll, which is deliberately soon.
        self._post(f"/v1/calls/{uuid}/accept", None, self.refresh)

    @Slot()
    def decline(self):
        uuid = self._call.get("uuid")
        if not uuid:
            return
        self._stop_ring()
        self._declined.add(str(uuid))
        self._post(f"/v1/calls/{uuid}/decline")
        self._call = {}
        self.changed.emit()

    @Slot()
    def hangUp(self):
        uuid = self._call.get("uuid")
        self._stop_ring()
        if uuid == "pretend":
            self._end_audio()
            self._call = {}
            self.changed.emit()
            return
        self._end_audio()
        if uuid:
            # A caller whose call is still ringing cancels it; anybody in one ends it.
            path = "cancel" if self.isOutgoing else "end"
            self._post(f"/v1/calls/{uuid}/{path}")
        self._call = {}
        self.changed.emit()

    @Slot(str)
    def callHandle(self, handle: str):
        """Ring somebody, by their xD name."""
        handle = str(handle).strip().lstrip("@")
        if not handle:
            return
        self._post("/v1/calls", {"username": handle}, self.refresh)

    @Property(bool, notify=changed)
    def cameraOn(self):
        return bool(self._audio and self._audio.publishing("camera"))

    @Property(bool, notify=changed)
    def sharingScreen(self):
        return bool(self._audio and self._audio.publishing("screen"))

    @Property(int, notify=videoChanged)
    def videoTick(self):
        """Counts frames. QML puts it in the image url so the picture reloads."""
        return self._video_tick

    @Property(str, notify=videoChanged)
    def videoKind(self):
        """"camera", "screen", or empty when nobody is sending anything."""
        return self._video_kind

    @Property("QVariant", notify=changed)
    def shareWindows(self):
        """Everything that could be shared, asked for fresh every time the
        picker opens - windows come and go while somebody decides."""
        from . import xdshare

        return xdshare.windows()

    @Property(str, notify=changed)
    def shareName(self):
        """What is being shared, so the call page can say so rather than just
        showing a lit button."""
        return self._share_name

    @Slot(str, str)
    def startShare(self, window_id: str, name: str):
        """Share one window, or the whole screen when the id is empty."""
        if not self._audio:
            return
        self._share_name = name or "your screen"
        self._audio.start_share(str(window_id or ""))
        QTimer.singleShot(700, self.changed.emit)
        self.changed.emit()

    @Slot()
    def stopShare(self):
        if self._audio:
            self._audio.stop_share()
        self._share_name = ""
        QTimer.singleShot(400, self.changed.emit)
        self.changed.emit()

    @Slot()
    def toggleCamera(self):
        if self._audio:
            self._audio.toggle_video("camera")
            QTimer.singleShot(600, self.changed.emit)

    @Slot()
    def toggleShare(self):
        if self.sharingScreen:
            self.stopShare()
        else:
            self.startShare("", "your whole screen")

    @Slot()
    def toggleMute(self):
        self._muted = not self._muted
        if self._audio:
            self._audio.set_muted(self._muted)
        self.changed.emit()

    @Slot()
    def openOnSite(self):
        import webbrowser

        webbrowser.open(f"{SITE}/messages")

    # ---- the audio ---------------------------------------------------------------

    def image_provider(self) -> CallFrames:
        """Handed to the QML engine so `image://xdcall/...` resolves."""
        return self._frames

    def _start_audio(self, url: str, token: str):
        self._audio = _Audio(
            url,
            token,
            on_state=lambda live: self._result.emit("audio", {"live": live}),
            on_frame=lambda image, kind: self._result.emit("frame", {"image": image, "kind": kind}),
            on_video_gone=lambda: self._result.emit("video_gone", {}),
            input_id=self._input_id,
            output_id=self._output_id,
        )
        self._audio.start()
        self._connected = True
        self.changed.emit()

    def _end_audio(self):
        self._share_name = ""
        self._clock.stop()
        self._since = 0.0
        if self._audio:
            self._audio.stop()
            self._audio = None
        self._connected = False
        self._muted = False


class _Audio:
    """One LiveKit room, with the real microphone and speakers on it.

    This uses livekit's PlatformAudio rather than moving samples by hand, and
    the reason is echo cancellation. Capturing from the microphone and playing
    into the speakers yourself means whatever the other person says is picked
    straight back up and sent to them - the call howls, unless everybody wears
    headphones. PlatformAudio is WebRTC's own device module: it captures, it
    plays what arrives, and it does AEC, noise suppression and gain control on
    the way through.

    It holds real hardware, so both the source and the module are closed on the
    way out. The docstrings warn about this repeatedly: a source left to the
    garbage collector leaves the microphone claimed, and the next call finds it
    taken.

    livekit is asyncio and Qt is not, so this owns a loop on its own thread and
    the only things crossing over are a url, a token, and a mute flag.
    """

    def __init__(
        self,
        url: str,
        token: str,
        on_state=None,
        input_id: str = "",
        output_id: str = "",
        on_frame=None,
        on_video_gone=None,
    ):
        self._url, self._token = url, token
        self._on_state = on_state
        self._on_frame, self._on_video_gone = on_frame, on_video_gone
        self._input_id, self._output_id = input_id, output_id
        self._platform_audio = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._track = None
        self._stopping = threading.Event()
        # kind -> {"capture": _Capture, "publication": LocalTrackPublication}
        self._video: dict = {}
        self._room = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stopping.set()
        loop = self._loop
        if loop and loop.is_running():
            # Waking the loop is what ends the session; the close-down runs in
            # the coroutine's own finally, where the handles belong.
            loop.call_soon_threadsafe(lambda: None)

    def set_muted(self, muted: bool):
        """Mute the published track rather than stopping the capture.

        The room is told, so the other side can see it: a microphone that has
        simply gone quiet is indistinguishable from one that has broken.
        """
        track = self._track
        if track is None:
            return
        try:
            track.mute() if muted else track.unmute()
        except Exception:
            pass

    def set_input(self, device_id: str):
        """Change the microphone mid-call, if the device module will take it."""
        self._input_id = device_id
        self._apply_device("recording", device_id)

    def set_output(self, device_id: str):
        self._output_id = device_id
        self._apply_device("playout", device_id)

    def _apply_device(self, which: str, device_id: str):
        platform_audio = self._platform_audio
        if platform_audio is None or not device_id:
            return
        try:
            setter = getattr(platform_audio, f"set_{which}_device")
            setter(device_id)
        except Exception as e:
            # The docstrings say to choose before connecting, so a refusal here
            # is expected rather than broken: the choice is kept and used on the
            # next call.
            print(f"[unidesk] xD call: the {which} device will change on the next call ({e})")

    def publishing(self, kind: str) -> bool:
        return kind in self._video

    def start_share(self, window_id: str):
        """Begin sharing: one window when given an id, the whole screen when not."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self._start_share(window_id), loop)

    def stop_share(self):
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self._stop_kind("screen"), loop)

    async def _start_share(self, window_id: str):
        from livekit import rtc

        await self._stop_kind("screen")
        room = self._room
        if room is None:
            return
        try:
            if window_id:
                hwnd = int(window_id)
                width, height = _WindowCapture.size(hwnd)
                if width <= 0:
                    return
                maker = lambda source: _WindowCapture(source, rtc, width, height, hwnd)  # noqa: E731
            else:
                width, height = _ScreenCapture.size()
                maker = lambda source: _ScreenCapture(source, rtc, width, height)  # noqa: E731

            source = rtc.VideoSource(width, height, is_screencast=True)
            track = rtc.LocalVideoTrack.create_video_track("screen", source)
            publication = await room.local_participant.publish_track(
                track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_SCREENSHARE)
            )
            capture = maker(source)
            capture.start()
            self._video["screen"] = {"capture": capture, "publication": publication, "source": source}
        except Exception as e:
            print(f"[unidesk] xD call: could not share that: {e}")

    async def _stop_kind(self, kind: str):
        running = self._video.pop(kind, None)
        if not running:
            return
        running["capture"].stop()
        room = self._room
        if room is not None:
            try:
                await room.local_participant.unpublish_track(running["publication"].sid)
            except Exception:
                pass

    def toggle_video(self, kind: str):
        """Start or stop sending the camera, or the screen.

        Driven from the GUI thread, done on the loop: everything livekit owns
        belongs to the loop it was built on.
        """
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self._toggle_video(kind), loop)

    async def _toggle_video(self, kind: str):
        from livekit import rtc

        room = self._room
        if room is None:
            return

        if kind in self._video:
            await self._stop_kind(kind)
            return

        try:
            maker = _ScreenCapture if kind == "screen" else _CameraCapture
            width, height = maker.size()
            source = rtc.VideoSource(width, height, is_screencast=(kind == "screen"))
            track = rtc.LocalVideoTrack.create_video_track(kind, source)
            publication = await room.local_participant.publish_track(
                track,
                rtc.TrackPublishOptions(
                    source=rtc.TrackSource.SOURCE_SCREENSHARE
                    if kind == "screen"
                    else rtc.TrackSource.SOURCE_CAMERA
                ),
            )
            capture = maker(source, rtc, width, height)
            capture.start()
            self._video[kind] = {"capture": capture, "publication": publication, "source": source}
        except Exception as e:
            print(f"[unidesk] xD call: could not send the {kind}: {e}")

    async def _watch(self, track, kind: str):
        """Somebody else's camera or screen, frame by frame, into a QImage.

        RGBA is asked for rather than converted here: the stream will hand over
        whatever format is wanted, and QImage reads RGBA directly - so nothing
        in between has to know how I420 is laid out.
        """
        from livekit import rtc

        stream = rtc.VideoStream.from_track(track=track, format=rtc.VideoBufferType.RGBA)
        try:
            async for event in stream:
                if self._stopping.is_set():
                    break
                frame = event.frame
                if not self._on_frame:
                    continue
                # copy(), because the frame's buffer belongs to the stream and
                # is reused the moment this coroutine yields.
                image = QImage(
                    bytes(frame.data), frame.width, frame.height, QImage.Format.Format_RGBA8888
                ).copy()
                self._on_frame(image, kind)
        except Exception as e:
            print(f"[unidesk] xD call: stopped watching the {kind}: {e}")
        finally:
            try:
                await stream.aclose()
            except Exception:
                pass
            if self._on_video_gone:
                self._on_video_gone()

    def _run(self):
        try:
            asyncio.run(self._session())
        except Exception as e:
            print(f"[unidesk] xD call audio: {e}")

    async def _session(self):
        from livekit import rtc

        self._loop = asyncio.get_running_loop()
        # Built inside the running loop on purpose: Room captures whichever
        # loop it is constructed on, and every event from the native side is
        # delivered back to that one. Built anywhere else, nothing ever fires.
        room = rtc.Room()
        self._room = room
        platform_audio = None
        source = None

        try:
            await room.connect(self._url, self._token, rtc.RoomOptions(auto_subscribe=True))

            platform_audio = rtc.PlatformAudio()
            self._platform_audio = platform_audio
            # Chosen before connecting, which is when the device module reads it.
            for which, device_id in (("recording", self._input_id), ("playout", self._output_id)):
                self._apply_device(which, device_id)
            source = platform_audio.create_audio_source(
                rtc.PlatformAudioOptions(
                    echo_cancellation=True,
                    noise_suppression=True,
                    auto_gain_control=True,
                )
            )
            track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
            self._track = track
            await room.local_participant.publish_track(
                track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            )

            if self._on_state:
                self._on_state(True)

            # Nothing to pump: the device module captures and plays on its own.
            # This only waits for somebody to hang up.
            while not self._stopping.is_set() and room.isconnected():
                await asyncio.sleep(0.2)
        finally:
            self._track = None
            # Cameras and screen grabs are threads holding hardware; they stop
            # before anything else goes.
            for running in list(self._video.values()):
                running["capture"].stop()
            self._video.clear()
            self._room = None
            self._platform_audio = None
            # Hardware first, and in this order: the source is what holds the
            # microphone. Left to the garbage collector, the next call finds the
            # device already claimed.
            for closing in (source, platform_audio):
                try:
                    if closing is not None:
                        closing.close()
                except Exception:
                    pass
            try:
                await room.disconnect()
            except Exception:
                pass
            if self._on_state:
                self._on_state(False)
