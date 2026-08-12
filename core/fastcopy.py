"""
FastCopy CLI Subprocess Driver for SD-FastBackup.
Resolves executable location, formats UTF-8 manifest files, and executes high-speed copy operations.
"""
import os
import sys
import shutil
import tempfile
import subprocess
from typing import List, Generator, Optional


def resolve_fastcopy_executable(custom_path: Optional[str] = None) -> Optional[str]:
    """
    Resolves FastCopy.exe in order of priority:
    1. Custom path provided in config/settings (if exists)
    2. `./bin/FastCopy.exe` relative to working directory or script root
    3. `C:\\Program Files\\FastCopy\\FastCopy.exe`
    4. PATH environment variable
    """
    # 1. Custom path
    if custom_path and os.path.exists(custom_path) and os.path.isfile(custom_path):
        return os.path.abspath(custom_path)

    # 2. Relative ./bin/FastCopy.exe
    base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    relative_bin = os.path.join(base_dir, "bin", "FastCopy.exe")
    if os.path.exists(relative_bin):
        return relative_bin

    current_relative_bin = os.path.join(os.getcwd(), "bin", "FastCopy.exe")
    if os.path.exists(current_relative_bin):
        return current_relative_bin

    # 3. Default System Install
    default_system = r"C:\Program Files\FastCopy\FastCopy.exe"
    if os.path.exists(default_system):
        return default_system

    # 4. PATH lookup
    in_path = shutil.which("FastCopy.exe") or shutil.which("fastcopy.exe")
    if in_path:
        return in_path

    return None


class FastCopyRunner:
    """Wraps FastCopy executable for high-speed file transfers."""

    def __init__(self, fastcopy_executable_path: Optional[str] = None):
        self.exe_path = resolve_fastcopy_executable(fastcopy_executable_path)

    def execute_manifest_copy(self, source_files: List[str], target_dir: str) -> Generator[str, None, int]:
        """
        Creates a temporary manifest file and spawns FastCopy subprocess.
        If FastCopy is not installed, falls back to standard Python shutil copy with logging.
        Yields STDOUT lines for UI progress updates.
        Returns returncode (0 for success).
        """
        if not source_files:
            return 0

        target_dir = os.path.abspath(target_dir)
        os.makedirs(target_dir, exist_ok=True)

        if not self.exe_path:
            # Fallback Python copy engine
            yield "[ENGINE] FastCopy binary not found. Using built-in Python transfer engine..."
            for idx, src in enumerate(source_files, start=1):
                try:
                    rel_name = os.path.basename(src)
                    dst = os.path.join(target_dir, rel_name)
                    shutil.copy2(src, dst)
                    yield f"[{idx}/{len(source_files)}] Copied: {rel_name}"
                except Exception as e:
                    yield f"[{idx}/{len(source_files)}] ERROR copying {src}: {e}"
            return 0

        # FastCopy Manifest Copy
        manifest_path = ""
        try:
            with tempfile.NamedTemporaryFile('w', delete=False, suffix='.txt', encoding='utf-8-sig') as temp_manifest:
                manifest_path = temp_manifest.name
                for path in source_files:
                    temp_manifest.write(f"{os.path.abspath(path)}\n")

            cmd = [
                self.exe_path,
                "/cmd=diff",
                "/verify",
                "/bufsize=1024",
                "/speed=full",
                "/utf8",
                "/auto_close",
                "/error_stop",
                f"/srcfile_w={manifest_path}",
                f"/to={target_dir}"
            ]

            yield f"[FASTCOPY] Spawning command: {' '.join(cmd)}"

            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding='utf-8',
                errors='replace',
                creationflags=creation_flags
            )

            if process.stdout:
                for line in process.stdout:
                    stripped = line.strip()
                    if stripped:
                        yield stripped

            process.wait()
            return process.returncode
        except Exception as e:
            yield f"[FASTCOPY ERROR] Failed to execute FastCopy: {e}"
            return 1
        finally:
            if manifest_path and os.path.exists(manifest_path):
                try:
                    os.remove(manifest_path)
                except Exception:
                    pass
