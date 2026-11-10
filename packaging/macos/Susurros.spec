# PyInstaller recipe for Susurros.app. Run it through packaging/macos/build.sh.
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

root = Path(SPECPATH).parents[1]
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]

datas, binaries, hidden = [], [], []
# MLX ships its GPU code as data files next to the library; mlx-whisper, its tokenizer tables.
for package in ("mlx", "mlx_whisper"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hidden += package_hidden
datas += collect_data_files("faster_whisper")   # the voice detector model
hidden += collect_submodules("susurros")
hidden += ["keyring.backends.macOS", "tiktoken_ext", "tiktoken_ext.openai_public",
           "AppKit", "Foundation", "Quartz", "ApplicationServices", "HIServices", "AVFoundation"]

analysis = Analysis(
    [str(root / "packaging" / "macos" / "launcher.py")],
    pathex=[str(root / "src")],
    datas=datas, binaries=binaries, hiddenimports=hidden,
    excludes=["torch", "tkinter", "pytest", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="Susurros", console=False,
          upx=False, target_arch="arm64", codesign_identity=None)
collected = COLLECT(exe, analysis.binaries, analysis.datas, upx=False, name="Susurros")
app = BUNDLE(
    collected, name="Susurros.app", icon=str(root / "build" / "macos" / "Susurros.icns"),
    bundle_identifier="io.github.ktjota.susurros", version=version,
    info_plist={
        "CFBundleDisplayName": "Susurros",
        "CFBundleShortVersionString": version,
        "LSMinimumSystemVersion": "14.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Susurros records your voice while you hold the dictation key, "
                                        "to turn it into text on this Mac.",
    },
)
