"""
Drive detector utility for SD-FastBackup.
Enumerates attached drives, removable media (SD cards), volume labels, and serial numbers.
"""
import os
import sys
import ctypes
import shutil
from typing import List, Dict, Any


def get_drive_volume_info(drive_path: str) -> Dict[str, str]:
    """
    Retrieves volume label and serial number for a given drive path (Windows).
    """
    label = "Unknown"
    serial = "UNKNOWN"

    if not drive_path:
        return {"label": label, "serial": serial}

    # Normalize drive path format e.g. "E:\\"
    drive_root = drive_path.rstrip("\\") + "\\"

    if sys.platform == "win32":
        try:
            volume_name_buffer = ctypes.create_unicode_buffer(1024)
            file_system_name_buffer = ctypes.create_unicode_buffer(1024)
            serial_number = ctypes.c_ulong()
            max_component_length = ctypes.c_ulong()
            file_system_flags = ctypes.c_ulong()

            rc = ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(drive_root),
                volume_name_buffer,
                ctypes.sizeof(volume_name_buffer),
                ctypes.byref(serial_number),
                ctypes.byref(max_component_length),
                ctypes.byref(file_system_flags),
                file_system_name_buffer,
                ctypes.sizeof(file_system_name_buffer)
            )

            if rc:
                label = volume_name_buffer.value or "NO_NAME"
                serial = f"{serial_number.value:08X}"
        except Exception:
            pass
    else:
        if os.path.exists(drive_root):
            label = os.path.basename(drive_path.rstrip("/\\")) or "MOUNT"
            serial = f"VOL_{abs(hash(drive_root)) % 100000000:08X}"

    return {"label": label, "serial": serial}


def get_available_drives() -> List[Dict[str, Any]]:
    """
    Returns list of connected drive information dicts:
    [{'path': 'E:\\', 'label': 'SD_CARD', 'drive_type': 'Removable', 'free_bytes': ..., 'total_bytes': ...}]
    """
    drives = []

    if sys.platform == "win32":
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter_code in range(26):
                if bitmask & (1 << letter_code):
                    drive_letter = f"{chr(65 + letter_code)}:\\"
                    
                    # Get Drive Type
                    # 2: DRIVE_REMOVABLE, 3: DRIVE_FIXED, 4: DRIVE_REMOTE, 5: DRIVE_CDROM, 6: DRIVE_RAMDISK
                    dtype_code = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(drive_letter))
                    type_str = "Removable" if dtype_code == 2 else ("Fixed" if dtype_code == 3 else "Other")

                    vol_info = get_drive_volume_info(drive_letter)
                    
                    free_bytes, total_bytes = 0, 0
                    try:
                        usage = shutil.disk_usage(drive_letter)
                        free_bytes = usage.free
                        total_bytes = usage.total
                    except Exception:
                        pass

                    drives.append({
                        "path": drive_letter,
                        "label": vol_info["label"],
                        "serial": vol_info["serial"],
                        "drive_type": type_str,
                        "free_bytes": free_bytes,
                        "total_bytes": total_bytes
                    })
        except Exception:
            pass
    else:
        # Cross-platform fallback for testing
        test_paths = ["/Volumes", "/media", "/mnt", "."]
        for p in test_paths:
            if os.path.exists(p):
                vol_info = get_drive_volume_info(p)
                try:
                    usage = shutil.disk_usage(p)
                    free_b, total_b = usage.free, usage.total
                except Exception:
                    free_b, total_b = 0, 0

                drives.append({
                    "path": os.path.abspath(p),
                    "label": vol_info["label"],
                    "serial": vol_info["serial"],
                    "drive_type": "Removable",
                    "free_bytes": free_b,
                    "total_bytes": total_b
                })

    return drives
