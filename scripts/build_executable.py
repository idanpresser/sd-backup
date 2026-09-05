"""
Automated Build Script for SD-FastBackup PyInstaller Executable.
Packages SD-FastBackup into a standalone onedir distribution under dist/SD-FastBackup/.
"""
import os
import sys
import shutil
import subprocess


def build():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root_dir)

    print("==================================================")
    print("🔨 Building SD-FastBackup Standalone Executable")
    print("==================================================")
    print(f"Working Directory: {root_dir}")

    # 1. Verify pyinstaller
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("❌ PyInstaller not found. Installing via pip...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. Run PyInstaller build
    spec_file = os.path.join(root_dir, "sd_backup.spec")
    if not os.path.exists(spec_file):
        print(f"❌ Spec file not found: {spec_file}")
        sys.exit(1)

    cmd = [sys.executable, "-m", "PyInstaller", spec_file, "--clean", "--noconfirm"]
    print(f"\nExecuting: {' '.join(cmd)}")
    res = subprocess.run(cmd)

    if res.returncode != 0:
        print(f"\n❌ Build failed with exit code {res.returncode}")
        sys.exit(res.returncode)

    # 3. Copy top-level config.json next to .exe if exists
    dist_dir = os.path.join(root_dir, "dist", "SD-FastBackup")
    src_cfg = os.path.join(root_dir, "config.json")
    dst_cfg = os.path.join(dist_dir, "config.json")
    if os.path.exists(src_cfg) and not os.path.exists(dst_cfg):
        shutil.copy2(src_cfg, dst_cfg)
        print("  Copied config.json adjacent to executable.")

    # 4. Verify Output Artifacts
    exe_path = os.path.join(dist_dir, "SD-FastBackup.exe")
    
    # In PyInstaller onedir mode, bundled data lives in _internal/
    internal_dir = os.path.join(dist_dir, "_internal")
    fcp_path = (
        os.path.join(internal_dir, "bin", "fcp.exe")
        if os.path.exists(os.path.join(internal_dir, "bin", "fcp.exe"))
        else os.path.join(dist_dir, "bin", "fcp.exe")
    )
    exiftool_path = (
        os.path.join(internal_dir, "bin", "exiftool.exe")
        if os.path.exists(os.path.join(internal_dir, "bin", "exiftool.exe"))
        else os.path.join(dist_dir, "bin", "exiftool.exe")
    )
    qss_path = (
        os.path.join(internal_dir, "assets", "dark_style.qss")
        if os.path.exists(os.path.join(internal_dir, "assets", "dark_style.qss"))
        else os.path.join(dist_dir, "assets", "dark_style.qss")
    )

    print("\n🔍 Verifying build outputs:")
    checks = [
        ("Executable", exe_path),
        ("FastCopy Binary (fcp.exe)", fcp_path),
        ("ExifTool Binary (exiftool.exe)", exiftool_path),
        ("Dark Theme Stylesheet (dark_style.qss)", qss_path),
    ]

    all_passed = True
    for name, p in checks:
        if os.path.exists(p):
            size_kb = os.path.getsize(p) / 1024
            print(f"  ✅ {name}: {os.path.relpath(p, root_dir)} ({size_kb:.1f} KB)")
        else:
            print(f"  ❌ {name} MISSING at: {p}")
            all_passed = False

    if not all_passed:
        print("\n❌ Verification failed: some output files are missing.")
        sys.exit(1)

    # Calculate total folder size
    total_size_bytes = sum(
        os.path.getsize(os.path.join(dirpath, filename))
        for dirpath, _, filenames in os.walk(dist_dir)
        for filename in filenames
    )
    total_mb = total_size_bytes / (1024 * 1024)

    print("\n🎉 Build successful!")
    print(f"📁 Standalone Distribution Folder: {dist_dir}")
    print(f"📦 Total Distribution Size: {total_mb:.2f} MB")
    print(f"🚀 Run Application: {exe_path}")


if __name__ == "__main__":
    build()
