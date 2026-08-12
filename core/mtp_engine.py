"""
Windows Shell COM MTP Driver for SD-FastBackup.
Provides MTP (Media Transfer Protocol) device detection, virtual directory traversal, 
metadata extraction, and stream copying for smartphones (Android & iPhone).
"""
import os
import sys
import time
import shutil
import tempfile
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    import win32com.client
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False


def is_mtp_path(path_str: str) -> bool:
    """Returns True if path_str represents an MTP device virtual path."""
    if not path_str:
        return False
    norm = path_str.replace("/", "\\")
    return norm.startswith("MTP:\\") or norm.startswith("shell:MTP\\")


def parse_mtp_device_name(path_str: str) -> str:
    """Extracts device name from MTP virtual path e.g. 'MTP:\\Pixel 8 Pro\\DCIM' -> 'Pixel 8 Pro'."""
    if not is_mtp_path(path_str):
        return ""
    norm = path_str.replace("/", "\\")
    parts = norm.split("\\")
    if len(parts) >= 2:
        return parts[1]
    return ""


class MTPEngine:
    """Windows Shell COM engine for browsing and transferring MTP phone media."""

    def __init__(self):
        self.shell = win32com.client.Dispatch("Shell.Application") if HAS_WIN32COM else None

    def get_mtp_devices(self) -> List[Dict[str, Any]]:
        """Enumerates connected MTP devices under 'This PC' (Shell Namespace 17)."""
        devices = []
        if not self.shell:
            return devices

        try:
            my_computer = self.shell.Namespace(17)  # 17 = ssfDRIVES (This PC)
            if my_computer:
                for item in my_computer.Items():
                    item_path = str(item.Path)
                    item_name = str(item.Name)
                    item_type = str(getattr(item, 'Type', '') or '')
                    
                    is_standard_drive = (len(item_path) == 3 and item_path[1:3] == ":\\") or item_path.endswith(":\\")
                    is_usb_guid = "\\\\?\\usb#" in item_path.lower() or "\\\\?\\wce#" in item_path.lower()
                    is_mobile_type = any(kw in item_type.lower() for kw in [
                        "mobile", "phone", "portable", "camera", "media player", 
                        "mtp", "iphone", "android", "pixel", "galaxy"
                    ])

                    if item.IsFolder and not is_standard_drive and (is_usb_guid or is_mobile_type or item_path.startswith("::{")):
                        devices.append({
                            "path": f"MTP:\\{item_name}",
                            "label": item_name,
                            "serial": f"MTP_{abs(hash(item_name)) % 100000000:08X}",
                            "drive_type": f"MTP Mobile Phone ({item_type})" if item_type else "MTP Mobile Phone",
                            "free_bytes": 0,
                            "total_bytes": 0,
                            "shell_item": item
                        })
        except Exception as e:
            logging.warning(f"Error enumerating MTP devices: {e}")

        return devices

    def _get_device_root_folder(self, device_name: str):
        """Locates the device shell folder for device_name under 'This PC'."""
        if not self.shell:
            return None

        my_computer = self.shell.Namespace(17)
        if not my_computer:
            return None

        for item in my_computer.Items():
            if str(item.Name).lower() == device_name.lower():
                return item.GetFolder

        return None

    def enumerate_mtp_files(
        self, 
        device_name: str, 
        include_dcim: bool = True, 
        include_private: bool = True, 
        full_volume: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Traverses MTP device media directories (Internal storage/DCIM, PRIVATE, etc.)
        and returns file dicts:
        [{'file_item': shell_item, 'name': fname, 'rel_path': rel_path, 'size': size_bytes, 'date_taken': datetime_obj}]
        """
        file_list = []
        dev_folder = self._get_device_root_folder(device_name)
        if not dev_folder:
            return file_list

        self._traverse_folder(dev_folder, "", file_list, include_dcim, include_private, full_volume)
        return file_list

    def _traverse_folder(
        self, 
        folder_item, 
        current_rel: str, 
        results: list, 
        include_dcim: bool, 
        include_private: bool, 
        full_volume: bool
    ):
        """Recursively traverses MTP virtual shell folders (locale-independent)."""
        try:
            items = folder_item.Items()
            for item in items:
                name = str(item.Name)
                name_upper = name.upper()

                if item.IsFolder:
                    sub_folder = item.GetFolder
                    if not sub_folder:
                        continue

                    # Filter top-level media folders if not full_volume
                    if not current_rel and not full_volume:
                        if name_upper == "DCIM" and not include_dcim:
                            continue
                        if name_upper == "PRIVATE" and not include_private:
                            continue

                    sub_rel = os.path.join(current_rel, name)
                    self._traverse_folder(sub_folder, sub_rel, results, include_dcim, include_private, full_volume)
                else:
                    # File item
                    size = getattr(item, 'Size', 0)
                    if not size:
                        try:
                            size = int(item.ExtendedProperty("System.Size") or 0)
                        except Exception:
                            size = 0

                    dt_val = None
                    try:
                        dt_raw = item.ExtendedProperty("System.ItemDate") or item.ExtendedProperty("System.DateModified")
                        if dt_raw:
                            dt_val = datetime.fromtimestamp(time.mktime(dt_raw.timetuple()))
                    except Exception:
                        dt_val = datetime.now()

                    if not dt_val:
                        dt_val = datetime.now()

                    rel_path = os.path.join(current_rel, name)
                    results.append({
                        "file_item": item,
                        "name": name,
                        "rel_path": rel_path,
                        "size": size,
                        "date_taken": dt_val
                    })
        except Exception as e:
            logging.debug(f"MTP traversal notice for '{current_rel}': {e}")

    def copy_mtp_file_to_local(self, shell_file_item, local_destination_path: str) -> bool:
        """
        Copies an MTP virtual shell item to standard local Windows filesystem path.
        """
        if not self.shell:
            return False

        temp_dir = tempfile.mkdtemp(prefix="mtp_stage_")
        try:
            target_shell_dir = self.shell.NameSpace(temp_dir)
            if not target_shell_dir:
                return False

            # CopyHere options: 16 = Respond "Yes to All" to any dialogs
            target_shell_dir.CopyHere(shell_file_item, 16)

            staged_filename = str(shell_file_item.Name)
            staged_path = os.path.join(temp_dir, staged_filename)

            # Wait for Windows Shell async copy to complete
            timeout_sec = 30
            start_t = time.time()
            while not os.path.exists(staged_path) and (time.time() - start_t) < timeout_sec:
                time.sleep(0.1)

            if os.path.exists(staged_path):
                os.makedirs(os.path.dirname(local_destination_path), exist_ok=True)
                shutil.move(staged_path, local_destination_path)
                return True
            else:
                logging.error(f"MTP copy timeout for '{staged_filename}'")
                return False
        except Exception as e:
            logging.error(f"MTP CopyHere failed: {e}")
            return False
        finally:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass


def browse_with_windows_shell(hwnd: int = 0) -> Optional[str]:
    """
    Spawns Windows Shell BrowseForFolder dialog allowing selection of MTP devices (Pixel 8 Pro, iPhone)
    or standard local drive folders.
    Returns MTP:\\DeviceName or local directory path.
    """
    if not HAS_WIN32COM:
        return None

    try:
        shell = win32com.client.Dispatch("Shell.Application")
        # BIF_RETURNONLYFSDIRS = 0x0001, BIF_NONEWFOLDERBUTTON = 0x0200
        # 17 = ssfDRIVES (This PC)
        folder = shell.BrowseForFolder(hwnd, "Select Source Drive, Folder, or Mobile Phone (MTP)", 0, 17)
        if folder:
            title = str(folder.Title)
            item_path = str(folder.Self.Path)

            # Check if MTP device or inside MTP device
            if not os.path.exists(item_path) or item_path.startswith("::{"):
                # MTP item selected
                name = str(folder.Self.Name)
                return f"MTP:\\{name}"
            else:
                return normalize_win_path(item_path)
    except Exception as e:
        logging.warning(f"Shell BrowseForFolder notice: {e}")

    return None
