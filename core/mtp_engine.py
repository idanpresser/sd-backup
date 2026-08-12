"""
Windows Shell COM MTP & PTP Driver for SD-FastBackup.
Provides MTP/PTP (Media & Picture Transfer Protocol) device detection, virtual directory traversal, 
metadata extraction, stream copying, subfolder fallback, and async USB folder polling for smartphones (Android & iPhone).
"""
import os
import sys
import time
import shutil
import tempfile
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from utils.media_filter import is_media_file

try:
    import win32com.client
    import pythoncom
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False


def _ensure_coinitialize():
    """Ensures COM Single-Threaded Apartment is initialized on background QThreads."""
    if HAS_WIN32COM and sys.platform == "win32":
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass


def is_mtp_path(path_str: str) -> bool:
    """Returns True if path_str represents an MTP device virtual path."""
    if not path_str:
        return False
    norm = path_str.replace("/", "\\")
    return norm.startswith("MTP:\\") or norm.startswith("shell:MTP\\")


def _get_mtp_path_components(path_str: str) -> List[str]:
    """Strips MTP:\\ prefix and splits path into non-empty components."""
    if not is_mtp_path(path_str):
        return []
    cleaned = path_str.replace("shell:MTP\\", "").replace("MTP:\\", "").strip("\\")
    return [p for p in cleaned.split("\\") if p]


def parse_mtp_device_name(path_str: str) -> str:
    """Extracts device name from MTP virtual path e.g. 'MTP:\\Pixel 8 Pro\\Internal shared storage' -> 'Pixel 8 Pro'."""
    parts = _get_mtp_path_components(path_str)
    if not parts:
        return ""
    return parts[0]


def parse_mtp_subfolder_path(path_str: str) -> str:
    """Extracts subfolder path after device name e.g. 'MTP:\\Pixel 8 Pro\\Internal shared storage\\DCIM' -> 'Internal shared storage\\DCIM'."""
    parts = _get_mtp_path_components(path_str)
    if len(parts) <= 1:
        return ""
    return os.path.join(*parts[1:])


class MTPEngine:
    """Windows Shell COM engine for browsing and transferring MTP/PTP phone media."""

    def __init__(self):
        _ensure_coinitialize()
        self.shell = win32com.client.Dispatch("Shell.Application") if HAS_WIN32COM else None

    def get_mtp_devices(self) -> List[Dict[str, Any]]:
        """Enumerates connected MTP/PTP devices under 'This PC' (Shell Namespace 17)."""
        _ensure_coinitialize()
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
                    is_usb_guid = "usb#" in item_path.lower() or "wce#" in item_path.lower()
                    is_mobile_type = any(kw in item_type.lower() for kw in [
                        "mobile", "phone", "portable", "camera", "media player", 
                        "mtp", "ptp", "iphone", "android", "pixel", "galaxy", "oppo"
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
        _ensure_coinitialize()
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
        subfolder_path: str = "",
        include_dcim: bool = True, 
        include_private: bool = True, 
        full_volume: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Traverses MTP/PTP device media directories (Internal storage/DCIM, Pictures, etc.)
        and returns file dicts:
        [{'file_item': shell_item, 'name': fname, 'rel_path': rel_path, 'size': size_bytes, 'date_taken': datetime_obj}]
        """
        _ensure_coinitialize()
        file_list = []
        root_folder = self._get_device_root_folder(device_name)
        if not root_folder:
            return file_list

        target_folder = root_folder

        # If subfolder_path is specified, navigate into it with retry polling
        if subfolder_path:
            sub_parts = subfolder_path.replace("/", "\\").split("\\")
            for part in sub_parts:
                if not part:
                    continue
                found_sub = None
                
                # Retry loop for async USB folder resolution
                for attempt in range(5):
                    try:
                        for item in target_folder.Items():
                            if item.IsFolder and str(item.Name).lower() == part.lower():
                                found_sub = item.GetFolder
                                break
                    except Exception:
                        pass
                    if found_sub:
                        break
                    time.sleep(0.15)

                if found_sub:
                    target_folder = found_sub
                else:
                    logging.warning(f"MTP subfolder part '{part}' not found in '{device_name}'")
                    break

        # 1. Primary traversal with async polling
        self._traverse_folder(target_folder, "", file_list, include_dcim, include_private, full_volume)

        # 2. Fallback to device root traversal if 0 files found and subfolder_path was specified
        if not file_list and subfolder_path and root_folder != target_folder:
            logging.info(f"0 files found in subfolder '{subfolder_path}'. Falling back to root device traversal...")
            self._traverse_folder(root_folder, "", file_list, include_dcim=True, include_private=True, full_volume=True)

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
        """Recursively traverses MTP virtual shell folders with async USB retry polling."""
        try:
            items = []
            for attempt in range(5):
                try:
                    items = list(folder_item.Items())
                    if items:
                        break
                except Exception:
                    pass
                time.sleep(0.15)

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
                    # Apply Multi-Layer Media Filter
                    if not is_media_file(name):
                        continue

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
        _ensure_coinitialize()
        if not self.shell:
            return False

        temp_dir = os.path.abspath(tempfile.mkdtemp(prefix="mtp_stage_"))
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
    Spawns Windows Shell BrowseForFolder dialog allowing selection of MTP devices (Pixel 8 Pro, iPhone, OPPO)
    or subfolders (Internal shared storage) or standard local drive folders.
    Reconstructs MTP:\\DeviceName\\SubFolder.
    """
    _ensure_coinitialize()
    if not HAS_WIN32COM:
        return None

    try:
        shell = win32com.client.Dispatch("Shell.Application")
        folder = shell.BrowseForFolder(hwnd, "Select Source Drive, Folder, or Mobile Phone (MTP/PTP)", 0, 17)
        if folder:
            item_path = str(folder.Self.Path)

            if not os.path.exists(item_path) or item_path.startswith("::{"):
                path_parts = []
                curr = folder
                
                while curr and hasattr(curr, "Title"):
                    title = str(curr.Title)
                    if title.lower() in ["this pc", "computer", "my computer"]:
                        break
                    path_parts.insert(0, str(curr.Self.Name) if hasattr(curr, "Self") else title)
                    
                    try:
                        curr = curr.ParentFolder
                    except Exception:
                        break

                if path_parts:
                    mtp_str = "\\".join(path_parts)
                    return f"MTP:\\{mtp_str}"
                else:
                    return f"MTP:\\{str(folder.Self.Name)}"
            else:
                return os.path.normpath(item_path)
    except Exception as e:
        logging.warning(f"Shell BrowseForFolder notice: {e}")

    return None
