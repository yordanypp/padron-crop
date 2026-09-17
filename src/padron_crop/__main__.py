"""Allow `python -m padron_crop ...` (same entry point as the console script)."""
from padron_crop.cli import main_entry

if __name__ == "__main__":
    main_entry()
