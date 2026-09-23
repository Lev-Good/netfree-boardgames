# -*- coding: utf-8 -*-
"""
פלטפורמת משחקי לוח מקוונת בנטפרי - מרכז הלובי והמשחקים (Platform Hub)
עיצוב משחקי מודרני (Gaming Dark HUD)
מאפשר בחירה ופתיחה של שחמט, דמקה ושש-בש,
הצטרפות ישירה מקוד הזמנה חכם, ולובי מאוחד המציג את כל המשחקים הפעילים.
"""

import sys
import os
import random
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QComboBox, QMessageBox,
    QFrame, QTabWidget, QAbstractItemView, QGridLayout
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QIcon

from chess_window import ChessMainWindow
from checkers_window import CheckersMainWindow
from backgammon_window import BackgammonMainWindow
from chess_sync import ChessSyncManager, decode_invite_code
from google_sheets_client import (
    GoogleSheetsClient, extract_spreadsheet_id, load_config, save_config,
    setup_netfree_ca_bundle
)
from theme_style import (
    get_gaming_stylesheet, BG_DARK, PANEL_DARK, ACCENT_BLUE,
    ACCENT_GREEN, ACCENT_ORANGE, ACCENT_PURPLE, BORDER_COLOR
)


class PlatformLobbyWorker(QThread):
    finished_task = Signal(bool, list, str)

    def __init__(self, sync_mgr: ChessSyncManager, sheet_id: str, game_filter: Optional[str] = None):
        super().__init__()
        self.sync_mgr = sync_mgr
        self.sheet_id = sheet_id
        self.game_filter = game_filter

    def run(self):
        try:
            success, games, err = self.sync_mgr.fetch_lobby_games(
                spreadsheet_id=self.sheet_id,
                game_type_filter=self.game_filter
            )
            self.finished_task.emit(success, games or [], err or "")
        except Exception as e:
            self.finished_task.emit(False, [], str(e))


class PlatformMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(get_gaming_stylesheet())
        self.sheets_client = GoogleSheetsClient()
        self.sync_mgr = ChessSyncManager(self.sheets_client)

        cfg = load_config()
        saved_nick = cfg.get("player_nickname")
        if saved_nick:
            self.player_name = saved_nick
        else:
            self.player_name = f"{self.sheets_client.computer_name}#{random.randint(100, 999)}"
            save_config({"player_nickname": self.player_name})

        self.spreadsheet_id = cfg.get("spreadsheet_id", "")
        self.active_game_windows = []
        self.active_workers: List[PlatformLobbyWorker] = []

        self.init_ui()
        self.check_netfree_status()
        self.update_auth_ui()
        if self.spreadsheet_id:
            self.refresh_lobby()

    def update_auth_ui(self):
        logged_in = self.sheets_client.is_logged_in()
        if logged_in:
            self.lbl_account_status.setText("🟢 מחובר לחשבון Google")
            self.lbl_account_status.setStyleSheet("color: #34D399; font-weight: bold; background: #064E3B; border: 1px solid #059669; border-radius: 6px; padding: 5px 12px;")
            self.btn_account_login.hide()
            self.btn_account_logout.show()
        else:
            self.lbl_account_status.setText("⚪ לא מחובר ל-Google")
            self.lbl_account_status.setStyleSheet("color: #94A3B8; background: #1E293B; border: 1px solid #334155; border-radius: 6px; padding: 5px 12px;")
            self.btn_account_login.show()
            self.btn_account_logout.hide()

    def on_google_login_clicked(self):
        self.btn_account_login.setEnabled(False)
        self.btn_account_login.setText("מתחבר...")
        try:
            success, msg, _ = self.sheets_client.authenticate(prompt_browser=True)
            if success:
                QMessageBox.information(self, "התחברות הצליחה", "התחברת בהצלחה לחשבון Google!")
            else:
                QMessageBox.warning(self, "כשל בהתחברות", f"לא ניתן היה להתחבר:\n{msg}")
        except Exception as e:
            QMessageBox.critical(self, "שגיאה", f"תקלה בהתחברות:\n{e}")
        finally:
            self.btn_account_login.setEnabled(True)
            self.btn_account_login.setText("🔑 התחבר ל-Google")
            self.update_auth_ui()

    def on_google_logout_clicked(self):
        reply = QMessageBox.question(
            self, "התנתקות מחשבון Google",
            "האם ברצונך להתנתק מחשבון Google הנוכחי?\n(הפעולה תמחק את הטוקן המקומי ותאפשר לך להתחבר עם חשבון אחר)",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.sheets_client.logout()
            self.update_auth_ui()
            QMessageBox.information(self, "התנתקת בהצלחה", "ההתנתקות הושלמה בהצלחה.")

    def check_netfree_status(self):
        try:
            bundle_path = setup_netfree_ca_bundle()
            if os.path.exists(bundle_path):
                self.lbl_netfree.setText("🛡️ נטפרי פעיל: תעודת אבטחה מוטמעת ומאובטחת")
                self.lbl_netfree.setStyleSheet("color: #34D399; font-weight: bold; background: #064E3B; border: 1px solid #059669; border-radius: 6px; padding: 5px 12px;")
            else:
                self.lbl_netfree.setText("🌐 אינטרנט רגיל")
                self.lbl_netfree.setStyleSheet("color: #94A3B8; background: #1E293B; border-radius: 6px; padding: 5px 12px;")
        except Exception:
            self.lbl_netfree.setText("🌐 אינטרנט רגיל")
            self.lbl_netfree.setStyleSheet("color: #94A3B8; background: #1E293B; border-radius: 6px; padding: 5px 12px;")

    def init_ui(self):
        self.setWindowTitle("🎮 פלטפורמת משחקי לוח מקוונת בנטפרי – Gaming Hub")
        self.resize(1080, 780)
        self.setLayoutDirection(Qt.RightToLeft)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(22, 18, 22, 18)
        main_layout.setSpacing(16)

        # כותרת עליונה מעוצבת בסגנון Gaming Banner
        header_banner = QFrame()
        header_banner.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1E1B4B, stop:0.5 #1E293B, stop:1 #0F172A);
                border: 1px solid #3730A3;
                border-radius: 12px;
                padding: 14px 18px;
            }
        """)
        header_layout = QHBoxLayout(header_banner)
        header_layout.setContentsMargins(10, 4, 10, 4)

        title_col = QVBoxLayout()
        title_lbl = QLabel("🎮 פלטפורמת משחקי לוח מקוונת בנטפרי")
        title_lbl.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title_lbl.setStyleSheet("color: #818CF8; letter-spacing: 0.5px;")
        title_col.addWidget(title_lbl)

        sub_lbl = QLabel("משחקים מקוונים מותאמים 100% לסינון נטפרי ללא שרתים חיצוניים – על בסיס Google Sheets בלבד")
        sub_lbl.setFont(QFont("Segoe UI", 10))
        sub_lbl.setStyleSheet("color: #CBD5E1;")
        title_col.addWidget(sub_lbl)
        header_layout.addLayout(title_col, stretch=1)

        self.lbl_account_status = QLabel("⚪ בודק חשבון...")
        header_layout.addWidget(self.lbl_account_status)

        self.lbl_netfree = QLabel("🛡️ בודק נטפרי...")
        header_layout.addWidget(self.lbl_netfree)
        main_layout.addWidget(header_banner)

        # שורת הגדרות מהירות: כינוי + חשבון גוגל + מזהה שיטס
        top_bar = QFrame()
        top_bar.setStyleSheet("""
            QFrame {
                background-color: #161F2E;
                border: 1px solid #2B374E;
                border-radius: 10px;
                padding: 6px;
            }
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 6, 12, 6)

        lbl_nick = QLabel("👤 כינוי:")
        lbl_nick.setStyleSheet("color: #94A3B8; font-weight: bold;")
        top_layout.addWidget(lbl_nick)

        self.txt_nick = QLineEdit(self.player_name)
        self.txt_nick.setMaximumWidth(150)
        self.txt_nick.textChanged.connect(self._on_nick_changed)
        top_layout.addWidget(self.txt_nick)

        lbl_s = QLabel("📊 מזהה גיליון שיתוף:")
        lbl_s.setStyleSheet("color: #94A3B8; font-weight: bold;")
        top_layout.addWidget(lbl_s)

        self.txt_sheet = QLineEdit(self.spreadsheet_id)
        self.txt_sheet.setPlaceholderText("הדבק כתובת URL או מזהה גליון...")
        self.txt_sheet.textChanged.connect(self._on_sheet_changed)
        top_layout.addWidget(self.txt_sheet, stretch=1)

        self.btn_account_login = QPushButton("🔑 התחבר ל-Google")
        self.btn_account_login.setObjectName("btnPrimary")
        self.btn_account_login.setToolTip("התחברות לחשבון Google כדי לשחק ולפתוח חדרים")
        self.btn_account_login.clicked.connect(self.on_google_login_clicked)
        top_layout.addWidget(self.btn_account_login)

        self.btn_account_logout = QPushButton("🚪 התנתק")
        self.btn_account_logout.setObjectName("btnDanger")
        self.btn_account_logout.setToolTip("התנתק מחשבון Google הנוכחי והחלף חשבון")
        self.btn_account_logout.clicked.connect(self.on_google_logout_clicked)
        top_layout.addWidget(self.btn_account_logout)

        self.btn_create_sheet = QPushButton("📄 צור גליון חדש")
        self.btn_create_sheet.setObjectName("btnSuccess")
        self.btn_create_sheet.clicked.connect(self.on_create_sheet_clicked)
        top_layout.addWidget(self.btn_create_sheet)

        main_layout.addWidget(top_bar)

        # אזור כרטיסיות המשחקים (3 כרטיסיות גדולות ומעוצבות)
        games_grid = QGridLayout()
        games_grid.setSpacing(16)

        # 1. שחמט
        card_chess = self._create_game_card(
            title="♟️ שחמט (Chess)",
            desc="משחק המלכים הבינלאומי המלא לפי חוקי FIDE.\nכולל הצרחה, הכתרת כלי, שעונים דיגיטליים, צ'אט חי וניתוח מהלכים.",
            badges=["פיד\"ה מלא", "שעוני בליץ", "צ'אט חי", "PGN"],
            btn_text="הפעל שחמט ♟️",
            btn_id="btnPrimary",
            callback=self.launch_chess
        )
        games_grid.addWidget(card_chess, 0, 0)

        # 2. דמקה
        card_checkers = self._create_game_card(
            title="⚪ דמקה (Checkers)",
            desc="דמקה ישראלית / בינלאומית (8x8) על לוח עץ יוקרתי.\nחובת אכילה קפדנית, שרשרת קפיצות רציפה ודמקה (מלכה) מעופפת.",
            badges=["חובת אכילה", "שרשרת קפיצות", "דמקה מעופפת 👑", "8x8"],
            btn_text="הפעל דמקה ⚪",
            btn_id="btnSuccess",
            callback=self.launch_checkers
        )
        games_grid.addWidget(card_checkers, 0, 1)

        # 3. שש-בש
        card_backgammon = self._create_game_card(
            title="🎲 שש-בש (Backgammon)",
            desc="שש-בש מסורתי אותנטי עם 24 משולשים.\nקוביות תלת-ממדיות, כניסה מהמשקוף (Bar), אכילת כלים, הוצאה ומארס טורקי.",
            badges=["קוביות 3D ודאבל", "משקוף (Bar)", "אכילת Blot", "מארס טורקי"],
            btn_text="הפעל שש-בש 🎲",
            btn_id="btnWarning",
            callback=self.launch_backgammon
        )
        games_grid.addWidget(card_backgammon, 0, 2)

        main_layout.addLayout(games_grid)

        # אזור הצטרפות ישירה מקוד הזמנה חכם
        invite_box = QGroupBox("🚀 הצטרפות מהירה באמצעות קוד הזמנה חכם (Smart Invite Code)")
        inv_layout = QHBoxLayout(invite_box)

        self.txt_invite_code = QLineEdit()
        self.txt_invite_code.setPlaceholderText("הדבק כאן קוד הזמנה חכם מחבר (לדוגמה: NETFREE#1BxiM...#CHECKERS#Room_123)...")
        inv_layout.addWidget(self.txt_invite_code, stretch=1)

        self.btn_join_code = QPushButton("⚡ פתח והצטרף מיד")
        self.btn_join_code.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7C3AED, stop:1 #8B5CF6);
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 18px;
                border-radius: 7px;
                border: 1px solid #A78BFA;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6D28D9, stop:1 #A78BFA);
            }
        """)
        self.btn_join_code.clicked.connect(self.on_join_code_clicked)
        inv_layout.addWidget(self.btn_join_code)

        main_layout.addWidget(invite_box)

        # לובי חדרים מאוחד
        lobby_box = QGroupBox("📋 לובי חדרים פתוחים בכל המשחקים (Realtime Lobby)")
        lobby_layout = QVBoxLayout(lobby_box)

        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("סינון לפי משחק:"))
        self.cmb_lobby_filter = QComboBox()
        self.cmb_lobby_filter.addItems(["כל המשחקים", "שחמט בלבד (CHESS)", "דמקה בלבד (CHECKERS)", "שש-בש בלבד (BACKGAMMON)"])
        self.cmb_lobby_filter.currentIndexChanged.connect(self.refresh_lobby)
        filter_bar.addWidget(self.cmb_lobby_filter)

        filter_bar.addStretch()

        self.btn_refresh_lobby = QPushButton("🔄 רענן לובי")
        self.btn_refresh_lobby.clicked.connect(self.refresh_lobby)
        filter_bar.addWidget(self.btn_refresh_lobby)
        lobby_layout.addLayout(filter_bar)

        self.table_lobby = QTableWidget(0, 5)
        self.table_lobby.setHorizontalHeaderLabels(["משחק", "שם חדר", "מארח", "זמן", "פעולה"])
        self.table_lobby.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_lobby.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lobby_layout.addWidget(self.table_lobby)

        main_layout.addWidget(lobby_box, stretch=1)

        self.setCentralWidget(main_widget)

    def _create_game_card(self, title: str, desc: str, badges: List[str], btn_text: str, btn_id: str, callback) -> QFrame:
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {PANEL_DARK};
                border: 1.5px solid {BORDER_COLOR};
                border-radius: 12px;
                padding: 14px;
            }}
            QFrame:hover {{
                border: 1.5px solid #475569;
                background-color: #1C2637;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        lbl_t = QLabel(title)
        lbl_t.setFont(QFont("Segoe UI", 15, QFont.Bold))
        lbl_t.setStyleSheet("color: #FFFFFF;")
        layout.addWidget(lbl_t)

        lbl_d = QLabel(desc)
        lbl_d.setWordWrap(True)
        lbl_d.setFont(QFont("Segoe UI", 9))
        lbl_d.setStyleSheet("color: #94A3B8; min-height: 48px;")
        layout.addWidget(lbl_d)

        # תגיות משחק
        badges_layout = QHBoxLayout()
        badges_layout.setSpacing(4)
        for b in badges:
            b_lbl = QLabel(b)
            b_lbl.setStyleSheet("background-color: #0F172A; color: #38BDF8; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 6px; border: 1px solid #1E293B;")
            badges_layout.addWidget(b_lbl)
        badges_layout.addStretch()
        layout.addLayout(badges_layout)

        btn = QPushButton(btn_text)
        btn.setObjectName(btn_id)
        btn.setFixedHeight(38)
        btn.clicked.connect(callback)
        layout.addWidget(btn)

        return card

    def _on_nick_changed(self, text: str):
        self.player_name = text.strip()
        cfg = load_config()
        cfg["player_nickname"] = self.player_name
        cfg["player_name"] = self.player_name
        save_config(cfg)

    def _on_sheet_changed(self, text: str):
        self.spreadsheet_id = extract_spreadsheet_id(text.strip())
        cfg = load_config()
        cfg["spreadsheet_id"] = self.spreadsheet_id
        save_config(cfg)

    def on_create_sheet_clicked(self):
        if not self.sheets_client.is_logged_in():
            success, msg, _ = self.sheets_client.authenticate(prompt_browser=True)
            self.update_auth_ui()
            if not success:
                QMessageBox.critical(self, "נדרשת התחברות Google", f"יש להתחבר לחשבון Google כדי ליצור גיליון משחקים:\n{msg}")
                return

        self.btn_create_sheet.setEnabled(False)
        self.btn_create_sheet.setText("יוצר גליון...")

        def _do_create():
            try:
                success, sheet_id, sheet_url = self.sheets_client.create_new_spreadsheet("פלטפורמת משחקי לוח בנטפרי")
                if success:
                    self.txt_sheet.setText(sheet_id)
                    self.spreadsheet_id = sheet_id
                    self.update_auth_ui()
                    QMessageBox.information(self, "נוצר בהצלחה!", f"נוצר גליון Google Sheets חדש ומותאם:\n{sheet_id}\n\nהגליון מוכן לשימוש בכל המשחקים.")
                    self.refresh_lobby()
                else:
                    QMessageBox.warning(self, "שגיאה ביצירת גליון", str(sheet_id))
            except Exception as e:
                QMessageBox.critical(self, "שגיאה", f"אירעה תקלה:\n{e}")
            finally:
                self.btn_create_sheet.setEnabled(True)
                self.btn_create_sheet.setText("📄 צור גליון חדש")

        _do_create()

    def launch_chess(self, sheet_id: Optional[str] = None, room_id: Optional[str] = None, color: Optional[str] = None):
        try:
            w = ChessMainWindow()
            if sheet_id and hasattr(w, "txt_sheet_id"):
                w.txt_sheet_id.setText(sheet_id)
            if room_id and hasattr(w, "txt_game_id"):
                w.txt_game_id.setText(room_id)
            if color == "B" and hasattr(w, "combo_mode"):
                w.combo_mode.setCurrentIndex(1)  # שחור
            self.active_game_windows.append(w)
            w.show()
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בהפעלת שחמט", f"לא ניתן להפעיל את משחק השחמט:\n{e}")

    def launch_checkers(self, sheet_id: Optional[str] = None, room_id: Optional[str] = None, color: Optional[str] = None):
        try:
            w = CheckersMainWindow()
            if sheet_id and hasattr(w, "txt_sheet_id"):
                w.txt_sheet_id.setText(sheet_id)
            if room_id and hasattr(w, "txt_room_id"):
                w.txt_room_id.setText(room_id)
            if color == "B":
                if hasattr(w, "combo_mode"):
                    w.combo_mode.setCurrentIndex(1)
                elif hasattr(w, "cmb_mode"):
                    w.cmb_mode.setCurrentIndex(1)
            self.active_game_windows.append(w)
            w.show()
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בהפעלת דמקה", f"לא ניתן להפעיל את משחק הדמקה:\n{e}")

    def launch_backgammon(self, sheet_id: Optional[str] = None, room_id: Optional[str] = None, color: Optional[str] = None):
        try:
            w = BackgammonMainWindow()
            if sheet_id and hasattr(w, "txt_sheet_id"):
                w.txt_sheet_id.setText(sheet_id)
            if room_id and hasattr(w, "txt_room_id"):
                w.txt_room_id.setText(room_id)
            if color == "B":
                if hasattr(w, "cmb_mode"):
                    w.cmb_mode.setCurrentIndex(1)
                elif hasattr(w, "combo_mode"):
                    w.combo_mode.setCurrentIndex(1)
            self.active_game_windows.append(w)
            w.show()
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בהפעלת שש-בש", f"לא ניתן להפעיל את משחק השש-בש:\n{e}")

    def on_join_code_clicked(self):
        code = self.txt_invite_code.text().strip()
        if not code:
            QMessageBox.information(self, "הזן קוד", "נא להדביק קוד הזמנה חכם מחבר.")
            return

        sheet_id, room_id, game_type = decode_invite_code(code)
        if not sheet_id or not room_id:
            QMessageBox.warning(self, "קוד שגוי", "מבנה קוד ההזמנה אינו תקין.")
            return

        g_type = (game_type or "CHESS").upper()
        if "CHECKER" in g_type or "דמקה" in g_type:
            self.launch_checkers(sheet_id=sheet_id, room_id=room_id, color="B")
        elif "BACKGAMMON" in g_type or "שש" in g_type:
            self.launch_backgammon(sheet_id=sheet_id, room_id=room_id, color="B")
        else:
            self.launch_chess(sheet_id=sheet_id, room_id=room_id, color="B")

    def refresh_lobby(self):
        if not self.spreadsheet_id:
            return

        f_idx = self.cmb_lobby_filter.currentIndex()
        filter_map = [None, "CHESS", "CHECKERS", "BACKGAMMON"]
        g_filter = filter_map[f_idx]

        worker = PlatformLobbyWorker(self.sync_mgr, self.spreadsheet_id, g_filter)
        self.active_workers.append(worker)

        def _on_done(success, games, err):
            try:
                if success:
                    self._update_lobby_table(games)
            finally:
                if worker in self.active_workers:
                    self.active_workers.remove(worker)
                worker.deleteLater()

        worker.finished_task.connect(_on_done)
        worker.start()

    def _update_lobby_table(self, games: List[Dict[str, Any]]):
        self.table_lobby.setRowCount(0)
        for g in games:
            row = self.table_lobby.rowCount()
            self.table_lobby.insertRow(row)

            g_type = g.get("game_type", "CHESS")
            if g_type == "CHECKERS":
                type_display = "⚪ דמקה"
            elif g_type == "BACKGAMMON":
                type_display = "🎲 שש-בש"
            else:
                type_display = "♟️ שחמט"

            r_id = g.get("room_id", "")
            host = g.get("host_name", "")
            tc = g.get("time_control", "")

            self.table_lobby.setItem(row, 0, QTableWidgetItem(type_display))
            self.table_lobby.setItem(row, 1, QTableWidgetItem(r_id))
            self.table_lobby.setItem(row, 2, QTableWidgetItem(host))
            self.table_lobby.setItem(row, 3, QTableWidgetItem(tc))

            btn_join = QPushButton("הצטרף")
            btn_join.setObjectName("btnPrimary")
            btn_join.setFixedHeight(28)
            btn_join.clicked.connect(lambda _, gt=g_type, rid=r_id: self._join_room_from_lobby(gt, rid))
            self.table_lobby.setCellWidget(row, 4, btn_join)

    def _join_room_from_lobby(self, game_type: str, room_id: str):
        if game_type == "CHECKERS":
            self.launch_checkers(sheet_id=self.spreadsheet_id, room_id=room_id, color="B")
        elif game_type == "BACKGAMMON":
            self.launch_backgammon(sheet_id=self.spreadsheet_id, room_id=room_id, color="B")
        else:
            self.launch_chess(sheet_id=self.spreadsheet_id, room_id=room_id, color="B")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PlatformMainWindow()
    window.show()
    sys.exit(app.exec())
