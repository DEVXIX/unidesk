# PyInstaller spec: python -m PyInstaller unidesk.spec  (run tools\build.ps1 instead)
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("unidesk/qml", "unidesk/qml"),
    ("unidesk/fonts", "unidesk/fonts"),
    ("unidesk/defaults", "unidesk/defaults"),
    ("build/media-bridge", "media-bridge"),
]
binaries = []
hiddenimports = collect_submodules("comtypes.gen") + collect_submodules("pycaw") + ["truststore", "pylnk3", "psutil"]

# The call's native libraries, each of which hides somewhere collect_all only
# finds if it is named exactly right:
#   livekit.rtc        - `livekit` is a NAMESPACE package (no __init__), so
#                        collecting "livekit" finds nothing and the 24 MB
#                        livekit_ffi.dll is silently left out.
#   _sounddevice_data  - sounddevice is a single module, not a package, and
#                        PortAudio lives in this separate one. Without it there
#                        is no ring.
#   cv2                - a pile of its own DLLs.
# A build missing any of these starts perfectly and then cannot take a call,
# which is the worst way for a dependency to be absent.
for package in ("materialyoucolor", "livekit.rtc", "_sounddevice_data", "sounddevice", "cv2"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["unidesk.pyw"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "unittest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtMultimedia"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="unidesk",
    icon="build/unidesk.ico",
    console=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="unidesk")
