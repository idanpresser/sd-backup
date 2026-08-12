"""
SD-FastBackup - Blacklist Cleaner Helper Script.
Purges blacklisted non-media system/database files from target backup folder and SQLite catalog.

Usage:
  python clean_blacklist.py "D:\\All_Media_Aug26"
"""
import sys
import os
import argparse
from utils.blacklist_cleaner import clean_blacklisted_files_in_backup


def main():
    parser = argparse.ArgumentParser(
        description="SD-FastBackup Helper: Purge blacklisted system/database files from backup and SQLite catalog."
    )
    parser.add_argument("root_dir", help="Backup target root directory (e.g. 'D:\\All_Media_Aug26')")

    args = parser.parse_args()

    print(f"🧹 Starting Blacklist Cleaner for: '{args.root_dir}'")

    try:
        stats = clean_blacklisted_files_in_backup(args.root_dir)

        print("\n✅ BLACKLIST CLEANER COMPLETED SUCCESSFULLY!")
        print(f"   Files Scanned:     {stats['scanned_count']}")
        print(f"   Files Purged:      {stats['deleted_count']}")
        print(f"   DB Records Purged: {stats['db_removed_count']}")
        if stats['errors'] > 0:
            print(f"   ⚠️ Errors:           {stats['errors']}")
            
    except Exception as e:
        print(f"\n🛑 ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
