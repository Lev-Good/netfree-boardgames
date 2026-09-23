# -*- coding: utf-8 -*-
"""
חלון משחק השחמט המלא - כולל סנכרון מקוון מתקדם ב-Google Sheets API (נטפרי),
ריבוי משחקים (חדרים נפרדים), לובי משחקים, צ'אט חי, שעוני שחמט דיגיטליים,
החזרת מהלך (Takeback), אפקטים קוליים, מצב צופה ויצירת גיליון בלחיצת כפתור.
"""

import sys
import os
import random
import datetime
from typing import Optional, Dict, Any, List, Tuple

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QComboBox, QFileDialog, QMessageBox,
    QFrame, QSplitter, QTabWidget, QTextEdit, QCheckBox, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor

import chess

from chess_engine import ChessEngine, MoveRecord, format_clock_time
from chess_board_widget import ChessBoardWidget
from chess_sync import ChessSyncManager, encode_invite_code, decode_invite_code
from google_sheets_client import GoogleSheetsClient, extract_spreadsheet_id, load_config, save_config
from theme_style import get_gaming_stylesheet
import sound_effects


class ChessNetworkWorker(QThread):
    """תהליך רקע לשליחה ומשיכת נתונים מ-Google Sheets API ללא תקיעת ממשק המשתמש"""
    finished_task = Signal(str, bool, object, str)  # (task_type, success, data, error_msg)

    def __init__(self, sync_mgr: ChessSyncManager, task_type: str, **kwargs):
        super().__init__()
        self.sync_mgr = sync_mgr
        self.task_type = task_type
        self.kwargs = kwargs

    def run(self):
        try:
            if self.task_type == "send_move":
                success, msg = self.sync_mgr.send_move(
                    spreadsheet_id=self.kwargs["sheet_id"],
                    room_id=self.kwargs["room_id"],
                    move_num=self.kwargs["move_num"],
                    player_name=self.kwargs["player_name"],
                    color=self.kwargs["color"],
                    move_uci=self.kwargs["move_uci"],
                    move_san=self.kwargs["move_san"],
                    fen=self.kwargs["fen"],
                    action=self.kwargs.get("action", "MOVE")
                )
                self.finished_task.emit("send_move", success, msg, "" if success else msg)

            elif self.task_type == "poll_bundle":
                success, data, err = self.sync_mgr.batch_poll_room(
                    spreadsheet_id=self.kwargs["sheet_id"],
                    room_id=self.kwargs["room_id"],
                    after_move_num=self.kwargs.get("after_move_num", 0),
                    after_msg_id=self.kwargs.get("after_msg_id", 0)
                )
                self.finished_task.emit("poll_bundle", success, data, err)

            elif self.task_type == "send_action":
                success, msg = self.sync_mgr.send_special_action(
                    spreadsheet_id=self.kwargs["sheet_id"],
                    room_id=self.kwargs["room_id"],
                    player_name=self.kwargs["player_name"],
                    color=self.kwargs["color"],
                    action=self.kwargs["action"]
                )
                self.finished_task.emit("send_action", success, msg, "" if success else msg)

            elif self.task_type == "send_chat":
                success, msg = self.sync_mgr.send_chat_message(
                    spreadsheet_id=self.kwargs["sheet_id"],
                    room_id=self.kwargs["room_id"],
                    msg_id=self.kwargs["msg_id"],
                    sender=self.kwargs["sender"],
                    color=self.kwargs["color"],
                    message=self.kwargs["message"]
                )
                self.finished_task.emit("send_chat", success, msg, "" if success else msg)

            elif self.task_type == "create_room":
                success, msg = self.sync_mgr.create_room(
                    spreadsheet_id=self.kwargs["sheet_id"],
                    room_id=self.kwargs["room_id"],
                    host_name=self.kwargs["host_name"],
                    host_color=self.kwargs.get("host_color", "W"),
                    time_control=self.kwargs.get("time_control", "NONE")
                )
                if success and self.kwargs.get("publish_lobby", False):
                    self.sync_mgr.publish_room_to_lobby(
                        spreadsheet_id=self.kwargs["sheet_id"],
                        room_id=self.kwargs["room_id"],
                        host_name=self.kwargs["host_name"],
                        time_control=self.kwargs.get("time_control", "NONE"),
                        host_color=self.kwargs.get("host_color", "W")
                    )
                self.finished_task.emit("create_room", success, msg, "" if success else msg)

            elif self.task_type == "join_room":
                success, room_info, err = self.sync_mgr.join_room(
                    spreadsheet_id=self.kwargs["sheet_id"],
                    room_id=self.kwargs["room_id"],
                    guest_name=self.kwargs["guest_name"]
                )
                self.finished_task.emit("join_room", success, room_info, err)

            elif self.task_type == "fetch_lobby":
                success, games, err = self.sync_mgr.fetch_lobby_games(
                    spreadsheet_id=self.kwargs["sheet_id"]
                )
                self.finished_task.emit("fetch_lobby", success, games, err)

            elif self.task_type == "create_sheet":
                success, sheet_id, sheet_url = self.sync_mgr.client.create_new_spreadsheet(
                    title=self.kwargs.get("title", "פלטפורמת שחמט מקוון בנטפרי")
                )
                self.finished_task.emit("create_sheet", success, {"id": sheet_id, "url": sheet_url}, "" if success else sheet_id)

        except Exception as e:
            self.finished_task.emit(self.task_type, False, None, str(e))


class ChessMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = ChessEngine()
        self.sheets_client = GoogleSheetsClient()
        self.sync_mgr = ChessSyncManager(self.sheets_client)

        # טעינת הגדרות שמורות
        cfg = load_config()
        self.saved_mode = cfg.get("mode_index", 0)
        self.is_online = (self.saved_mode in (0, 1, 2))
        self.is_spectator = (self.saved_mode == 2)
        if self.saved_mode == 0:
            self.local_color: Optional[chess.Color] = chess.WHITE
        elif self.saved_mode == 1:
            self.local_color: Optional[chess.Color] = chess.BLACK
        else:
            self.local_color = None

        self.game_id = cfg.get("game_id") or f"Room_{random.randint(1000, 9999)}"
        # יצירת מזהה שחקן ייחודי כדי למנוע התנגשות אם שני מחשבים נקראים "משתמש"
        saved_nick = cfg.get("player_nickname")
        if saved_nick:
            self.player_name = saved_nick
        else:
            self.player_name = f"{self.sheets_client.computer_name}#{random.randint(100, 999)}"
            save_config({"player_nickname": self.player_name})

        self.opponent_name = "יריב"
        self.last_chat_msg_id = 0

        # שעוני שחמט דיגיטליים
        self.time_control_name = "NONE"
        self.white_time_seconds: Optional[int] = None
        self.black_time_seconds: Optional[int] = None
        self.increment_seconds = 0
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.on_clock_tick)

        # ניקוד סשן
        self.score_white = 0
        self.score_black = 0
        self.score_draws = 0

        # דגימה (Polling) מקוונת מאוחדת
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_room_bundle)
        self.is_polling_active = False

        # ניהול מרובה תהליכים בטוח ללא קריסות (Thread-Safe Worker Pool)
        self.active_workers: List[ChessNetworkWorker] = []
        self.is_polling_busy = False

        # מצב צפייה בהיסטוריה
        self.is_reviewing = False

        self.init_ui()
        self.update_game_status_display()
        self.update_score_and_captures()
        self.update_clock_labels()

    def init_ui(self):
        self.setWindowTitle("שחמט מקוון בנטפרי – פלטפורמת שחמט חכמה דרך Google Sheets API")
        self.resize(1180, 800)
        self.setMinimumSize(1020, 700)

        # ערכת נושא גיימינג מודרנית (Gaming Dark HUD)
        self.setStyleSheet(get_gaming_stylesheet())

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # ------------------ צד ימין: לוח השחמט וכרטיסי שחקנים ושעונים ------------------
        board_panel = QVBoxLayout()
        board_panel.setSpacing(8)

        # כרטיס שחקן עליון + שעון
        self.card_top_player = self.create_player_card("יריב (שחור)", is_top=True)
        board_panel.addWidget(self.card_top_player)

        # רכיב הלוח
        self.board_widget = ChessBoardWidget(self.engine.board)
        self.board_widget.move_attempted.connect(self.on_player_move_attempted)
        board_panel.addWidget(self.board_widget, stretch=1)

        # כרטיס שחקן תחתון + שעון
        self.card_bottom_player = self.create_player_card(f"{self.player_name} (לבן)", is_top=False)
        board_panel.addWidget(self.card_bottom_player)

        main_layout.addLayout(board_panel, stretch=6)

        # ------------------ צד שמאל: לשוניות ניהול, צ'אט, חדר ולובי ------------------
        self.tabs = QTabWidget()

        # לשונית 1: משחק וצ'אט
        tab_game = QWidget()
        self.init_game_tab(tab_game)
        self.tabs.addTab(tab_game, "🎮 משחק וצ'אט")

        # לשונית 2: חדר והתחברות
        tab_room = QWidget()
        self.init_room_tab(tab_room)
        self.tabs.addTab(tab_room, "🌐 חדר והזמנה")

        # לשונית 3: לובי משחקים
        tab_lobby = QWidget()
        self.init_lobby_tab(tab_lobby)
        self.tabs.addTab(tab_lobby, "👥 לובי משחקים")

        main_layout.addWidget(self.tabs, stretch=5)

    def create_player_card(self, title: str, is_top: bool) -> QFrame:
        """כרטיס שחקן עם שם, כלים שנאכלו, הפרש חומר ושעון דיגיטלי בעיצוב Gaming HUD"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #161F2E;
                border: 1.5px solid #2B374E;
                border-radius: 8px;
                padding: 4px 10px;
            }
        """)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)

        lbl_name = QLabel(title)
        lbl_name.setStyleSheet("font-weight: bold; font-size: 14px; color: #F8FAFC;")

        lbl_captures = QLabel("")
        lbl_captures.setStyleSheet("font-size: 17px; color: #E2E8F0;")

        lbl_diff = QLabel("")
        lbl_diff.setStyleSheet("font-size: 13px; font-weight: bold; color: #10B981;")

        lbl_clock = QLabel("⏱️ --:--")
        lbl_clock.setStyleSheet("""
            QLabel {
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 17px;
                font-weight: bold;
                color: #38BDF8;
                background-color: #0B0E14;
                border: 1.5px solid #1E293B;
                border-radius: 6px;
                padding: 4px 10px;
            }
        """)

        layout.addWidget(lbl_name)
        layout.addSpacing(10)
        layout.addWidget(lbl_captures)
        layout.addWidget(lbl_diff)
        layout.addStretch()
        layout.addWidget(lbl_clock)

        if is_top:
            self.lbl_top_name = lbl_name
            self.lbl_top_captures = lbl_captures
            self.lbl_top_diff = lbl_diff
            self.lbl_top_clock = lbl_clock
            self.card_top = card
        else:
            self.lbl_bottom_name = lbl_name
            self.lbl_bottom_captures = lbl_captures
            self.lbl_bottom_diff = lbl_diff
            self.lbl_bottom_clock = lbl_clock
            self.card_bottom = card

        return card

    # ------------------ לשונית 1: משחק וצ'אט ------------------

    def init_game_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # באנר סטטוס תור בעיצוב Gaming HUD
        self.banner_status = QFrame()
        self.banner_status.setStyleSheet("QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1E1B4B, stop:1 #1E293B); border: 1.5px solid #4338CA; border-radius: 8px; padding: 6px; }")
        banner_layout = QVBoxLayout(self.banner_status)
        banner_layout.setContentsMargins(8, 5, 8, 5)
        self.lbl_turn_status = QLabel("תור הלבן")
        self.lbl_turn_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #818CF8;")
        self.lbl_turn_status.setAlignment(Qt.AlignCenter)
        self.lbl_extra_status = QLabel("המשחק החל. מהלך 1")
        self.lbl_extra_status.setStyleSheet("font-size: 12px; color: #94A3B8;")
        self.lbl_extra_status.setAlignment(Qt.AlignCenter)
        banner_layout.addWidget(self.lbl_turn_status)
        banner_layout.addWidget(self.lbl_extra_status)
        layout.addWidget(self.banner_status)

        # סרגל פעולות מהירות (כניעה, תיקו, החזרת מהלך, משחק חדש)
        actions_bar = QHBoxLayout()
        self.btn_resign = QPushButton("🏳️ היכנע")
        self.btn_resign.setObjectName("btnDanger")
        self.btn_resign.clicked.connect(self.on_resign_clicked)

        self.btn_draw = QPushButton("🤝 הצע תיקו")
        self.btn_draw.setObjectName("btnSecondary")
        self.btn_draw.clicked.connect(self.on_draw_clicked)

        self.btn_takeback = QPushButton("↩️ בקש החזרה")
        self.btn_takeback.setObjectName("btnSecondary")
        self.btn_takeback.clicked.connect(self.on_takeback_clicked)

        self.btn_new_game = QPushButton("🔄 משחק חדש")
        self.btn_new_game.clicked.connect(self.on_new_game_clicked)

        actions_bar.addWidget(self.btn_resign)
        actions_bar.addWidget(self.btn_draw)
        actions_bar.addWidget(self.btn_takeback)
        actions_bar.addWidget(self.btn_new_game)
        layout.addLayout(actions_bar)

        # טבלת היסטוריית מהלכים
        hist_box = QGroupBox("היסטוריית מהלכים")
        hist_layout = QVBoxLayout(hist_box)
        hist_layout.setContentsMargins(6, 6, 6, 6)

        self.table_history = QTableWidget()
        self.table_history.setColumnCount(3)
        self.table_history.setHorizontalHeaderLabels(["תור", "לבן", "שחור"])
        self.table_history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_history.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_history.setMaximumHeight(140)
        self.table_history.cellClicked.connect(self.on_history_cell_clicked)
        hist_layout.addWidget(self.table_history)

        # כפתורי דפדוף וייצוא
        nav_layout = QHBoxLayout()
        btn_first = QPushButton("<<")
        btn_first.setObjectName("btnSecondary")
        btn_first.setFixedWidth(36)
        btn_first.clicked.connect(self.nav_first_move)
        btn_prev = QPushButton("<")
        btn_prev.setObjectName("btnSecondary")
        btn_prev.setFixedWidth(36)
        btn_prev.clicked.connect(self.nav_prev_move)
        btn_next = QPushButton(">")
        btn_next.setObjectName("btnSecondary")
        btn_next.setFixedWidth(36)
        btn_next.clicked.connect(self.nav_next_move)
        btn_last = QPushButton(">>")
        btn_last.setObjectName("btnSecondary")
        btn_last.setFixedWidth(36)
        btn_last.clicked.connect(self.nav_last_move)
        nav_layout.addWidget(btn_first)
        nav_layout.addWidget(btn_prev)
        nav_layout.addWidget(btn_next)
        nav_layout.addWidget(btn_last)
        nav_layout.addStretch()
        btn_export = QPushButton("ייצא PGN")
        btn_export.setObjectName("btnSecondary")
        btn_export.clicked.connect(self.export_pgn_file)
        nav_layout.addWidget(btn_export)
        hist_layout.addLayout(nav_layout)
        layout.addWidget(hist_box)

        # צ'אט חי בתוך המשחק
        chat_box = QGroupBox("💬 צ'אט חי בתוך החדר")
        chat_layout = QVBoxLayout(chat_box)
        chat_layout.setContentsMargins(6, 6, 6, 6)

        # שורת כותרת הצ'אט וסאונד
        chat_header = QHBoxLayout()
        self.btn_sound_toggle = QPushButton("🔊 צלילים: פעיל")
        self.btn_sound_toggle.setObjectName("btnSecondary")
        self.btn_sound_toggle.clicked.connect(self.toggle_sound)
        chat_header.addStretch()
        chat_header.addWidget(self.btn_sound_toggle)
        chat_layout.addLayout(chat_header)

        # היסטוריית הודעות
        self.txt_chat_history = QTextEdit()
        self.txt_chat_history.setReadOnly(True)
        self.txt_chat_history.setStyleSheet("""
            QTextEdit {
                background-color: #FAFAFA;
                border: 1px solid #DADCE0;
                border-radius: 6px;
                font-size: 13px;
            }
        """)
        chat_layout.addWidget(self.txt_chat_history, stretch=1)

        # כפתורי תגובה מהירה
        quick_layout = QHBoxLayout()
        quick_phrases = ["בהצלחה! 🤝", "מהלך יפה! 👏", "אופס... 😅", "תודה על המשחק! 🏆"]
        for phrase in quick_phrases:
            btn_q = QPushButton(phrase)
            btn_q.setObjectName("btnSecondary")
            btn_q.setStyleSheet("font-size: 11px; padding: 4px 6px;")
            btn_q.clicked.connect(lambda _, p=phrase: self.send_chat_message(p))
            quick_layout.addWidget(btn_q)
        chat_layout.addLayout(quick_layout)

        # שורת הזנת הודעה
        input_layout = QHBoxLayout()
        self.txt_chat_input = QLineEdit()
        self.txt_chat_input.setPlaceholderText("הקלד הודעה בצ'אט ולחץ Enter...")
        self.txt_chat_input.returnPressed.connect(self.on_chat_enter_pressed)
        btn_send_chat = QPushButton("שלח")
        btn_send_chat.clicked.connect(self.on_chat_enter_pressed)
        input_layout.addWidget(self.txt_chat_input)
        input_layout.addWidget(btn_send_chat)
        chat_layout.addLayout(input_layout)

        layout.addWidget(chat_box, stretch=1)

        # שורת ניקוד סשן
        self.lbl_session_score = QLabel("ניקוד סשן: לבן 0 | שחור 0 | תיקו 0")
        self.lbl_session_score.setStyleSheet("font-size: 12px; font-weight: bold; color: #5F6368;")
        self.lbl_session_score.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_session_score)

    # ------------------ לשונית 2: חדר והתחברות ------------------

    def init_room_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # 1. ניהול גיליון Google Sheets
        sheet_box = QGroupBox("1. חיבור גיליון Google Sheets (נטפרי)")
        sheet_layout = QVBoxLayout(sheet_box)

        btn_create_sheet = QPushButton("📄 צור גיליון שחמט חדש בחשבון Google שלך")
        btn_create_sheet.setObjectName("btnSuccess")
        btn_create_sheet.clicked.connect(self.on_create_new_sheet_clicked)
        sheet_layout.addWidget(btn_create_sheet)

        row_sheet_id = QHBoxLayout()
        lbl_s = QLabel("מזהה/קישור גיליון:")
        lbl_s.setFixedWidth(120)
        saved_sheet_id = load_config().get("spreadsheet_id", "")
        self.txt_sheet_id = QLineEdit(saved_sheet_id)
        self.txt_sheet_id.setPlaceholderText("הדבק כאן מזהה Google Sheet או קישור מלא")
        self.txt_sheet_id.textChanged.connect(lambda t: save_config({"spreadsheet_id": t.strip()}))
        row_sheet_id.addWidget(lbl_s)
        row_sheet_id.addWidget(self.txt_sheet_id)
        sheet_layout.addLayout(row_sheet_id)

        layout.addWidget(sheet_box)

        # 2. אירוח משחק חדש (Host)
        host_box = QGroupBox("2. אירוח משחק חדש (מארח)")
        host_layout = QVBoxLayout(host_box)

        row_time = QHBoxLayout()
        lbl_tc = QLabel("בקרת זמן (שעון):")
        lbl_tc.setFixedWidth(120)
        self.combo_time_control = QComboBox()
        self.combo_time_control.addItems(["ללא הגבלת זמן", "5 דקות", "10 דקות", "15 דקות + 5 שניות"])
        row_time.addWidget(lbl_tc)
        row_time.addWidget(self.combo_time_control)
        host_layout.addLayout(row_time)

        row_room = QHBoxLayout()
        lbl_r = QLabel("מזהה חדר:")
        lbl_r.setFixedWidth(120)
        self.txt_game_id = QLineEdit(self.game_id)
        self.txt_game_id.textChanged.connect(lambda t: save_config({"game_id": t.strip().upper()}))
        btn_gen_code = QPushButton("חדר חדש")
        btn_gen_code.setObjectName("btnSecondary")
        btn_gen_code.clicked.connect(self.generate_new_room_code)
        row_room.addWidget(lbl_r)
        row_room.addWidget(self.txt_game_id)
        row_room.addWidget(btn_gen_code)
        host_layout.addLayout(row_room)

        self.chk_publish_lobby = QCheckBox("פרסם משחק זה בלובי המרכזי (כדי ששחקנים אחרים יוכלו למצוא אותו)")
        self.chk_publish_lobby.setChecked(True)
        host_layout.addWidget(self.chk_publish_lobby)

        btn_host_start = QPushButton("🚀 פתח חדר והתחל משחק כמארח")
        btn_host_start.clicked.connect(self.on_host_create_room_clicked)
        host_layout.addWidget(btn_host_start)

        # קוד הזמנה חכם
        row_invite = QHBoxLayout()
        lbl_inv = QLabel("קוד הזמנה חכם:")
        lbl_inv.setFixedWidth(120)
        self.lbl_invite_code = QLineEdit()
        self.lbl_invite_code.setReadOnly(True)
        self.lbl_invite_code.setPlaceholderText("יופק אוטומטית לאחר פתיחת החדר")
        btn_copy_invite = QPushButton("📋 העתק")
        btn_copy_invite.setObjectName("btnSecondary")
        btn_copy_invite.clicked.connect(self.copy_invite_code)
        row_invite.addWidget(lbl_inv)
        row_invite.addWidget(self.lbl_invite_code)
        row_invite.addWidget(btn_copy_invite)
        host_layout.addLayout(row_invite)

        layout.addWidget(host_box)

        # 3. הצטרפות למשחק קיים (Guest / Spectator)
        join_box = QGroupBox("3. הצטרפות למשחק (אורח או צופה)")
        join_layout = QVBoxLayout(join_box)

        row_paste_code = QHBoxLayout()
        self.txt_join_code = QLineEdit()
        self.txt_join_code.setPlaceholderText("הדבק קוד הזמנה חכם (NETFREE#...) או מזהה חדר")
        btn_join_by_code = QPushButton("⚡ הצטרף לפי קוד")
        btn_join_by_code.setObjectName("btnSuccess")
        btn_join_by_code.clicked.connect(self.on_join_by_code_clicked)
        row_paste_code.addWidget(self.txt_join_code)
        row_paste_code.addWidget(btn_join_by_code)
        join_layout.addLayout(row_paste_code)

        row_role = QHBoxLayout()
        lbl_role = QLabel("תפקיד בהתחברות:")
        lbl_role.setFixedWidth(120)
        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "משחק מקוון – שחקן לבן (יוזם)",
            "משחק מקוון – שחקן שחור (מצטרף)",
            "מצב צופה (Spectator – צפייה וצ'אט)",
            "משחק מקומי (שני שחקנים על אותו מחשב)"
        ])
        self.combo_mode.setCurrentIndex(self.saved_mode)
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        row_role.addWidget(lbl_role)
        row_role.addWidget(self.combo_mode)
        join_layout.addLayout(row_role)

        row_direct_join = QHBoxLayout()
        self.btn_join_room = QPushButton("התחבר ישירות לפי ההגדרות שלעיל")
        self.btn_join_room.clicked.connect(self.on_manual_connect_clicked)
        self.lbl_room_status = QLabel("מנותק")
        self.lbl_room_status.setStyleSheet("color: #5F6368; font-weight: bold;")
        row_direct_join.addWidget(self.btn_join_room)
        row_direct_join.addWidget(self.lbl_room_status)
        row_direct_join.addStretch()
        join_layout.addLayout(row_direct_join)

        layout.addWidget(join_box)

        # כלי בדיקה
        row_diag = QHBoxLayout()
        row_diag.addStretch()
        btn_diag = QPushButton("🛠️ כלי בדיקת תקשורת ו-API")
        btn_diag.setObjectName("btnSecondary")
        btn_diag.clicked.connect(self.open_diagnostics)
        row_diag.addWidget(btn_diag)
        layout.addLayout(row_diag)

        layout.addStretch()

    # ------------------ לשונית 3: לובי משחקים ------------------

    def init_lobby_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        lbl_desc = QLabel("רשימת חדרים שממתינים לשחקנים בגיליון המשותף:")
        lbl_desc.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_desc)

        self.table_lobby = QTableWidget()
        self.table_lobby.setColumnCount(5)
        self.table_lobby.setHorizontalHeaderLabels(["חדר", "מארח", "בקרת זמן", "צבע מארח", "שעה"])
        self.table_lobby.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_lobby.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_lobby.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table_lobby, stretch=1)

        lobby_buttons = QHBoxLayout()
        btn_refresh = QPushButton("🔄 רענן רשימת לובי")
        btn_refresh.clicked.connect(self.on_refresh_lobby_clicked)
        btn_join_selected = QPushButton("🎯 הצטרף למשחק הנבחר")
        btn_join_selected.setObjectName("btnSuccess")
        btn_join_selected.clicked.connect(self.on_join_selected_lobby_game)

        lobby_buttons.addWidget(btn_refresh)
        lobby_buttons.addWidget(btn_join_selected)
        layout.addLayout(lobby_buttons)

    # ------------------ שעוני שחמט דיגיטליים ------------------

    def setup_time_control(self, tc_text: str):
        """הגדרת שעוני שחמט לפי סוג בקרת הזמן"""
        self.time_control_name = tc_text.upper()
        if "5" in tc_text and "15" not in tc_text:
            self.white_time_seconds = 300
            self.black_time_seconds = 300
            self.increment_seconds = 0
        elif "10" in tc_text:
            self.white_time_seconds = 600
            self.black_time_seconds = 600
            self.increment_seconds = 0
        elif "15" in tc_text:
            self.white_time_seconds = 900
            self.black_time_seconds = 900
            self.increment_seconds = 5
        else:
            self.white_time_seconds = None
            self.black_time_seconds = None
            self.increment_seconds = 0

        self.update_clock_labels()
        if self.white_time_seconds is not None:
            self.clock_timer.start(1000)
        else:
            self.clock_timer.stop()

    def on_clock_tick(self):
        """תקתוק שעון כל שניה עבור השחקן שזהו תורו (רק אם המשחק החל בפועל)"""
        if self.engine.is_game_over() or self.white_time_seconds is None or len(self.engine.history) == 0:
            return

        if self.engine.is_white_turn():
            self.white_time_seconds = max(0, self.white_time_seconds - 1)
            if self.white_time_seconds == 0:
                self.clock_timer.stop()
                self.on_time_out(chess.WHITE)
        else:
            self.black_time_seconds = max(0, self.black_time_seconds - 1)
            if self.black_time_seconds == 0:
                self.clock_timer.stop()
                self.on_time_out(chess.BLACK)

        self.update_clock_labels()

    def update_clock_labels(self):
        """עדכון תצוגת השעונים בכרטיסים"""
        w_str = format_clock_time(self.white_time_seconds)
        b_str = format_clock_time(self.black_time_seconds)

        # צבעי השעון (אדום אם פחות מ-30 שניות)
        w_style = "color: #D93025; font-weight: bold;" if (self.white_time_seconds is not None and self.white_time_seconds < 30) else "color: #202124;"
        b_style = "color: #D93025; font-weight: bold;" if (self.black_time_seconds is not None and self.black_time_seconds < 30) else "color: #202124;"

        if self.board_widget.is_flipped:
            # שחור למטה, לבן למעלה
            self.lbl_bottom_clock.setText(f"⏱️ {b_str}")
            self.lbl_bottom_clock.setStyleSheet(f"font-family: monospace; font-size: 16px; {b_style} background: #F1F3F4; border-radius: 4px; padding: 3px 6px;")
            self.lbl_top_clock.setText(f"⏱️ {w_str}")
            self.lbl_top_clock.setStyleSheet(f"font-family: monospace; font-size: 16px; {w_style} background: #F1F3F4; border-radius: 4px; padding: 3px 6px;")
        else:
            # לבן למטה, שחור למעלה
            self.lbl_bottom_clock.setText(f"⏱️ {w_str}")
            self.lbl_bottom_clock.setStyleSheet(f"font-family: monospace; font-size: 16px; {w_style} background: #F1F3F4; border-radius: 4px; padding: 3px 6px;")
            self.lbl_top_clock.setText(f"⏱️ {b_str}")
            self.lbl_top_clock.setStyleSheet(f"font-family: monospace; font-size: 16px; {b_style} background: #F1F3F4; border-radius: 4px; padding: 3px 6px;")

    def on_time_out(self, timed_out_color: chess.Color):
        """שחקן הפסיד בזמן"""
        sound_effects.play_game_end_sound(False)
        loser = "הלבן" if timed_out_color == chess.WHITE else "השחור"
        winner = "השחור" if timed_out_color == chess.WHITE else "הלבן"
        QMessageBox.critical(self, "נגמר הזמן!", f"נגמר הזמן לשחקן {loser}!\nהניצחון לשחקן {winner}!")
        self.record_game_end(winner="local" if timed_out_color != self.local_color else "opponent")

    # ------------------ סאונד ------------------

    def toggle_sound(self):
        curr = sound_effects.is_sound_enabled()
        sound_effects.set_sound_enabled(not curr)
        if not curr:
            self.btn_sound_toggle.setText("🔊 צלילים: פעיל")
        else:
            self.btn_sound_toggle.setText("🔇 צלילים: מושתק")

    # ------------------ ניהול תור ומצב משחק ------------------

    def update_game_status_display(self):
        """עדכון חיוויי המצב, הכרטיסים והתור"""
        if self.is_reviewing:
            return

        status_text, is_over = self.engine.get_game_status_hebrew()
        is_white = self.engine.is_white_turn()
        move_num = (len(self.engine.history) // 2) + 1

        self.lbl_extra_status.setText(f"מהלך {move_num} • {len(self.engine.history)} מסעים בוצעו")

        if is_over:
            self.banner_status.setStyleSheet("QFrame { background-color: #FCE8E6; border: 2px solid #D93025; border-radius: 8px; padding: 8px; }")
            self.lbl_turn_status.setText(status_text)
            self.lbl_turn_status.setStyleSheet("font-size: 17px; font-weight: bold; color: #D93025;")
            self.board_widget.interactive = False
            self.stop_polling()
            self.clock_timer.stop()
            return

        if self.is_spectator:
            self.board_widget.interactive = False
            turn_name = "הלבן" if is_white else "השחור"
            self.lbl_turn_status.setText(f"מצב צופה (Spectator) – תור {turn_name}")
            self.lbl_turn_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #5F6368;")
            self.banner_status.setStyleSheet("QFrame { background-color: #F1F3F4; border: 2px solid #DADCE0; border-radius: 8px; padding: 8px; }")
            self.start_polling()
            return

        if not self.is_online or self.local_color is None:
            # משחק מקומי
            self.board_widget.interactive = True
            turn_str = "תור הלבן" if is_white else "תור השחור"
            self.lbl_turn_status.setText(turn_str)
            self.lbl_turn_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #1A73E8;")
            self.banner_status.setStyleSheet("QFrame { background-color: #E8F0FE; border: 2px solid #1A73E8; border-radius: 8px; padding: 8px; }")
        else:
            is_my_turn = (self.engine.get_turn() == self.local_color)
            self.board_widget.interactive = is_my_turn

            if is_my_turn:
                self.lbl_turn_status.setText("תורך לשחק!")
                self.lbl_turn_status.setStyleSheet("font-size: 17px; font-weight: bold; color: #137333;")
                self.banner_status.setStyleSheet("QFrame { background-color: #E6F4EA; border: 2px solid #137333; border-radius: 8px; padding: 8px; }")
                # דגימת צ'אט ובקשות תיקו/החזרה בקצב רגוע
                self.start_polling(interval_ms=3000)
            else:
                self.lbl_turn_status.setText("ממתין למהלך היריב...")
                self.lbl_turn_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #E37400;")
                self.banner_status.setStyleSheet("QFrame { background-color: #FEF7E0; border: 2px solid #FBBC04; border-radius: 8px; padding: 8px; }")
                self.start_polling(interval_ms=1800)

    def update_score_and_captures(self):
        """עדכון ניקוד הכלים שנאכלו וההפרש בחומר"""
        info = self.engine.calculate_material_and_captures()
        diff = info["diff"]

        if self.board_widget.is_flipped:
            self.lbl_bottom_name.setText(f"{self.player_name} (שחור)")
            self.lbl_top_name.setText(f"{self.opponent_name} (לבן)")
            self.lbl_bottom_captures.setText(info["captured_by_black"])
            self.lbl_top_captures.setText(info["captured_by_white"])
            self.lbl_bottom_diff.setText(f"+{-diff}" if diff < 0 else "")
            self.lbl_top_diff.setText(f"+{diff}" if diff > 0 else "")
        else:
            self.lbl_bottom_name.setText(f"{self.player_name} (לבן)")
            self.lbl_top_name.setText(f"{self.opponent_name} (שחור)")
            self.lbl_bottom_captures.setText(info["captured_by_white"])
            self.lbl_top_captures.setText(info["captured_by_black"])
            self.lbl_bottom_diff.setText(f"+{diff}" if diff > 0 else "")
            self.lbl_top_diff.setText(f"+{-diff}" if diff < 0 else "")

    def update_history_table(self):
        pairs = self.engine.get_paired_history()
        self.table_history.setRowCount(len(pairs))
        for row_idx, p in enumerate(pairs):
            it_turn = QTableWidgetItem(f"{p['turn']}.")
            it_turn.setTextAlignment(Qt.AlignCenter)
            it_white = QTableWidgetItem(p["white"])
            it_white.setTextAlignment(Qt.AlignCenter)
            it_black = QTableWidgetItem(p["black"])
            it_black.setTextAlignment(Qt.AlignCenter)
            self.table_history.setItem(row_idx, 0, it_turn)
            self.table_history.setItem(row_idx, 1, it_white)
            self.table_history.setItem(row_idx, 2, it_black)
        self.table_history.scrollToBottom()

    # ------------------ אירועי מהלכים ------------------

    def on_player_move_attempted(self, uci: str):
        """ביצוע מהלך של השחקן המקומי"""
        color_str = "W" if self.engine.is_white_turn() else "B"

        # אם היה במצב סקירה בהיסטוריה - החזרה מיידית למצב חי
        if self.is_reviewing:
            self.nav_last_move()

        # בדיקה האם זו אכילה לפני ביצוע המהלך
        try:
            mv = chess.Move.from_uci(uci)
            is_capture = self.engine.board.is_capture(mv)
        except Exception:
            is_capture = False

        success, san, err = self.engine.push_move(uci, self.player_name)
        if not success:
            QMessageBox.warning(self, "מהלך לא חוקי", err)
            return

        # הוספת תוספת זמן לשעון (אם מוגדרת)
        if self.increment_seconds > 0:
            if color_str == "W" and self.white_time_seconds is not None:
                self.white_time_seconds += self.increment_seconds
            elif color_str == "B" and self.black_time_seconds is not None:
                self.black_time_seconds += self.increment_seconds

        # אפקטים קוליים
        if self.engine.board.is_checkmate():
            sound_effects.play_game_end_sound(True)
        elif self.engine.board.is_check():
            sound_effects.play_check_sound()
        elif is_capture:
            sound_effects.play_capture_sound()
        else:
            sound_effects.play_move_sound()

        # עדכון לוח וממשק
        self.board_widget.set_last_move(chess.Move.from_uci(uci))
        self.update_history_table()
        self.update_score_and_captures()
        self.update_game_status_display()
        self.update_clock_labels()

        # אם מקוון - שיגור המהלך
        if self.is_online and not self.is_spectator:
            sheet_id = self.txt_sheet_id.text().strip()
            move_num = len(self.engine.history)
            fen = self.engine.board.fen()

            action_status = "MOVE"
            if self.engine.board.is_checkmate():
                action_status = "CHECKMATE"
            elif self.engine.board.is_check():
                action_status = "CHECK"

            self.run_background_task(
                "send_move",
                sheet_id=sheet_id,
                room_id=self.game_id,
                move_num=move_num,
                player_name=self.player_name,
                color=color_str,
                move_uci=uci,
                move_san=san,
                fen=fen,
                action=action_status
            )

    # ------------------ דגימה מאוחדת (Polling) ------------------

    def start_polling(self, interval_ms: int = 1800):
        if not self.is_online:
            return
        self.is_polling_active = True
        self.poll_timer.start(interval_ms)

    def stop_polling(self):
        self.is_polling_active = False
        self.poll_timer.stop()

    def poll_room_bundle(self):
        """שליפת מטא, מהלכים וצ'אט בבקשה אחת מהירה"""
        if not self.is_online or self.is_polling_busy:
            return

        sheet_id = self.txt_sheet_id.text().strip()
        if not sheet_id:
            return

        self.run_background_task(
            "poll_bundle",
            sheet_id=sheet_id,
            room_id=self.game_id,
            after_move_num=len(self.engine.history),
            after_msg_id=self.last_chat_msg_id
        )

    # ------------------ צ'אט חי ------------------

    def on_chat_enter_pressed(self):
        msg = self.txt_chat_input.text().strip()
        if msg:
            self.send_chat_message(msg)
            self.txt_chat_input.clear()

    def send_chat_message(self, text: str):
        """שליחת הודעת צ'אט לגיליון החדר"""
        if not self.is_online:
            self.append_chat_message(datetime.datetime.now().strftime("%H:%M:%S"), self.player_name, "מקומי", text)
            return

        sheet_id = self.txt_sheet_id.text().strip()
        if not sheet_id:
            return

        self.last_chat_msg_id += 1
        my_id = self.last_chat_msg_id
        color_str = "SPEC" if self.is_spectator else ("W" if self.local_color == chess.WHITE else "B")

        # הוספה מיידית למסך
        curr_time = datetime.datetime.now().strftime("%H:%M:%S")
        self.append_chat_message(curr_time, self.player_name, color_str, text)

        self.run_background_task(
            "send_chat",
            sheet_id=sheet_id,
            room_id=self.game_id,
            msg_id=my_id,
            sender=self.player_name,
            color=color_str,
            message=text
        )

    def append_chat_message(self, time_str: str, sender: str, color_tag: str, text: str):
        badge_color = "#1A73E8" if color_tag == "W" else ("#202124" if color_tag == "B" else "#5F6368")
        color_name = "לבן" if color_tag == "W" else ("שחור" if color_tag == "B" else "צופה")

        html = f"""
        <div style="margin-bottom: 6px;">
            <span style="color: #80868B; font-size: 11px;">[{time_str}]</span>
            <span style="font-weight: bold; color: {badge_color};"> {sender} ({color_name}):</span>
            <span style="color: #202124;"> {text}</span>
        </div>
        """
        self.txt_chat_history.append(html)
        self.txt_chat_history.verticalScrollBar().setValue(self.txt_chat_history.verticalScrollBar().maximum())

    # ------------------ החזרת מהלך, תיקו וכניעה ------------------

    def on_takeback_clicked(self):
        """בקשת החזרת מהלך (Takeback)"""
        if not self.engine.history:
            QMessageBox.information(self, "החזרת מהלך", "טרם בוצעו מהלכים במשחק.")
            return

        if not self.is_online:
            # במשחק מקומי - אישור מיידי
            self.engine.pop_last_move()
            self.nav_last_move()
            self.update_history_table()
            self.update_score_and_captures()
            self.update_game_status_display()
            return

        sheet_id = self.txt_sheet_id.text().strip()
        color_str = "W" if self.local_color == chess.WHITE else "B"

        # אם תור היריב כרגע (אנחנו בדיוק עשינו מהלך שגוי) - ביטול מהלך 1
        # אם תורנו כרגע (היריב כבר ענה למהלך שלנו) - ביטול 2 מהלכים כדי לחזור למצב לפני המהלך שלנו
        popped_count = 1 if (self.engine.get_turn() != self.local_color) else 2
        if popped_count > len(self.engine.history):
            popped_count = len(self.engine.history)

        self.run_background_task(
            "send_action",
            sheet_id=sheet_id,
            room_id=self.game_id,
            player_name=self.player_name,
            color=color_str,
            action=f"TAKEBACK_REQ_{popped_count}"
        )
        QMessageBox.information(self, "בקשת החזרה", f"בקשת ביטול {popped_count} מהלכים נשלחה ליריב. ממתין לאישורו...")

    def on_draw_clicked(self):
        """הצעת תיקו ליריב"""
        if self.is_online:
            sheet_id = self.txt_sheet_id.text().strip()
            color_str = "W" if self.local_color == chess.WHITE else "B"
            self.run_background_task(
                "send_action",
                sheet_id=sheet_id,
                room_id=self.game_id,
                player_name=self.player_name,
                color=color_str,
                action="DRAW_OFFER"
            )
            QMessageBox.information(self, "הצעת תיקו", "הצעת התיקו נשלחה ליריב.")
        else:
            res = QMessageBox.question(self, "תיקו", "האם להסכים על תיקו?")
            if res == QMessageBox.Yes:
                self.record_game_end(winner="draw")

    def on_resign_clicked(self):
        res = QMessageBox.question(self, "כניעה", "האם אתה בטוח שברצונך להיכנע?")
        if res == QMessageBox.Yes:
            if self.is_online:
                sheet_id = self.txt_sheet_id.text().strip()
                color_str = "W" if self.local_color == chess.WHITE else "B"
                self.run_background_task(
                    "send_action",
                    sheet_id=sheet_id,
                    room_id=self.game_id,
                    player_name=self.player_name,
                    color=color_str,
                    action="RESIGN"
                )
            self.record_game_end(winner="opponent")
            sound_effects.play_game_end_sound(False)
            QMessageBox.information(self, "המשחק הסתיים", "נכנעת. המשחק הסתיים.")

    def record_game_end(self, winner: str):
        self.clock_timer.stop()
        if winner == "local":
            if self.local_color == chess.WHITE:
                self.score_white += 1
            else:
                self.score_black += 1
        elif winner == "opponent":
            if self.local_color == chess.WHITE:
                self.score_black += 1
            else:
                self.score_white += 1
        elif winner == "draw":
            self.score_draws += 1

        self.lbl_session_score.setText(f"ניקוד סשן: לבן {self.score_white} | שחור {self.score_black} | תיקו {self.score_draws}")
        self.stop_polling()
        self.board_widget.interactive = False

    def on_new_game_clicked(self):
        res = QMessageBox.question(self, "משחק חדש", "האם לאפס את הלוח ולהתחיל משחק חדש?")
        if res == QMessageBox.Yes:
            self.engine.reset()
            self.is_reviewing = False
            self.board_widget.board = self.engine.board
            self.board_widget.set_last_move(None)
            self.board_widget.clear_selection()
            self.update_history_table()
            self.update_score_and_captures()
            self.update_game_status_display()
            tc = self.combo_time_control.currentText()
            self.setup_time_control(tc)

    # ------------------ ניהול רקע ו-Worker (Thread-Safe) ------------------

    def run_background_task(self, task_type: str, **kwargs):
        if task_type == "poll_bundle":
            if self.is_polling_busy:
                return
            self.is_polling_busy = True

        worker = ChessNetworkWorker(self.sync_mgr, task_type, **kwargs)
        self.active_workers.append(worker)

        def _on_done(t_type, s_ok, d_res, e_msg):
            try:
                self.on_worker_finished(t_type, s_ok, d_res, e_msg)
            finally:
                if worker in self.active_workers:
                    self.active_workers.remove(worker)
                worker.deleteLater()

        worker.finished_task.connect(_on_done)
        worker.start()

    def on_worker_finished(self, task_type: str, success: bool, data: Any, err_msg: str):
        if task_type == "poll_bundle":
            self.is_polling_busy = False
            if success and data:
                self.process_poll_bundle_result(data)

        elif task_type == "send_move":
            if not success:
                QMessageBox.warning(self, "שגיאת סנכרון מהלך", f"כשל בשליחת המהלך ל-Google Sheets:\n{err_msg}")

        elif task_type == "create_sheet":
            if success and data:
                new_id = data.get("id")
                new_url = data.get("url")
                self.txt_sheet_id.setText(new_id)
                save_config({"spreadsheet_id": new_id})
                self.update_invite_code_display()
                QMessageBox.information(
                    self,
                    "גיליון שחמט חדש נוצר בהצלחה!",
                    f"קובץ ה-Google Sheet נוצר בהצלחה בחשבונך!\n\nמזהה גיליון:\n{new_id}\n\n"
                    f"קישור:\n{new_url}\n\n"
                    f"הערה חשובה עבור נטפרי: ודא שחברך קיבל הרשאת עריכה (Editor) לגיליון זה כדי שיוכל לשלוח מהלכים."
                )
            else:
                QMessageBox.critical(self, "שגיאה ביצירת גיליון", f"נכשל ביצירת גיליון חדש:\n{err_msg}")

        elif task_type == "create_room":
            if success:
                self.lbl_room_status.setText(f"מארח חדר {self.game_id} (לבן)")
                self.lbl_room_status.setStyleSheet("color: #137333; font-weight: bold;")
                self.update_invite_code_display()
                self.tabs.setCurrentIndex(0)
                tc = self.combo_time_control.currentText()
                self.setup_time_control(tc)
                self.start_polling(interval_ms=1800)
                QMessageBox.information(
                    self,
                    "החדר נפתח בהצלחה!",
                    f"חדר המשחק {self.game_id} מוכן בגיליון!\n\nשתף את קוד ההזמנה עם חברך:\n{self.lbl_invite_code.text()}"
                )
            else:
                QMessageBox.critical(self, "שגיאה בפתיחת חדר", f"לא ניתן לפתוח את החדר:\n{err_msg}")

        elif task_type == "join_room":
            if success:
                info = data or {}
                h_name = info.get("host_name", "מארח")
                h_color = info.get("host_color", "W")
                tc = info.get("time_control", "NONE")
                self.opponent_name = h_name

                # אם הצטרף כשחקן נגדי
                if not self.is_spectator:
                    if h_color == "W":
                        self.local_color = chess.BLACK
                        self.board_widget.set_player_color(chess.BLACK)
                    else:
                        self.local_color = chess.WHITE
                        self.board_widget.set_player_color(chess.WHITE)

                color_title = "צופה" if self.is_spectator else ("שחור" if self.local_color == chess.BLACK else "לבן")
                self.lbl_room_status.setText(f"מחובר לחדר {self.game_id} ({color_title})")
                self.lbl_room_status.setStyleSheet("color: #137333; font-weight: bold;")
                self.setup_time_control(tc)
                self.tabs.setCurrentIndex(0)
                self.start_polling(interval_ms=1800)
                self.update_score_and_captures()
                self.update_game_status_display()
                QMessageBox.information(self, "חיבור לחדר הצליח!", f"התחברת לחדר {self.game_id} מול {h_name}!")
            else:
                QMessageBox.warning(self, "שגיאה בהצטרפות", f"לא ניתן להצטרף לחדר:\n{err_msg}")

        elif task_type == "fetch_lobby":
            if success and isinstance(data, list):
                self.populate_lobby_table(data)
            else:
                QMessageBox.warning(self, "שגיאה בטעינת לובי", f"נכשל במשיכת רשימת הלובי:\n{err_msg}")

    def process_poll_bundle_result(self, data: Dict[str, Any]):
        """עיבוד תוצאות ה-Polling המאוחדות: מטא, מהלכים וצ'אט"""
        meta = data.get("meta", {})
        moves = data.get("moves", [])
        chat_msgs = data.get("chat", [])

        # 1. עיבוד מטא-דאטה (הצטרפות שחקן, תיקו, כניעה, החזרת מהלך)
        if meta:
            guest = meta.get("guest_player", "")
            host = meta.get("host_player", "")
            if guest and self.local_color == chess.WHITE and self.opponent_name != guest:
                self.opponent_name = guest
                self.update_score_and_captures()

            action_status = meta.get("action_status", "NONE")
            my_color_code = "W" if self.local_color == chess.WHITE else "B"
            opp_color_code = "B" if self.local_color == chess.WHITE else "W"

            # כניעה של היריב
            if f"RESIGN_{opp_color_code}" in action_status:
                self.sync_mgr.update_action_status(self.txt_sheet_id.text().strip(), self.game_id, "NONE")
                sound_effects.play_game_end_sound(True)
                QMessageBox.information(self, "ניצחון!", f"השחקן {self.opponent_name} נכנע. ניצחת במשחק!")
                self.record_game_end(winner="local")
                return

            # הצעת תיקו מהיריב
            if f"DRAW_OFFER_{opp_color_code}" in action_status:
                self.sync_mgr.update_action_status(self.txt_sheet_id.text().strip(), self.game_id, "NONE")
                res = QMessageBox.question(self, "הצעת תיקו", f"השחקן {self.opponent_name} מציע תיקו. האם להסכים?")
                if res == QMessageBox.Yes:
                    self.sync_mgr.update_action_status(self.txt_sheet_id.text().strip(), self.game_id, f"DRAW_ACCEPTED_{my_color_code}", "FINISHED")
                    self.record_game_end(winner="draw")
                else:
                    self.sync_mgr.update_action_status(self.txt_sheet_id.text().strip(), self.game_id, f"DRAW_DECLINED_{my_color_code}")
                return

            if f"DRAW_ACCEPTED_{opp_color_code}" in action_status:
                self.sync_mgr.update_action_status(self.txt_sheet_id.text().strip(), self.game_id, "NONE")
                self.record_game_end(winner="draw")
                QMessageBox.information(self, "המשחק הסתיים", "היריב קיבל את הצעת התיקו!")
                return

            # בקשת החזרת מהלך (Takeback)
            if "TAKEBACK_REQ_" in action_status and f"_{opp_color_code}" in action_status:
                self.sync_mgr.update_action_status(self.txt_sheet_id.text().strip(), self.game_id, "NONE")
                count = 1
                try:
                    parts = action_status.split("_")
                    count = int(parts[2])
                except Exception:
                    count = 1

                res = QMessageBox.question(self, "בקשת החזרת מהלך", f"השחקן {self.opponent_name} מבקש להחזיר {count} מהלכים אחורה. האם להסכים?")
                if res == QMessageBox.Yes:
                    sheet_id = self.txt_sheet_id.text().strip()
                    for _ in range(count):
                        self.engine.pop_last_move()
                    # מחיקה נקייה של השורות מהגיליון כדי שלא ייקראו שוב
                    self.sync_mgr.remove_last_moves(sheet_id, self.game_id, count=count)
                    self.nav_last_move()
                    self.update_history_table()
                    self.update_score_and_captures()
                    self.update_game_status_display()
                    self.sync_mgr.update_action_status(sheet_id, self.game_id, f"TAKEBACK_ACC_{count}_{my_color_code}")
                else:
                    self.sync_mgr.update_action_status(self.txt_sheet_id.text().strip(), self.game_id, f"TAKEBACK_DECLINED_{my_color_code}")
                return

            if "TAKEBACK_ACC_" in action_status and f"_{opp_color_code}" in action_status:
                self.sync_mgr.update_action_status(self.txt_sheet_id.text().strip(), self.game_id, "NONE")
                count = 1
                try:
                    parts = action_status.split("_")
                    count = int(parts[2])
                except Exception:
                    count = 1

                for _ in range(count):
                    self.engine.pop_last_move()
                self.nav_last_move()
                self.update_history_table()
                self.update_score_and_captures()
                self.update_game_status_display()
                QMessageBox.information(self, "החזרת מהלך", f"היריב אישר את ביטול {count} המהלכים.")
                return

        # 2. עיבוד מהלכים חדשים
        if moves:
            for m in moves:
                uci = m.get("move_uci", "")
                p_name = m.get("player", "יריב")
                c_str = m.get("color", "")

                if not uci:
                    continue

                # בדיקה האם זהו מהלך היריב לפי צבע ולא לפי שם שחקן!
                my_color_str = "W" if self.local_color == chess.WHITE else "B"
                is_opp_move = (c_str != my_color_str) if not self.is_spectator else True

                if is_opp_move:
                    self.opponent_name = p_name

                    # בדיקת אכילה לפני ביצוע
                    try:
                        mv = chess.Move.from_uci(uci)
                        is_capture = self.engine.board.is_capture(mv)
                    except Exception:
                        is_capture = False

                    success, san, err = self.engine.push_move(uci, p_name)
                    if success:
                        # תוספת זמן
                        if self.increment_seconds > 0:
                            if c_str == "W" and self.white_time_seconds is not None:
                                self.white_time_seconds += self.increment_seconds
                            elif c_str == "B" and self.black_time_seconds is not None:
                                self.black_time_seconds += self.increment_seconds

                        # צלילים
                        if self.engine.board.is_checkmate():
                            sound_effects.play_game_end_sound(False)
                        elif self.engine.board.is_check():
                            sound_effects.play_check_sound()
                        elif is_capture:
                            sound_effects.play_capture_sound()
                        else:
                            sound_effects.play_move_sound()

                        self.nav_last_move()
                        self.update_history_table()
                        self.update_score_and_captures()
                        self.update_game_status_display()
                        self.update_clock_labels()

        # 3. עיבוד הודעות צ'אט חדשות
        if chat_msgs:
            played_chat_sound = False
            for c in chat_msgs:
                c_id = c.get("msg_id", 0)
                if c_id > self.last_chat_msg_id:
                    self.last_chat_msg_id = c_id
                    sender = c.get("sender", "")
                    if sender != self.player_name:
                        self.append_chat_message(c.get("timestamp", ""), sender, c.get("color", ""), c.get("text", ""))
                        played_chat_sound = True

            if played_chat_sound:
                sound_effects.play_chat_sound()

    # ------------------ ניהול חדרים והתחברות ------------------

    def generate_new_room_code(self):
        self.game_id = f"Room_{random.randint(1000, 9999)}"
        self.txt_game_id.setText(self.game_id)
        self.update_invite_code_display()

    def update_invite_code_display(self):
        sheet_id = self.txt_sheet_id.text().strip()
        room_id = self.txt_game_id.text().strip().upper()
        if sheet_id and room_id:
            code = encode_invite_code(sheet_id, room_id)
            self.lbl_invite_code.setText(code)

    def copy_invite_code(self):
        code = self.lbl_invite_code.text().strip()
        if code:
            QApplication.clipboard().setText(code)
            QMessageBox.information(self, "הועתק", f"קוד ההזמנה הועתק ללוח:\n{code}\n\nשלח אותו לחברך!")

    def on_create_new_sheet_clicked(self):
        """יצירת קובץ Google Spreadsheet חדש לגמרי בחשבון המשתמש"""
        if not self.sheets_client.is_logged_in():
            success, msg, _ = self.sheets_client.authenticate(prompt_browser=True)
            if not success:
                QMessageBox.critical(self, "כשל בהתחברות Google", msg)
                return

        self.run_background_task("create_sheet", title="פלטפורמת שחמט מקוון בנטפרי")

    def on_host_create_room_clicked(self):
        """פתיחת חדר חדש כמארח (לבן)"""
        try:
            sheet_id = extract_spreadsheet_id(self.txt_sheet_id.text().strip())
            if not sheet_id:
                QMessageBox.warning(self, "חסר גיליון", "נא להזין מזהה Google Sheet או ליצור גיליון חדש בכפתור למעלה.")
                return

            if not self.sheets_client.is_logged_in():
                success, msg, _ = self.sheets_client.authenticate(prompt_browser=True)
                if not success:
                    QMessageBox.critical(self, "כשל בהתחברות Google", msg)
                    return

            r_id = self.txt_game_id.text().strip().upper()
            if not r_id:
                r_id = f"CHESS_{random.randint(1000, 9999)}"
                self.txt_game_id.setText(r_id)
            self.game_id = r_id

            self.is_online = True
            self.is_spectator = False
            self.local_color = chess.WHITE
            self.board_widget.set_player_color(chess.WHITE)

            tc = self.combo_time_control.currentText()
            pub = self.chk_publish_lobby.isChecked()

            self.run_background_task(
                "create_room",
                sheet_id=sheet_id,
                room_id=self.game_id,
                host_name=self.player_name,
                host_color="W",
                time_control=tc,
                publish_lobby=pub
            )
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בפתיחת חדר", f"אירעה שגיאה:\n{e}")

    def on_join_by_code_clicked(self):
        """הצטרפות לפי קוד הזמנה חכם (NETFREE#...)"""
        try:
            raw_code = self.txt_join_code.text().strip()
            if not raw_code:
                QMessageBox.warning(self, "קוד חסר", "נא להדביק את קוד ההזמנה שקיבלת מהחבר.")
                return

            sheet_id, room_id, g_type = decode_invite_code(raw_code)
            if not sheet_id or not room_id:
                # אולי הדביק רק מזהה חדר
                sheet_id = extract_spreadsheet_id(self.txt_sheet_id.text().strip())
                room_id = raw_code.upper()

            if not sheet_id:
                QMessageBox.warning(self, "מזהה גיליון חסר", "הקוד שהוזן אינו מכיל מזהה גיליון מלא, ומזהה הגיליון במסך ריק.")
                return

            self.txt_sheet_id.setText(sheet_id)
            self.txt_game_id.setText(room_id)
            self.game_id = room_id

            if not self.sheets_client.is_logged_in():
                success, msg, _ = self.sheets_client.authenticate(prompt_browser=True)
                if not success:
                    QMessageBox.critical(self, "כשל בהתחברות Google", msg)
                    return

            self.is_online = True
            self.is_spectator = (self.combo_mode.currentIndex() == 2)
            self.run_background_task(
                "join_room",
                sheet_id=sheet_id,
                room_id=room_id,
                guest_name=self.player_name
            )
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בהצטרפות", f"אירעה שגיאה:\n{e}")

    def on_manual_connect_clicked(self):
        """התחברות ידנית לפי הגדרות החלון"""
        idx = self.combo_mode.currentIndex()
        sheet_id = self.txt_sheet_id.text().strip()
        self.game_id = self.txt_game_id.text().strip().upper()

        if idx in (0, 1, 2):
            if not sheet_id:
                QMessageBox.warning(self, "חסר גיליון", "נא להזין מזהה Google Sheet או ליצור גיליון חדש.")
                return

            if not self.sheets_client.is_logged_in():
                success, msg, _ = self.sheets_client.authenticate(prompt_browser=True)
                if not success:
                    QMessageBox.critical(self, "כשל בהתחברות Google", msg)
                    return

            self.is_online = True
            if idx == 0:
                self.is_spectator = False
                self.local_color = chess.WHITE
                self.board_widget.set_player_color(chess.WHITE)
            elif idx == 1:
                self.is_spectator = False
                self.local_color = chess.BLACK
                self.board_widget.set_player_color(chess.BLACK)
            else:
                self.is_spectator = True
                self.local_color = None
                self.board_widget.set_player_color(None)

            self.run_background_task(
                "join_room",
                sheet_id=sheet_id,
                room_id=self.game_id,
                guest_name=self.player_name
            )
        else:
            # מקומי
            self.is_online = False
            self.is_spectator = False
            self.local_color = None
            self.board_widget.set_player_color(None)
            self.lbl_room_status.setText("משחק מקומי")
            self.lbl_room_status.setStyleSheet("color: #5F6368; font-weight: bold;")
            self.stop_polling()
            self.tabs.setCurrentIndex(0)

    def on_mode_changed(self, idx: int):
        save_config({"mode_index": idx})
        if idx == 0:
            self.is_online = True
            self.is_spectator = False
            self.local_color = chess.WHITE
            self.board_widget.set_player_color(chess.WHITE)
        elif idx == 1:
            self.is_online = True
            self.is_spectator = False
            self.local_color = chess.BLACK
            self.board_widget.set_player_color(chess.BLACK)
        elif idx == 2:
            self.is_online = True
            self.is_spectator = True
            self.local_color = None
            self.board_widget.set_player_color(None)
        else:
            self.is_online = False
            self.is_spectator = False
            self.local_color = None
            self.board_widget.set_player_color(None)
            self.stop_polling()

        self.update_score_and_captures()
        self.update_game_status_display()

    # ------------------ לובי ------------------

    def on_refresh_lobby_clicked(self):
        sheet_id = self.txt_sheet_id.text().strip()
        if not sheet_id:
            QMessageBox.warning(self, "חסר גיליון", "נא להזין מזהה Google Sheet כדי לטעון את הלובי.")
            return

        if not self.sheets_client.is_logged_in():
            success, msg, _ = self.sheets_client.authenticate(prompt_browser=True)
            if not success:
                QMessageBox.critical(self, "כשל בהתחברות Google", msg)
                return

        self.run_background_task("fetch_lobby", sheet_id=sheet_id)

    def populate_lobby_table(self, games: List[Dict[str, Any]]):
        self.table_lobby.setRowCount(len(games))
        for row_idx, g in enumerate(games):
            r_item = QTableWidgetItem(g.get("room_id", ""))
            r_item.setTextAlignment(Qt.AlignCenter)
            h_item = QTableWidgetItem(g.get("host_name", ""))
            h_item.setTextAlignment(Qt.AlignCenter)
            t_item = QTableWidgetItem(g.get("time_control", ""))
            t_item.setTextAlignment(Qt.AlignCenter)
            c_item = QTableWidgetItem("לבן" if g.get("host_color") == "W" else "שחור")
            c_item.setTextAlignment(Qt.AlignCenter)
            s_item = QTableWidgetItem(g.get("created_at", ""))
            s_item.setTextAlignment(Qt.AlignCenter)

            self.table_lobby.setItem(row_idx, 0, r_item)
            self.table_lobby.setItem(row_idx, 1, h_item)
            self.table_lobby.setItem(row_idx, 2, t_item)
            self.table_lobby.setItem(row_idx, 3, c_item)
            self.table_lobby.setItem(row_idx, 4, s_item)

    def on_join_selected_lobby_game(self):
        curr_row = self.table_lobby.currentRow()
        if curr_row < 0:
            QMessageBox.information(self, "בחירת משחק", "נא לבחור שורה מהלובי כדי להצטרף.")
            return

        room_id = self.table_lobby.item(curr_row, 0).text()
        sheet_id = self.txt_sheet_id.text().strip()
        self.game_id = room_id
        self.txt_game_id.setText(room_id)

        self.is_online = True
        self.is_spectator = False
        self.run_background_task(
            "join_room",
            sheet_id=sheet_id,
            room_id=room_id,
            guest_name=self.player_name
        )

    # ------------------ דפדוף לא הרסני בהיסטוריה ו-PGN ------------------

    def on_history_cell_clicked(self, row: int, col: int):
        pairs = self.engine.get_paired_history()
        if 0 <= row < len(pairs):
            pair = pairs[row]
            fen = pair["white_fen"] if col == 1 else pair.get("black_fen")
            if fen:
                self.is_reviewing = True
                self.board_widget.board.set_fen(fen)
                self.board_widget.interactive = False
                self.board_widget.update()
                self.lbl_turn_status.setText("👁️ צפייה בהיסטוריה (לחץ >> למשחק החי)")
                self.lbl_turn_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #5F6368;")

    def nav_first_move(self):
        if not self.engine.history:
            return
        self.is_reviewing = True
        self.board_widget.board.reset()
        self.board_widget.set_last_move(None)
        self.board_widget.interactive = False
        self.board_widget.update()
        self.lbl_turn_status.setText("👁️ צפייה בהיסטוריה (לחץ >> למשחק החי)")
        self.lbl_turn_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #5F6368;")

    def nav_prev_move(self):
        if not self.engine.history:
            return
        curr_fen = self.board_widget.board.fen()
        idx = -1
        for i, rec in enumerate(self.engine.history):
            if rec.fen_after == curr_fen:
                idx = i
                break

        if idx > 0:
            self.is_reviewing = True
            prev_rec = self.engine.history[idx - 1]
            self.board_widget.board.set_fen(prev_rec.fen_after)
            self.board_widget.set_last_move(chess.Move.from_uci(prev_rec.uci))
            self.board_widget.interactive = False
            self.board_widget.update()
            self.lbl_turn_status.setText("👁️ צפייה בהיסטוריה (לחץ >> למשחק החי)")
            self.lbl_turn_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #5F6368;")
        elif idx == 0:
            self.nav_first_move()

    def nav_next_move(self):
        if not self.engine.history:
            return
        curr_fen = self.board_widget.board.fen()
        idx = -1
        for i, rec in enumerate(self.engine.history):
            if rec.fen_after == curr_fen:
                idx = i
                break

        if 0 <= idx < len(self.engine.history) - 1:
            next_rec = self.engine.history[idx + 1]
            self.board_widget.board.set_fen(next_rec.fen_after)
            self.board_widget.set_last_move(chess.Move.from_uci(next_rec.uci))
            self.board_widget.update()
            if idx + 1 == len(self.engine.history) - 1:
                self.nav_last_move()
        elif idx == -1:
            first_rec = self.engine.history[0]
            self.board_widget.board.set_fen(first_rec.fen_after)
            self.board_widget.set_last_move(chess.Move.from_uci(first_rec.uci))
            self.board_widget.update()
            if len(self.engine.history) == 1:
                self.nav_last_move()

    def nav_last_move(self):
        self.is_reviewing = False
        self.board_widget.board.set_fen(self.engine.board.fen())
        if self.engine.history:
            self.board_widget.set_last_move(chess.Move.from_uci(self.engine.history[-1].uci))
        else:
            self.board_widget.set_last_move(None)
        self.board_widget.update()
        self.update_game_status_display()

    def export_pgn_file(self):
        white = self.player_name if self.local_color == chess.WHITE else self.opponent_name
        black = self.opponent_name if self.local_color == chess.WHITE else self.player_name
        pgn_text = self.engine.export_pgn(white, black, f"Room {self.game_id}")

        default_filename = f"{self.game_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pgn"
        filepath, _ = QFileDialog.getSaveFileName(self, "שמור קובץ היסטוריית שחמט (PGN)", default_filename, "PGN Files (*.pgn);;Text Files (*.txt)")
        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(pgn_text)
            QMessageBox.information(self, "ייצוא הצליח", f"קובץ ה-PGN נשמר בהצלחה:\n{filepath}")

    def open_diagnostics(self):
        try:
            from app_gui import MainWindow
            self.diag_win = MainWindow()
            self.diag_win.show()
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בפתיחת כלי בדיקה", f"לא ניתן לפתוח את כלי הבדיקה:\n{e}")


def run_chess():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    app.setLayoutDirection(Qt.RightToLeft)
    win = ChessMainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    run_chess()
