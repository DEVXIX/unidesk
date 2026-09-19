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

# livekit ships its own 25 MB native library and cv2 a pile of DLLs; both are
# found by collect_all and by nothing else, so a build without this starts
# fine and then cannot take a call.
for package in ("materialyoucolor", "livekit", "sounddevice", "mss", "cv2"):
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
