# -*- mode: python -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = [], [], []
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "sounddevice", "_sounddevice_data",
            "av", "tokenizers"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += ["pynput.keyboard._win32", "pynput.mouse._win32"]

# The Whisper model fetched by build.ps1 ships beside the exe as models/base.en.
datas += [(str(root / "packaging" / "model-cache" / "base.en"), "models/base.en")]

a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="LocalDictation",
          console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="LocalDictation", upx=False)
