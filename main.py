# -*- coding: utf-8 -*-
"""
נקודת כניסה ראשית עבור פלטפורמת משחקי לוח מקוונת בנטפרי (שחמט, דמקה, שש-בש)
מריץ כברירת מחדל את מסך הבית ומרכז המשחקים (Platform Hub),
ומאפשר הרצה ישירה של משחק ספציפי באמצעות דגלים:
--chess, --checkers, --backgammon, --test
"""

import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox
import traceback

def install_global_exception_handler():
    def _handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        try:
            log_path = os.path.join(CURRENT_DIR, "crash.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- CRASH AT {traceback.format_exc()} ---\n{err_msg}\n")
        except Exception:
            pass

        print(err_msg, file=sys.stderr)
        try:
            app = QApplication.instance()
            if app:
                QMessageBox.critical(
                    None,
                    "שגיאה בלתי צפויה",
                    f"אירעה שגיאה בתוכנה:\n{exc_value}\n\nהפרטים נשמרו בקובץ crash.log"
                )
        except Exception:
            pass

    sys.excepthook = _handle_exception

def main():
    install_global_exception_handler()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    if "--test" in sys.argv:
        from app_gui import run_gui
        run_gui()
        return

    if "--chess" in sys.argv:
        from chess_window import ChessMainWindow
        win = ChessMainWindow()
        win.show()
    elif "--checkers" in sys.argv:
        from checkers_window import CheckersMainWindow
        win = CheckersMainWindow()
        win.show()
    elif "--backgammon" in sys.argv:
        from backgammon_window import BackgammonMainWindow
        win = BackgammonMainWindow()
        win.show()
    else:
        from platform_window import PlatformMainWindow
        win = PlatformMainWindow()
        win.show()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()
