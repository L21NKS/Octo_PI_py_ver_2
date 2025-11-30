#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import importlib, sys
from logger import logger

MENU = """
Select the mode:
 1) Web version (panel /web, API /docs)
 2) Terminal version (menu in the console)
 q) Exit
> """

def main():
    while True:
        try:
            choice = input(MENU).strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "q"

        if choice == "1":
            try:
                mod = importlib.import_module("octo_web")
                if hasattr(mod, "main"):
                    mod.main()        # блокируется до выхода через /app/exit
                else:
                    logger.error("Not found octo_web.main()")
            except Exception as e:
                logger.exception(f"Web-version: {e}")

        elif choice == "2":
            try:
                mod = importlib.import_module("octo_cli")
                if hasattr(mod, "SurveillanceSystem"):
                    mod.SurveillanceSystem().main_menu()
                else:
                    logger.error("Not found class SurveillanceSystem в octo_cli")
            except Exception as e:
                logger.exception(f"CLI-version: {e}")
        elif choice in ("q"):
            logger.info("Exit."); sys.exit(0)
        else:
            logger.warning("Incorrect choice. Enter 1, 2, or q.")

if __name__ == "__main__":
    main()
