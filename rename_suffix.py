"""
SD-FastBackup - Suffix Renamer Helper Script.
Renames file suffixes in target backup folder and updates the SQLite database catalog.

Usage:
  python rename_suffix.py "D:\\All_Media_Aug26" "AnatKP(C)" "IdanPresser(C)" ["C:\\DEV\\sd_backup\\file_list.txt"]
"""
import sys
import os
import argparse
from utils.suffix_renamer import rename_suffix_in_backup


def main():
    parser = argparse.ArgumentParser(
        description="SD-FastBackup Helper: Rename file suffixes on disk and update SQLite catalog."
    )
    parser.add_argument("root_dir", help="Backup target root directory (where .sd_backup_catalog.db lives)")
    parser.add_argument("old_suffix", help="Old suffix string to replace (e.g. 'AnatKP(C)')")
    parser.add_argument("new_suffix", help="New suffix string to apply (e.g. 'IdanPresser(C)')")
    parser.add_argument("file_list", nargs="?", default=None, help="Optional text file listing specific files to rename")

    args = parser.parse_args()

    print(f"🔄 Starting Suffix Renamer for: '{args.root_dir}'")
    print(f"   Old Suffix: '{args.old_suffix}'")
    print(f"   New Suffix: '{args.new_suffix}'")
    if args.file_list:
        print(f"   File List:  '{args.file_list}'")

    try:
        stats = rename_suffix_in_backup(
            root_dir=args.root_dir,
            old_suffix=args.old_suffix,
            new_suffix=args.new_suffix,
            file_list_path=args.file_list
        )

        print("\n✅ SUFFIX RENAMER COMPLETED SUCCESSFULLY!")
        print(f"   Scanned Files:    {stats['scanned_count']}")
        print(f"   Files Renamed:    {stats['renamed_count']}")
        print(f"   Database Records: {stats['db_updated_count']}")
        if stats['errors'] > 0:
            print(f"   ⚠️ Errors:          {stats['errors']}")
            
    except Exception as e:
        print(f"\n🛑 ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
