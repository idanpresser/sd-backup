"""
Drive detector utility for SD-FastBackup.
Enumerates attached drives, removable media (SD cards), MTP mobile phone devices, volume labels, and same-drive checks.
"""
import os
import sys
import ctypes
import shutil
from typing import List, Dict, Any
from core.mtp_engine import MTPEngine


def is_same_drive(path_a: str, path_b: str) -> bool:
    """
    Returns True if both paths reside on the same drive/volume root (e.g. both on C:\\ or both on D:\\).
    MTP devices are never same-drive with local drives.
    """
    if not path_a or not path_b:
        return False

    if path_a.startswith("MTP:\\") or path_b.startswith("MTP:\\"):
        return False

    abs_a = os.path.abspath(path_a)
    abs_b = os.path.abspath(path_b)

    drive_a, _ = os.path.splitdrive(abs_a)
    drive_b, _ = os.path.splitdrive(abs_b)

    if drive_a and drive_b:
        return drive_a.upper() == drive_b.upper()

    return os.path.dirname(abs_a) == os.path.dirname(abs_b) or abs_a.split(os.sep)[1:2] == abs_b.split(os.sep)[1:2]


def get_drive_volume_info(drive_path: str) -> Dict[str, str]:
    """
    Retrieves volume label and serial number for a given drive path (Windows).
    """
    label = "Unknown"
    serial = "UNKNOWN"

    if not drive_path:
        return {"label": label, "serial": serial}

    if drive_path.startswith("MTP:\\"):
        dev_name = drive_path.replace("MTP:\\", "")
        return {"label": dev_name, "serial": f"MTP_{abs(hash(dev_name)) % 100000000:08X}"}

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
    Includes standard Drive Letters (E:\\, F:\\) AND MTP Mobile Phone Devices (Pixel 8, iPhone).
    """
    drives = []

    if sys.platform == "win32":
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter_code in range(26):
                if bitmask & (1 << letter_code):
                    drive_letter = f"{chr(65 + letter_code)}:\\"
                    
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

        # 2. Add connected MTP Mobile Phone Devices
        try:
            mtp_engine = MTPEngine()
            mtp_devs = mtp_engine.get_mtp_devices()
            drives.extend(mtp_devs)
        except Exception:
            pass

    else:
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
