# -*- coding: utf-8 -*-
"""
ממשק משתמש שולחני עבור בדיקת Google Sheets API בנטפרי
מבוסס PySide6 עם תמיכה מלאה ב-RTL (יישור לימין) ועיצוב מודרני.
"""

import os
import sys
import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QProgressBar, QFrame, QScrollArea
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QIcon, QColor

from google_sheets_client import GoogleSheetsClient, extract_spreadsheet_id, SheetsErrorType, load_config, save_config


class WorkerThread(QThread):
    """תהליך רקע למניעת תקיעת הממשק בעת ביצוע פניות רשת ו-OAuth"""
    finished = Signal(dict)
    step_update = Signal(int, str, bool)

    def __init__(self, action_type: str, client: GoogleSheetsClient, **kwargs):
        super().__init__()
        self.action_type = action_type
        self.client = client
        self.kwargs = kwargs

    def run(self):
        result = {}
        try:
            if self.action_type == "auth":
                success, msg, err_type = self.client.authenticate(prompt_browser=True)
                result = {"success": success, "message": msg, "error_type": err_type}

            elif self.action_type == "read":
                sheet_id = self.kwargs.get("sheet_id", "")
                sheet_name = self.kwargs.get("sheet_name", "Sheet1")
                success, data, err_type = self.client.read_sheet(sheet_id, sheet_name)
                result = {"success": success, "data": data, "error_type": err_type}

            elif self.action_type == "write":
                sheet_id = self.kwargs.get("sheet_id", "")
                sheet_name = self.kwargs.get("sheet_name", "Sheet1")
                custom_values = self.kwargs.get("values", None)
                success, data, err_type = self.client.write_row(sheet_id, sheet_name, custom_values)
                result = {"success": success, "data": data, "error_type": err_type}

            elif self.action_type == "full_test":
                sheet_id = self.kwargs.get("sheet_id", "")
                sheet_name = self.kwargs.get("sheet_name", "Sheet1")

                def on_step(step_num, message, is_success):
                    self.step_update.emit(step_num, message, is_success)

                test_report = self.client.run_full_test(sheet_id, sheet_name, progress_cb=on_step)
                result = {"report": test_report}

            elif self.action_type == "send_move":
                sheet_id = self.kwargs.get("sheet_id", "")
                sheet_name = self.kwargs.get("sheet_name", "Sheet1")
                player = self.kwargs.get("player", "")
                msg = self.kwargs.get("message", "")
                success, status_text = self.client.send_game_message(sheet_id, sheet_name, player, msg)
                result = {"success": success, "message": status_text}

            elif self.action_type == "poll":
                sheet_id = self.kwargs.get("sheet_id", "")
                sheet_name = self.kwargs.get("sheet_name", "Sheet1")
                success, rows, err = self.client.read_all_moves(sheet_id, sheet_name)
                result = {"success": success, "rows": rows, "error": err}

        except Exception as e:
            result = {"success": False, "message": str(e), "error_type": SheetsErrorType.OTHER_ERROR}

        self.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.client = GoogleSheetsClient()
        self.polling_timer = QTimer(self)
        self.polling_timer.timeout.connect(self.on_polling_tick)
        self.last_poll_rows_count = 0
        self.worker = None

        self.init_ui()
        self.update_auth_status_ui()
        self.check_credentials_file_ui()

    def init_ui(self):
        self.setWindowTitle("בדיקת Google Sheets API – פלטפורמת משחק בנטפרי")
        self.resize(920, 840)
        self.setMinimumSize(820, 720)

        # סגנון מודרני ונקי
        self.setStyleSheet("""
            QWidget {
                font-family: 'Segoe UI', 'Arial', sans-serif;
                font-size: 14px;
                color: #202124;
            }
            QMainWindow {
                background-color: #F8F9FA;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #DADCE0;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 14px;
                background-color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top right;
                padding: 0 10px;
                color: #1A73E8;
            }
            QLineEdit {
                border: 1px solid #DADCE0;
                border-radius: 6px;
                padding: 8px 12px;
                background-color: #FFFFFF;
            }
            QLineEdit:focus {
                border: 2px solid #1A73E8;
            }
            QPushButton {
                background-color: #1A73E8;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 9px 18px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1557B0;
            }
            QPushButton:disabled {
                background-color: #BDC1C6;
                color: #FFFFFF;
            }
            QPushButton#btnSecondary {
                background-color: #E8F0FE;
                color: #1967D2;
                border: 1px solid #DADCE0;
            }
            QPushButton#btnSecondary:hover {
                background-color: #D2E3FC;
            }
            QPushButton#btnFullTest {
                background-color: #0D652D;
                font-size: 15px;
                padding: 12px 24px;
            }
            QPushButton#btnFullTest:hover {
                background-color: #08481F;
            }
            QTextEdit {
                border: 1px solid #DADCE0;
                border-radius: 6px;
                background-color: #FFFFFF;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 13px;
            }
            QTabWidget::pane {
                border: 1px solid #DADCE0;
                border-radius: 8px;
                background-color: #FFFFFF;
            }
            QTabBar::tab {
                background: #E8EAED;
                border: 1px solid #DADCE0;
                padding: 10px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-left: 2px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #FFFFFF;
                border-bottom: 2px solid #1A73E8;
                color: #1A73E8;
            }
            QTableWidget {
                border: 1px solid #DADCE0;
                border-radius: 6px;
                gridline-color: #E8EAED;
                background-color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #F1F3F4;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #DADCE0;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 15, 20, 15)
        main_layout.setSpacing(12)

        # 1. כותרת עליונה
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        lbl_title = QLabel("בדיקת Google Sheets API")
        lbl_title.setStyleSheet("font-size: 22px; font-weight: bold; color: #202124;")
        lbl_subtitle = QLabel("ניסוי תקשורת עם שרתי Google תחת סינון נטפרי עבור פלטפורמת משחק מקוון")
        lbl_subtitle.setStyleSheet("font-size: 13px; color: #5F6368;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_subtitle)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        btn_guide = QPushButton("הוראות הגדרה ו-OAuth")
        btn_guide.setObjectName("btnSecondary")
        btn_guide.clicked.connect(self.show_guide_dialog)
        header_layout.addWidget(btn_guide)

        btn_open_chess = QPushButton("פתח שחמט מקוון ♟")
        btn_open_chess.setStyleSheet("background-color: #188038; color: white; font-weight: bold;")
        btn_open_chess.clicked.connect(self.open_chess_game)
        header_layout.addWidget(btn_open_chess)
        main_layout.addLayout(header_layout)


        # 2. סרגל סטטוס קובץ credentials.json
        self.credentials_bar = QFrame()
        self.credentials_bar.setStyleSheet("""
            QFrame {
                background-color: #FFF3CD;
                border: 1px solid #FFEBAA;
                border-radius: 6px;
                padding: 6px 12px;
            }
        """)
        creds_bar_layout = QHBoxLayout(self.credentials_bar)
        creds_bar_layout.setContentsMargins(10, 4, 10, 4)
        self.lbl_creds_status = QLabel("בודק קובץ credentials.json...")
        self.lbl_creds_status.setStyleSheet("font-size: 13px; color: #856404; font-weight: bold;")
        creds_bar_layout.addWidget(self.lbl_creds_status)
        creds_bar_layout.addStretch()

        self.btn_browse_creds = QPushButton("טען קובץ credentials.json...")
        self.btn_browse_creds.setObjectName("btnSecondary")
        self.btn_browse_creds.clicked.connect(self.browse_credentials_file)
        creds_bar_layout.addWidget(self.btn_browse_creds)
        main_layout.addWidget(self.credentials_bar)

        # 3. לשוניות ראשיות
        self.tabs = QTabWidget()
        self.tab_test = QWidget()
        self.tab_multiplayer = QWidget()

        self.setup_test_tab()
        self.setup_multiplayer_tab()

        self.tabs.addTab(self.tab_test, "בדיקת תקשורת וקריאה/כתיבה (סעיפים 1-10)")
        self.tabs.addTab(self.tab_multiplayer, "תקשורת בין 2 מחשבים ו-Polling (סעיפים 11-13)")
        main_layout.addWidget(self.tabs)

        # מד התקדמות כללי
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

    def setup_test_tab(self):
        """הקמת לשונית הבדיקה הראשית לפי סעיפים 6-10 באפיון"""
        layout = QVBoxLayout(self.tab_test)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # אזור הגדרות גיליון וחיבור
        group_inputs = QGroupBox("הגדרות Google Sheet והתחברות")
        inputs_layout = QVBoxLayout(group_inputs)

        # שורה 1: מזהה הגיליון
        row1 = QHBoxLayout()
        lbl_sheet_id = QLabel("מזהה Google Sheet:")
        lbl_sheet_id.setFixedWidth(160)
        saved_sheet_id = load_config().get("spreadsheet_id", "")
        self.txt_sheet_id = QLineEdit(saved_sheet_id)
        self.txt_sheet_id.setPlaceholderText("הדבק כאן את מזהה הגיליון או את כתובת ה-URL המלאה מ-Google Sheets")
        self.txt_sheet_id.textChanged.connect(lambda t: save_config({"spreadsheet_id": t.strip()}))
        row1.addWidget(lbl_sheet_id)
        row1.addWidget(self.txt_sheet_id)
        inputs_layout.addLayout(row1)


        # שורה 2: שם הלשונית
        row2 = QHBoxLayout()
        lbl_sheet_name = QLabel("שם הלשונית:")
        lbl_sheet_name.setFixedWidth(160)
        self.txt_sheet_name = QLineEdit("Sheet1")
        self.txt_sheet_name.setFixedWidth(200)
        row2.addWidget(lbl_sheet_name)
        row2.addWidget(self.txt_sheet_name)
        row2.addStretch()
        inputs_layout.addLayout(row2)

        # שורה 3: סטטוס התחברות וכפתורי חשבון
        row3 = QHBoxLayout()
        lbl_auth_title = QLabel("סטטוס התחברות Google:")
        lbl_auth_title.setFixedWidth(160)
        self.lbl_auth_badge = QLabel("לא מחובר")
        self.lbl_auth_badge.setStyleSheet("color: #D93025; font-weight: bold;")
        row3.addWidget(lbl_auth_title)
        row3.addWidget(self.lbl_auth_badge)
        row3.addSpacing(20)

        self.btn_auth = QPushButton("התחבר ל-Google")
        self.btn_auth.clicked.connect(self.on_btn_auth_clicked)
        row3.addWidget(self.btn_auth)

        self.btn_logout = QPushButton("התנתק")
        self.btn_logout.setObjectName("btnSecondary")
        self.btn_logout.clicked.connect(self.on_btn_logout_clicked)
        self.btn_logout.hide()
        row3.addWidget(self.btn_logout)

        row3.addStretch()
        inputs_layout.addLayout(row3)

        layout.addWidget(group_inputs)

        # אזור כפתורי פעולה
        group_actions = QGroupBox("בדיקות פעולה")
        actions_layout = QHBoxLayout(group_actions)
        actions_layout.setSpacing(12)

        self.btn_read = QPushButton("בדוק קריאה")
        self.btn_read.setObjectName("btnSecondary")
        self.btn_read.clicked.connect(self.on_btn_read_clicked)

        self.btn_write = QPushButton("בדוק כתיבה")
        self.btn_write.setObjectName("btnSecondary")
        self.btn_write.clicked.connect(self.on_btn_write_clicked)

        self.btn_full = QPushButton("בדיקה מלאה (5 שלבים)")
        self.btn_full.setObjectName("btnFullTest")
        self.btn_full.clicked.connect(self.on_btn_full_clicked)

        actions_layout.addWidget(self.btn_read)
        actions_layout.addWidget(self.btn_write)
        actions_layout.addWidget(self.btn_full)
        layout.addWidget(group_actions)

        # אזור תוצאות (סעיף 8 באפיון)
        group_results = QGroupBox("אזור תוצאות ואבחון נטפרי")
        results_layout = QVBoxLayout(group_results)

        # תצוגת שלבים מובנית
        self.steps_frame = QFrame()
        self.steps_frame.setStyleSheet("background-color: #F8F9FA; border-radius: 6px; padding: 6px;")
        steps_layout = QVBoxLayout(self.steps_frame)
        steps_layout.setSpacing(4)

        self.lbl_step1 = QLabel("שלב 1 – התחברות: ממתין לבדיקה")
        self.lbl_step2 = QLabel("שלב 2 – Google Sheets API: ממתין לבדיקה")
        self.lbl_step3 = QLabel("שלב 3 – קריאה: ממתין לבדיקה")
        self.lbl_step4 = QLabel("שלב 4 – כתיבה: ממתין לבדיקה")
        self.lbl_step5 = QLabel("שלב 5 – קריאה חוזרת: ממתין לבדיקה")

        for lbl in [self.lbl_step1, self.lbl_step2, self.lbl_step3, self.lbl_step4, self.lbl_step5]:
            lbl.setStyleSheet("font-size: 13px; color: #3C4043;")
            steps_layout.addWidget(lbl)

        results_layout.addWidget(self.steps_frame)

        # כרטיס תוצאה סופית בולט (סעיף 8)
        self.final_banner = QFrame()
        self.final_banner.setStyleSheet("""
            QFrame {
                background-color: #E8EAED;
                border: 2px solid #DADCE0;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        banner_layout = QVBoxLayout(self.final_banner)
        banner_layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_banner_title = QLabel("טרם בוצעה בדיקה מלאה")
        self.lbl_banner_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #3C4043;")
        self.lbl_banner_desc = QLabel("לחץ על 'בדיקה מלאה' או בצע בדיקות קריאה/כתיבה בודדות.")
        self.lbl_banner_desc.setStyleSheet("font-size: 13px; color: #5F6368;")
        self.lbl_banner_desc.setWordWrap(True)

        banner_layout.addWidget(self.lbl_banner_title)
        banner_layout.addWidget(self.lbl_banner_desc)
        results_layout.addWidget(self.final_banner)

        # לוג מפורט
        lbl_log_title = QLabel("יומן דיאגנוסטיקה מפורט (לוג):")
        lbl_log_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #5F6368; margin-top: 4px;")
        results_layout.addWidget(lbl_log_title)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFixedHeight(120)
        results_layout.addWidget(self.txt_log)

        layout.addWidget(group_results)

    def setup_multiplayer_tab(self):
        """לשונית העברת מהלכים ו-Polling (סעיפים 11-13 באפיון)"""
        layout = QVBoxLayout(self.tab_multiplayer)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        info_box = QLabel(
            "לשונית זו מאפשרת לבדוק תקשורת דו-כיוונית בין שני מחשבים מחוברים בנטפרי (סעיפים 11-13 באפיון).\n"
            "מחשב א' שולח מהלך/הודעה, ומחשב ב' מקבל אותו דרך Google Sheets באמצעות מנגנון דגימה מחזורי (Polling)."
        )
        info_box.setStyleSheet("background-color: #E8F0FE; color: #174EA6; padding: 10px; border-radius: 6px;")
        layout.addWidget(info_box)

        # אזור שליחה
        group_send = QGroupBox("שליחת מהלך / הודעה חדשה לגיליון")
        send_layout = QVBoxLayout(group_send)

        row_sender = QHBoxLayout()
        lbl_player = QLabel("שם השחקן / מחשב:")
        lbl_player.setFixedWidth(140)
        self.txt_player_name = QLineEdit(self.client.computer_name)
        self.txt_player_name.setFixedWidth(200)
        row_sender.addWidget(lbl_player)
        row_sender.addWidget(self.txt_player_name)
        row_sender.addStretch()
        send_layout.addLayout(row_sender)

        row_msg = QHBoxLayout()
        lbl_msg = QLabel("תוכן המהלך / הודעה:")
        lbl_msg.setFixedWidth(140)
        self.txt_move_content = QLineEdit("שלום ממחשב " + self.client.computer_name)
        row_msg.addWidget(lbl_msg)
        row_msg.addWidget(self.txt_move_content)

        self.btn_send_move = QPushButton("שלח מהלך לגיליון")
        self.btn_send_move.clicked.connect(self.on_btn_send_move_clicked)
        row_msg.addWidget(self.btn_send_move)
        send_layout.addLayout(row_msg)

        layout.addWidget(group_send)

        # אזור קבלה ו-Polling
        group_feed = QGroupBox("סנכרון והאזנה למהלכים מהמחשב השני (Polling)")
        feed_layout = QVBoxLayout(group_feed)

        poll_bar = QHBoxLayout()
        self.btn_toggle_poll = QPushButton("הפעל האזנה אוטומטית (Polling)")
        self.btn_toggle_poll.clicked.connect(self.toggle_polling)
        poll_bar.addWidget(self.btn_toggle_poll)

        self.btn_refresh_now = QPushButton("רענן עכשיו ידנית")
        self.btn_refresh_now.setObjectName("btnSecondary")
        self.btn_refresh_now.clicked.connect(self.on_polling_tick)
        poll_bar.addWidget(self.btn_refresh_now)

        poll_bar.addStretch()
        self.lbl_poll_status = QLabel("האזנה כבויה")
        self.lbl_poll_status.setStyleSheet("color: #5F6368; font-weight: bold;")
        poll_bar.addWidget(self.lbl_poll_status)

        feed_layout.addLayout(poll_bar)

        # טבלת מהלכים שהתקבלו
        self.table_moves = QTableWidget()
        self.table_moves.setColumnCount(4)
        self.table_moves.setHorizontalHeaderLabels(["פעולה", "שעה", "שחקן / מחשב", "מהלך / תוכן"])
        self.table_moves.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        feed_layout.addWidget(self.table_moves)

        layout.addWidget(group_feed)

    # ------------------ עזרים ועדכוני ממשק ------------------

    def log(self, text: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt_log.append(f"[{now}] {text}")

    def check_credentials_file_ui(self):
        exists = self.client.credentials_file_exists()
        if exists:
            self.lbl_creds_status.setText(f"✅ קובץ ההגדרות '{os.path.basename(self.client.credentials_path)}' נמצא ומוכן לפעולה.")
            self.credentials_bar.setStyleSheet("""
                QFrame {
                    background-color: #E6F4EA;
                    border: 1px solid #CEEAD6;
                    border-radius: 6px;
                    padding: 6px 12px;
                }
            """)
            self.lbl_creds_status.setStyleSheet("font-size: 13px; color: #137333; font-weight: bold;")
            self.btn_browse_creds.setText("החלף קובץ credentials.json...")
        else:
            self.lbl_creds_status.setText("⚠️ חסר קובץ credentials.json. יש להוריד אותו מ-Google Cloud Console.")
            self.credentials_bar.setStyleSheet("""
                QFrame {
                    background-color: #FEF7E0;
                    border: 1px solid #FEEFC3;
                    border-radius: 6px;
                    padding: 6px 12px;
                }
            """)
            self.lbl_creds_status.setStyleSheet("font-size: 13px; color: #B06000; font-weight: bold;")
            self.btn_browse_creds.setText("טען קובץ credentials.json...")

    def update_auth_status_ui(self):
        if self.client.is_logged_in():
            self.lbl_auth_badge.setText("✅ מחובר ל-Google")
            self.lbl_auth_badge.setStyleSheet("color: #137333; font-weight: bold;")
            self.btn_auth.setText("התחבר מחדש / החלף חשבון")
            self.btn_logout.show()
        else:
            self.lbl_auth_badge.setText("❌ לא מחובר")
            self.lbl_auth_badge.setStyleSheet("color: #D93025; font-weight: bold;")
            self.btn_auth.setText("התחבר ל-Google")
            self.btn_logout.hide()

    def set_loading(self, loading: bool):
        if loading:
            self.progress_bar.show()
            self.btn_auth.setEnabled(False)
            self.btn_read.setEnabled(False)
            self.btn_write.setEnabled(False)
            self.btn_full.setEnabled(False)
        else:
            self.progress_bar.hide()
            self.btn_auth.setEnabled(True)
            self.btn_read.setEnabled(True)
            self.btn_write.setEnabled(True)
            self.btn_full.setEnabled(True)

    def browse_credentials_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "בחר קובץ credentials.json מ-Google Cloud Console",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        if filepath:
            self.client.set_credentials_file(filepath)
            self.check_credentials_file_ui()
            self.log(f"נטען קובץ הגדרות: {filepath}")

    def show_guide_dialog(self):
        guide_text = (
            "הוראות הגדרה ב-Google Cloud Console:\n\n"
            "1. היכנס אל console.cloud.google.com וצור פרויקט חדש.\n"
            "2. בספריית ה-APIs הפעל את Google Sheets API.\n"
            "3. במסך ההסכמה (OAuth Consent Screen) הגדר משתמש בדיקה (Test User) עם כתובת המייל שלך.\n"
            "4. ב-Credentials צור OAuth Client ID מסוג Desktop App והורד את קובץ ה-JSON.\n"
            "5. שנה את שמו ל-credentials.json ושמור אותו בתיקיית התוכנה, או טען אותו באמצעות הכפתור בתוכנה.\n"
            "6. פתח Google Sheet חדש, העתק את הקישור שלו לשדה בתוכנה, וודא שיש לך הרשאת עריכה."
        )
        QMessageBox.information(self, "הוראות הגדרת Google Cloud", guide_text)

    def open_chess_game(self):
        try:
            from chess_window import ChessMainWindow
            self.chess_win = ChessMainWindow()
            self.chess_win.show()
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בפתיחת שחמט", f"לא ניתן לפתוח את משחק השחמט:\n{e}")

    # ------------------ אירועי כפתורים ------------------


    def on_btn_auth_clicked(self):
        if not self.client.credentials_file_exists():
            QMessageBox.warning(
                self,
                "חסר קובץ credentials.json",
                "קובץ ההגדרות credentials.json אינו קיים בתיקייה.\n"
                "יש להוריד אותו מ-Google Cloud Console ולהניח אותו בתיקייה, או לטעון אותו בעזרת הכפתור הצהוב למעלה."
            )
            return

        self.set_loading(True)
        self.log("פותח התחברות ל-Google בדפדפן...")

        self.worker = WorkerThread("auth", self.client)
        self.worker.finished.connect(self.on_auth_finished)
        self.worker.start()

    def on_auth_finished(self, res: dict):
        self.set_loading(False)
        if res.get("success"):
            self.log("✅ התחברות ל-Google הצליחה!")
            self.update_auth_status_ui()
            QMessageBox.information(self, "התחברות הצליחה", "ההתחברות לחשבון Google בוצעה בהצלחה!")
        else:
            msg = res.get("message", "שגיאה לא ידועה בהתחברות")
            self.log(f"❌ כשל בהתחברות: {msg}")
            self.update_auth_status_ui()
            QMessageBox.critical(self, "כשל בהתחברות", msg)

    def on_btn_logout_clicked(self):
        self.client.logout()
        self.update_auth_status_ui()
        self.log("המשתמש התנתק. קובץ token.json נמחק.")
        QMessageBox.information(self, "התנתקות", "הטוקן נמחק בהצלחה. החיבור נותק.")

    def on_btn_read_clicked(self):
        sheet_id = self.txt_sheet_id.text().strip()
        sheet_name = self.txt_sheet_name.text().strip() or "Sheet1"

        if not sheet_id:
            QMessageBox.warning(self, "שגיאה", "נא להזין מזהה Google Sheet או להדביק קישור מלא.")
            return

        self.set_loading(True)
        self.log(f"מנסה לקרוא נתונים מגיליון {sheet_name}...")

        self.worker = WorkerThread("read", self.client, sheet_id=sheet_id, sheet_name=sheet_name)
        self.worker.finished.connect(self.on_read_finished)
        self.worker.start()

    def on_read_finished(self, res: dict):
        self.set_loading(False)
        if res.get("success"):
            data = res.get("data", [])
            row_count = len(data)
            self.log(f"✅ קריאת נתונים הצליחה! נקראו {row_count} שורות.")

            # הצגת נתונים לדוגמה
            sample = ""
            for i, row in enumerate(data[:5]):
                sample += f"שורה {i+1}: {', '.join(str(c) for c in row)}\n"

            msg = f"קריאת הנתונים הצליחה בהצלחה!\nנמצאו {row_count} שורות בגיליון.\n\nדוגמה לשורות ראשונות:\n{sample}"
            QMessageBox.information(self, "בדיקת קריאה הצליחה", msg)
        else:
            err = res.get("data", "")
            self.log(f"❌ שגיאה בקריאה: {err}")
            QMessageBox.critical(self, "שגיאה בקריאה", str(err))

    def on_btn_write_clicked(self):
        sheet_id = self.txt_sheet_id.text().strip()
        sheet_name = self.txt_sheet_name.text().strip() or "Sheet1"

        if not sheet_id:
            QMessageBox.warning(self, "שגיאה", "נא להזין מזהה Google Sheet או להדביק קישור מלא.")
            return

        self.set_loading(True)
        self.log(f"מנסה להוסיף שורת בדיקה לגיליון {sheet_name}...")

        self.worker = WorkerThread("write", self.client, sheet_id=sheet_id, sheet_name=sheet_name)
        self.worker.finished.connect(self.on_write_finished)
        self.worker.start()

    def on_write_finished(self, res: dict):
        self.set_loading(False)
        if res.get("success"):
            row = res.get("data", [])
            self.log(f"✅ שורה נכתבה בהצלחה: {row}")
            QMessageBox.information(
                self,
                "בדיקת כתיבה הצליחה",
                f"השורה נוספה בהצלחה לגיליון:\n{', '.join(row)}"
            )
        else:
            err = res.get("data", "")
            self.log(f"❌ שגיאה בכתיבה: {err}")
            QMessageBox.critical(self, "שגיאה בכתיבה", str(err))

    def on_btn_full_clicked(self):
        sheet_id = self.txt_sheet_id.text().strip()
        sheet_name = self.txt_sheet_name.text().strip() or "Sheet1"

        if not sheet_id:
            QMessageBox.warning(self, "שגיאה", "נא להזין מזהה Google Sheet או להדביק קישור מלא.")
            return

        if not self.client.credentials_file_exists():
            QMessageBox.warning(
                self,
                "חסר קובץ credentials.json",
                "יש לטעון קובץ credentials.json מ-Google Cloud לפני ביצוע הבדיקה."
            )
            return

        self.set_loading(True)
        self.reset_steps_ui()
        self.log("=== מתחיל בדיקה מלאה (5 שלבים) ===")

        self.worker = WorkerThread("full_test", self.client, sheet_id=sheet_id, sheet_name=sheet_name)
        self.worker.step_update.connect(self.on_full_test_step)
        self.worker.finished.connect(self.on_full_test_finished)
        self.worker.start()

    def reset_steps_ui(self):
        self.lbl_step1.setText("שלב 1 – התחברות: בביצוע...")
        self.lbl_step2.setText("שלב 2 – Google Sheets API: ממתין...")
        self.lbl_step3.setText("שלב 3 – קריאה: ממתין...")
        self.lbl_step4.setText("שלב 4 – כתיבה: ממתין...")
        self.lbl_step5.setText("שלב 5 – קריאה חוזרת: ממתין...")

        for lbl in [self.lbl_step1, self.lbl_step2, self.lbl_step3, self.lbl_step4, self.lbl_step5]:
            lbl.setStyleSheet("font-size: 13px; color: #3C4043;")

        self.lbl_banner_title.setText("מבצע בדיקה מלאה...")
        self.lbl_banner_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1A73E8;")
        self.lbl_banner_desc.setText("התהליך מתבצע ברקע, אנא המתן...")
        self.final_banner.setStyleSheet("""
            QFrame {
                background-color: #E8F0FE;
                border: 2px solid #1A73E8;
                border-radius: 8px;
                padding: 10px;
            }
        """)

    def on_full_test_step(self, step_num: int, message: str, is_success: bool):
        icon = "✅" if is_success else "❌"
        color = "#137333" if is_success else "#D93025"

        lbl_map = {
            1: self.lbl_step1,
            2: self.lbl_step2,
            3: self.lbl_step3,
            4: self.lbl_step4,
            5: self.lbl_step5
        }

        lbl = lbl_map.get(step_num)
        if lbl:
            lbl.setText(f"{message}")
            lbl.setStyleSheet(f"font-size: 13px; color: {color}; font-weight: bold;")

        self.log(f"{icon} {message}")

    def on_full_test_finished(self, res: dict):
        self.set_loading(False)
        self.update_auth_status_ui()
        report = res.get("report", {})
        overall_success = report.get("overall_success", False)

        title = report.get("summary_title", "")
        detail = report.get("summary_detail", "")

        self.lbl_banner_title.setText(title)
        self.lbl_banner_desc.setText(detail)

        if overall_success:
            self.final_banner.setStyleSheet("""
                QFrame {
                    background-color: #E6F4EA;
                    border: 2px solid #137333;
                    border-radius: 8px;
                    padding: 12px;
                }
            """)
            self.lbl_banner_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #137333;")
            self.lbl_banner_desc.setStyleSheet("font-size: 14px; color: #0D652D; font-weight: bold;")
            self.log("🎉 בדיקה מלאה הסתיימה בהצלחה מוחלטת!")
        else:
            self.final_banner.setStyleSheet("""
                QFrame {
                    background-color: #FCE8E6;
                    border: 2px solid #D93025;
                    border-radius: 8px;
                    padding: 12px;
                }
            """)
            self.lbl_banner_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #D93025;")
            self.lbl_banner_desc.setStyleSheet("font-size: 14px; color: #C5221F;")
            self.log(f"⚠️ בדיקה מלאה נכשלה: {detail}")

    # ------------------ סעיפים 11-13: בדיקת 2 מחשבים ו-Polling ------------------

    def on_btn_send_move_clicked(self):
        sheet_id = self.txt_sheet_id.text().strip()
        sheet_name = self.txt_sheet_name.text().strip() or "Sheet1"
        player = self.txt_player_name.text().strip()
        msg = self.txt_move_content.text().strip()

        if not sheet_id or not msg:
            QMessageBox.warning(self, "חסר נתון", "נא להזין מזהה גיליון ותוכן מהלך.")
            return

        self.btn_send_move.setEnabled(False)
        self.worker = WorkerThread("send_move", self.client, sheet_id=sheet_id, sheet_name=sheet_name, player=player, message=msg)
        self.worker.finished.connect(self.on_move_sent)
        self.worker.start()

    def on_move_sent(self, res: dict):
        self.btn_send_move.setEnabled(True)
        if res.get("success"):
            self.log(f"מהלך נשלח: {self.txt_move_content.text()}")
            # רענון טבלה מיידי
            self.on_polling_tick()
        else:
            QMessageBox.critical(self, "שגיאה בשליחה", res.get("message", "שגיאה"))

    def toggle_polling(self):
        if self.polling_timer.isActive():
            self.polling_timer.stop()
            self.btn_toggle_poll.setText("הפעל האזנה אוטומטית (Polling)")
            self.lbl_poll_status.setText("האזנה כבויה")
            self.lbl_poll_status.setStyleSheet("color: #5F6368; font-weight: bold;")
            self.log("האזנה אוטומטית הופסקה.")
        else:
            sheet_id = self.txt_sheet_id.text().strip()
            if not sheet_id:
                QMessageBox.warning(self, "שגיאה", "נא להזין מזהה גיליון תחילה.")
                return
            # דגימה כל 3 שניות
            self.polling_timer.start(3000)
            self.btn_toggle_poll.setText("עצור האזנה אוטומטית")
            self.lbl_poll_status.setText("האזנה פעילה (כל 3 שניות)...")
            self.lbl_poll_status.setStyleSheet("color: #137333; font-weight: bold;")
            self.log("האזנה אוטומטית (Polling) הופעלה (כל 3 שניות).")
            self.on_polling_tick()

    def on_polling_tick(self):
        sheet_id = self.txt_sheet_id.text().strip()
        sheet_name = self.txt_sheet_name.text().strip() or "Sheet1"
        if not sheet_id or not self.client.is_logged_in():
            return

        # הרצת קריאה ברקע אם לא רץ כרגע עובד אחר
        if self.worker and self.worker.isRunning():
            return

        self.worker = WorkerThread("poll", self.client, sheet_id=sheet_id, sheet_name=sheet_name)
        self.worker.finished.connect(self.on_polling_data_received)
        self.worker.start()

    def on_polling_data_received(self, res: dict):
        if not res.get("success"):
            return

        rows = res.get("rows", [])
        self.table_moves.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            for c_idx in range(4):
                val = row[c_idx] if c_idx < len(row) else ""
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                self.table_moves.setItem(r_idx, c_idx, item)

        # גלילה אוטומטית לשורה האחרונה אם נוספו שורות
        if len(rows) > self.last_poll_rows_count:
            self.table_moves.scrollToBottom()
            if self.last_poll_rows_count > 0:
                new_row = rows[-1]
                self.log(f"🔔 זוהה מהלך חדש בגיליון: {new_row}")
            self.last_poll_rows_count = len(rows)


def run_gui():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    # כיוון ימין-לשמאל עברי
    app.setLayoutDirection(Qt.RightToLeft)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    run_gui()
