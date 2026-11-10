# PyInstaller recipe for the Windows app folder (dist\Susurros). The setup program is then
# made from that folder with packaging\windows\installer.iss.
import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).parents[1]

# The NVIDIA libraries for the GPU go next to the executable, where Windows looks for DLLs.
binaries = []
for module in ("nvidia.cublas", "nvidia.cudnn"):
    spec = importlib.util.find_spec(module)
    for location in (spec.submodule_search_locations if spec else []):
        for library in sorted((Path(location) / "bin").glob("*.dll")):
            if not library.name.lower().startswith("nvblas"):   # not used by the speech engine
                binaries.append((str(library), "."))

hidden = collect_submodules("susurros", filter=lambda name: ".mac" not in name and ".linux" not in name)
hidden += ["keyring.backends.Windows"]

analysis = Analysis(
    [str(root / "packaging" / "windows" / "launcher.py")],
    pathex=[str(root / "src")],
    datas=collect_data_files("faster_whisper"),   # the voice detector model
    binaries=binaries, hiddenimports=hidden,
    excludes=["tkinter", "pytest", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="Susurros", console=False,
          upx=False, icon=str(root / "build" / "windows" / "susurros.ico"))
collected = COLLECT(exe, analysis.binaries, analysis.datas, upx=False, name="Susurros")
