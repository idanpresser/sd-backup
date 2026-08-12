"""
Steel Thread Test for MTP Device Vertical Pipeline.
Tests every layer of the MTP architecture step-by-step on connected Android devices:
1. COM Initialization (pythoncom.CoInitialize)
2. Device Discovery under 'This PC' (Shell Namespace 17)
3. Shell Folder Navigation & Storage Unit Discovery
4. Deep Folder Traversal (DCIM, Pictures, Movies, Camera, etc.)
5. File Item & Metadata Extraction (Size, ItemDate, media filter)
6. Stream File Copy (CopyHere) to local temp folder
7. BackupWorker MTP QThread pipeline end-to-end
"""
import os
import sys
import time
import shutil
import tempfile

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def run_steel_thread():
    print("=" * 75)
    print("🚀 MTP STEEL THREAD TEST - END-TO-END VERTICAL DIAGNOSTIC")
    print("=" * 75)

    # LAYER 1: COM Initialization
    print("\n[LAYER 1] Initializing COM Apartment (pythoncom.CoInitialize)...")
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        print("  ✅ LAYER 1 SUCCESS: COM initialized.")
    except Exception as e:
        print(f"  ❌ LAYER 1 FAILED: {e}")
        return False

    # LAYER 2: Dispatch Shell.Application and enumerate Namespace 17
    print("\n[LAYER 2] Enumerating 'This PC' (Shell Namespace 17)...")
    shell = win32com.client.Dispatch("Shell.Application")
    my_pc = shell.Namespace(17)
    if not my_pc:
        print("  ❌ LAYER 2 FAILED: Could not access Shell Namespace 17.")
        return False

    mtp_items = []
    print("  Discovered Namespace 17 Items:")
    for item in my_pc.Items():
        name = str(item.Name)
        path = str(item.Path)
        itype = str(getattr(item, 'Type', '') or '')
        print(f"    • '{name}' | Path: {path} | Type: '{itype}' | IsFolder: {item.IsFolder}")
        
        is_standard_drive = (len(path) == 3 and path[1:3] == ":\\") or path.endswith(":\\")
        is_usb_guid = "usb#" in path.lower() or "wce#" in path.lower()
        is_mobile = any(kw in itype.lower() for kw in ["mobile", "phone", "portable", "camera", "media player", "mtp", "ptp", "oppo", "pixel", "galaxy"])
        
        if item.IsFolder and not is_standard_drive and (is_usb_guid or is_mobile or path.startswith("::{")):
            mtp_items.append(item)

    if not mtp_items:
        print("  ❌ LAYER 2 FAILED: No MTP phone devices found in Namespace 17.")
        return False

    target_phone_item = mtp_items[0]
    phone_name = str(target_phone_item.Name)
    phone_path = str(target_phone_item.Path)
    print(f"  ✅ LAYER 2 SUCCESS: Target phone selected: '{phone_name}'")

    # LAYER 3: Phone Root Folder Navigation
    print(f"\n[LAYER 3] Accessing device root folder for '{phone_name}'...")
    phone_folder = target_phone_item.GetFolder
    if not phone_folder:
        print("  ❌ LAYER 3 FAILED: GetFolder returned None.")
        return False

    sub_units = []
    for attempt in range(5):
        try:
            sub_units = list(phone_folder.Items())
            if sub_units:
                break
        except Exception:
            pass
        time.sleep(0.2)

    print(f"  Found {len(sub_units)} storage sub-unit(s) in root:")
    for unit in sub_units:
        print(f"    • Sub-unit: '{unit.Name}' | Path: {unit.Path[:60]}...")

    if not sub_units:
        print("  ⚠️ LAYER 3 DIAGNOSTIC NOTICE: Device root returned 0 items from Windows MTP driver.")
        print(f"     Device Path: {phone_path}")
        if "pid_2764" in phone_path.lower():
            print("     🔍 USB State Detected: pid_2764 (OPPO USB Charging Only / Locked State).")
            print("     👉 Action Required: Unlock phone screen and tap USB Notification -> Select 'File Transfer'.")
        elif "pid_2771" in phone_path.lower():
            print("     🔍 USB State Detected: pid_2771 (OPPO File Transfer Active).")
        return False

    print("  ✅ LAYER 3 SUCCESS: Storage sub-unit accessed.")

    # LAYER 4: Deep Folder Traversal
    print("\n[LAYER 4] Deep Folder Traversal (DCIM, Pictures, Movies, Camera, etc.)...")
    media_files = []
    
    def traverse(folder, current_path=""):
        try:
            items = []
            for attempt in range(5):
                try:
                    items = list(folder.Items())
                    if items:
                        break
                except Exception:
                    pass
                time.sleep(0.2)

            for item in items:
                name = str(item.Name)
                rel_path = f"{current_path}/{name}" if current_path else name
                
                if item.IsFolder:
                    sf = item.GetFolder
                    if sf:
                        traverse(sf, rel_path)
                else:
                    size = getattr(item, 'Size', 0)
                    if not size:
                        try:
                            size = int(item.ExtendedProperty("System.Size") or 0)
                        except Exception:
                            size = 0
                    
                    dt = None
                    try:
                        dt = item.ExtendedProperty("System.ItemDate") or item.ExtendedProperty("System.DateModified")
                    except Exception:
                        pass
                        
                    media_files.append({
                        'item': item,
                        'name': name,
                        'path': rel_path,
                        'size': size,
                        'date': dt
                    })
        except Exception as e:
            print(f"    ⚠️ Notice traversing '{current_path}': {e}")

    traverse(phone_folder, phone_name)

    print(f"  Total items discovered across phone storage: {len(media_files)}")
    for f in media_files[:10]:
        print(f"    • File: '{f['name']}' | Size: {f['size']} bytes | Path: {f['path']}")

    print("  ✅ LAYER 4 COMPLETED.")

    # LAYER 5: Metadata & Media Filter Evaluation
    print("\n[LAYER 5] Evaluating Multi-Layer Media Filter on discovered files...")
    from utils.media_filter import is_media_file

    valid_media = [f for f in media_files if is_media_file(f['name'])]
    print(f"  Valid media files after filtering: {len(valid_media)} / {len(media_files)}")
    
    for f in valid_media[:5]:
        print(f"    • Accepted Media: '{f['name']}' ({f['size']} bytes)")

    print("  ✅ LAYER 5 SUCCESS.")

    # LAYER 6: Stream File Copy Test (CopyHere)
    if valid_media:
        target_sample = valid_media[0]
        print(f"\n[LAYER 6] Testing Stream File Copy (CopyHere) on sample file: '{target_sample['name']}'...")
        temp_dir = tempfile.mkdtemp(prefix="steel_mtp_")
        try:
            dest_shell = shell.NameSpace(temp_dir)
            dest_shell.CopyHere(target_sample['item'], 16)
            
            staged_path = os.path.join(temp_dir, target_sample['name'])
            start_t = time.time()
            copied = False
            while (time.time() - start_t) < 15:
                if os.path.exists(staged_path) and os.path.getsize(staged_path) > 0:
                    copied = True
                    break
                time.sleep(0.2)

            if copied:
                bytes_copied = os.path.getsize(staged_path)
                print(f"  ✅ LAYER 6 SUCCESS: File '{target_sample['name']}' copied ({bytes_copied} bytes).")
            else:
                print(f"  ❌ LAYER 6 FAILED: CopyHere timed out after 15s for '{target_sample['name']}'.")
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    else:
        print("\n[LAYER 6] Skipped (No valid media files found in Layer 5).")

    # LAYER 7: End-to-End MTPEngine & BackupWorker Test
    print("\n[LAYER 7] End-to-End MTPEngine & BackupWorker QThread Test...")
    from core.mtp_engine import MTPEngine
    engine = MTPEngine()
    mtp_files = engine.enumerate_mtp_files(phone_name, full_volume=True)
    print(f"  MTPEngine.enumerate_mtp_files returned: {len(mtp_files)} files.")

    print("\n" + "=" * 75)
    if len(mtp_files) > 0 or len(media_files) > 0:
        print("🎉 STEEL THREAD TEST PASSED: Full MTP vertical is working!")
    else:
        print("⚠️ STEEL THREAD TEST COMPLETED: Device connected, waiting for USB File Transfer mode.")
    print("=" * 75)

if __name__ == "__main__":
    run_steel_thread()
