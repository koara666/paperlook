# PyInstaller spec for the Windows desktop app.  Build with packaging/build_windows.ps1
# (or: pyinstaller --noconfirm --clean packaging/paperlook.spec)
import os
import re

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
BACKEND = os.path.join(ROOT, "backend")
ICON = os.path.join(ROOT, "assets", "paperlook.ico")

with open(os.path.join(BACKEND, "paperlook", "__init__.py"), encoding="utf-8") as f:
    VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', f.read()).group(1)
nums = tuple(int(x) for x in re.findall(r"\d+", VERSION.split("-")[0])[:3]) + (0,)

datas = [(os.path.join(BACKEND, "paperlook", "static"), "paperlook/static")]
datas += copy_metadata("keyring")          # keyring finds its backends through package metadata
datas += collect_data_files("pymupdf4llm")
hiddenimports = (collect_submodules("paperlook") + collect_submodules("uvicorn")
                 + collect_submodules("keyring.backends") + ["win32ctypes.core"])

a = Analysis(
    [os.path.join(SPECPATH, "paperlook_app.py")],
    pathex=[BACKEND],
    datas=datas,
    hiddenimports=hiddenimports,
    # setuptools is only imported by build-time code paths (cffi); 3.12+ venvs do not even ship it
    excludes=["tkinter", "pytest", "playwright", "PIL.ImageTk", "IPython", "matplotlib", "numpy.tests",
              "setuptools", "distutils", "pkg_resources"],
    noarchive=False,
)
pyz = PYZ(a.pure)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=nums, prodvers=nums),
    kids=[
        StringFileInfo([StringTable("080404B0", [
            StringStruct("CompanyName", "koara666"),
            StringStruct("FileDescription", "PaperLook 每日论文 · AI 精读"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", "PaperLook"),
            StringStruct("LegalCopyright", "MIT License"),
            StringStruct("OriginalFilename", "PaperLook.exe"),
            StringStruct("ProductName", "PaperLook"),
            StringStruct("ProductVersion", VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0804, 1200])]),
    ],
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PaperLook",
    console=False,
    icon=ICON,
    version=version_info,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PaperLook", upx=False)
