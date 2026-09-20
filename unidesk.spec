# PyInstaller spec: python -m PyInstaller unidesk.spec  (run tools\build.ps1 instead)
from pathlib import Path

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

# The terminal and the storage widget: the ssh client, the screen it paints
# into, and the S3 client. Optional here as well as at runtime - a machine
# without one of them still builds, and the widget says what is missing.
#
# pyvda is which virtual desktop is showing; without it widgets show on all.
for package in ("paramiko", "pyte", "boto3", "botocore", "pyvda"):
    try:
        d, b, h = collect_all(package)
    except Exception as e:
        print(f"[unidesk.spec] {package} not installed, leaving it out: {e}")
        continue
    datas += d
    binaries += b
    hiddenimports += h

# materialyoucolor's celebi links against numpy's OWN repaired copy of the C++
# runtime, by the mangled name delvewheel gave it (msvcp140-<hash>.dll). numpy
# ships that in numpy.libs, which is on the DLL search path only because
# numpy's __init__ puts it there - and celebi is imported long before anything
# imports numpy. Frozen, that leaves it unfindable and unidesk dies on its
# first line with "DLL load failed while importing celebi".
#
# It only became reachable when numpy arrived with opencv. A copy goes where
# Windows always looks.
try:
    import numpy as _numpy
    _numpy_libs = Path(_numpy.__file__).resolve().parent.parent / "numpy.libs"
    binaries += [(str(dll), ".") for dll in _numpy_libs.glob("msvcp140*.dll")]
except Exception:
    pass

a = Analysis(
    ["unidesk.pyw"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "unittest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtMultimedia"],
    noarchive=False,
)
# botocore ships a description of all 435 AWS services, and the storage
# widget speaks to exactly one of them. Keeping only S3's costs nothing and
# saves seventeen megabytes of a download nobody asked to be bigger.
KEEP_AWS = ("botocore/data/s3/", "botocore/data/endpoints", "botocore/data/partitions",
            "botocore/data/_retry", "botocore/data/sdk-default")


def _wanted(entry):
    name = entry[0].replace("\\", "/")
    if not name.startswith("botocore/data/"):
        return True
    return any(name.startswith(keep) for keep in KEEP_AWS)


a.datas = [entry for entry in a.datas if _wanted(entry)]

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
