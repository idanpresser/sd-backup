"""
Suffix Renamer Helper for SD-FastBackup.
Delegates to consolidated maintenance module (utils/maintenance.py).
"""
from utils.maintenance import rename_suffix_in_backup

__all__ = ["rename_suffix_in_backup"]

