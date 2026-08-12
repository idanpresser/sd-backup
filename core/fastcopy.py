"""
FastCopy CLI Subprocess Driver for SD-FastBackup.
Resolves executable location (FastCopy.exe or fcp.exe), formats UTF-8 manifest files,
executes high-speed copy operations, and parses real-time stdout progress metrics.
"""
import os
import re
import sys
import shutil
import tempfile
import subprocess
from typing import List, Generator, Optional, Dict, Any


def parse_fastcopy_stdout_line(line: str) -> Dict[str, Any]:
    """
    Parses a single line of stdout from FastCopy / fcp.exe and extracts metrics.
    Returns dict with keys:
      - 'bytes_transferred': int
      - 'total_bytes': int
      - 'bytes_pct': float
      - 'files_transferred': int
      - 'total_files': int
      - 'speed_str': str
      - 'current_file': str
    """
    result = {}
    if not line:
        return result

    # 1. Transferred bytes pattern: "Transferred : 5,420,100,000 / 15,041,261,487 Bytes (36.0%)"
    bytes_match = re.search(r'Transferred\s*:\s*([\d,]+)\s*/\s*([\d,]+)\s*Bytes(?:\s*\(([\d\.]+)%\))?', line, re.IGNORECASE)
    if bytes_match:
        try:
            trans_b = int(bytes_match.group(1).replace(',', ''))
            tot_b = int(bytes_match.group(2).replace(',', ''))
            result['bytes_transferred'] = trans_b
            result['total_bytes'] = tot_b
            if bytes_match.group(3):
                result['bytes_pct'] = float(bytes_match.group(3))
            elif tot_b > 0:
                result['bytes_pct'] = round((trans_b / tot_b) * 100, 1)
        except Exception:
            pass

    # 2. Transferred files pattern: "Transferred : 12 / 120 Files"
    files_match = re.search(r'Transferred\s*:\s*([\d,]+)\s*/\s*([\d,]+)\s*Files', line, re.IGNORECASE)
    if files_match:
        try:
            result['files_transferred'] = int(files_match.group(1).replace(',', ''))
            result['total_files'] = int(files_match.group(2).replace(',', ''))
        except Exception:
            pass

    # 3. Speed pattern: "Speed : 485.2 MB/s (00:00:15)"
    speed_match = re.search(r'Speed\s*:\s*([\d\.]+\s*(?:B|KB|MB|GB|TB)/s)', line, re.IGNORECASE)
    if speed_match:
        result['speed_str'] = speed_match.group(1).strip()

    # 4. Current file pattern: "Copying : C:\DCIM\100EOS\IMG_0001.JPG"
    file_match = re.search(r'(?:Copying|Copied|Processing)\s*:\s*(.+)', line, re.IGNORECASE)
    if file_match:
        result['current_file'] = file_match.group(1).strip()

    return result


def resolve_fastcopy_executable(custom_path: Optional[str] = None) -> Optional[str]:
    """
    Resolves FastCopy or fcp executable in order of priority:
    1. Custom path provided in config/settings (file path or folder containing fcp.exe / FastCopy.exe)
    2. Working directory `./bin/fcp.exe` or `./bin/FastCopy.exe`
    3. Module base directory `./bin/fcp.exe` or `./bin/FastCopy.exe`
    4. `C:\\Program Files\\FastCopy\\fcp.exe` or `C:\\Program Files\\FastCopy\\FastCopy.exe`
    5. PATH environment variable (`fcp.exe`, `FastCopy.exe`)
    """
    executable_names = ["fcp.exe", "FastCopy.exe", "fastcopy.exe", "fcp"]

    # 1. Custom path check
    if custom_path:
        if custom_path.lower() == "none" or custom_path.lower() == "fallback":
            return None
        custom_path = os.path.normpath(custom_path)
        if os.path.isfile(custom_path) and os.path.exists(custom_path):
            return custom_path
        if os.path.isdir(custom_path):
            for name in executable_names:
                candidate = os.path.normpath(os.path.join(custom_path, name))
                if os.path.exists(candidate):
                    return candidate

    # 2. Check current working directory bin first
    cwd_bin = os.path.normpath(os.path.join(os.getcwd(), "bin"))
    for name in executable_names:
        candidate = os.path.join(cwd_bin, name)
        if os.path.exists(candidate):
            return candidate

    # 3. Check module directory bin
    module_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    module_bin = os.path.normpath(os.path.join(module_dir, "bin"))
    for name in executable_names:
        candidate = os.path.join(module_bin, name)
        if os.path.exists(candidate):
            return candidate

    # 4. Default System Install
    default_install_dirs = [
        r"C:\Program Files\FastCopy",
        r"C:\Program Files (x86)\FastCopy"
    ]
    for sys_dir in default_install_dirs:
        for name in executable_names:
            candidate = os.path.normpath(os.path.join(sys_dir, name))
            if os.path.exists(candidate):
                return candidate

    # 5. PATH lookup
    for name in executable_names:
        in_path = shutil.which(name)
        if in_path:
            return os.path.normpath(in_path)

    return None


class FastCopyRunner:
    """Wraps FastCopy / fcp executable for high-speed file transfers."""

    def __init__(self, fastcopy_executable_path: Optional[str] = None, force_fallback: bool = False):
        if force_fallback:
            self.exe_path = None
        else:
            self.exe_path = resolve_fastcopy_executable(fastcopy_executable_path)

    def execute_manifest_copy(self, source_files: List[str], target_dir: str) -> Generator[str, None, int]:
        """
        Creates a temporary manifest file and spawns FastCopy / fcp subprocess.
        If FastCopy is not installed or force_fallback is True, uses built-in Python shutil copy.
        Yields STDOUT lines for UI progress updates.
        Returns returncode (0 for success).
        """
        if not source_files:
            return 0

        target_dir = os.path.normpath(os.path.abspath(target_dir)).rstrip("\\/")
        os.makedirs(target_dir, exist_ok=True)

        if not self.exe_path:
            # Fallback Python copy engine
            yield "[ENGINE] FastCopy binary not found. Using built-in Python transfer engine..."
            for idx, src in enumerate(source_files, start=1):
                try:
                    norm_src = os.path.normpath(src)
                    rel_name = os.path.basename(norm_src)
                    dst = os.path.normpath(os.path.join(target_dir, rel_name))
                    shutil.copy2(norm_src, dst)
                    yield f"Transferred : {idx} / {len(source_files)} Files"
                    yield f"Copying : {rel_name}"
                except Exception as e:
                    yield f"[ERROR] Copying {src}: {e}"
            return 0

        # FastCopy / fcp Manifest Copy
        manifest_path = ""
        try:
            with tempfile.NamedTemporaryFile('w', delete=False, suffix='.txt', encoding='utf-8-sig') as temp_manifest:
                manifest_path = temp_manifest.name
                for path in source_files:
                    temp_manifest.write(f"{os.path.normpath(os.path.abspath(path))}\n")

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
