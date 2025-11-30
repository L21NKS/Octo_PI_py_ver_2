#!/usr/bin/env python3
import os
import zipfile
from loguru import logger

LOGS_DIR = "logs"

def _list_logs():
    files = []
    if os.path.exists(LOGS_DIR):
        for f in os.listdir(LOGS_DIR):
            if f.endswith(".log") or f.endswith(".zip"):
                files.append(f)
    return sorted(files, reverse=True)

def _print_file(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        print(f.read())

def _print_zip_first_log(path):
    with zipfile.ZipFile(path, "r") as zf:
        # Берём первый файл из архива (у Loguru он единственный)
        name = zf.namelist()[0]
        with zf.open(name, "r") as f:
            content = f.read().decode("utf-8", errors="ignore")
            print(content)

def view_logs():
    if not os.path.exists(LOGS_DIR):
        logger.warning("The logs folder was not found")
        return

    log_files = _list_logs()
    if not log_files:
        logger.warning("No log files found")
        return

    while True:
        print("Available log files:")
        for i, file in enumerate(log_files, 1):
            print(f"{i}. {file}")
        try:
            choice = input("\nSelect the file (q — exit): ").strip()
            if choice == "q":
                return
            idx = int(choice) - 1
            if idx < 0 or idx >= len(log_files):
                logger.warning("Wrong choice")
                continue

            selected = os.path.join(LOGS_DIR, log_files[idx])
            print("\n" + "=" * 80)
            if selected.endswith(".log"):
                _print_file(selected)
            else:
                _print_zip_first_log(selected)
            print("=" * 80 + "\n")
            input("Press Enter to return to the list")
        except (ValueError, IndexError):
            logger.warning("Wrong choice")

if __name__ == "__main__":
    view_logs()
