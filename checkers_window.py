# -*- coding: utf-8 -*-
"""
חלון משחק דמקה מקוון בנטפרי - כולל סנכרון מקוון דרך Google Sheets API,
לוח עץ אינטראקטיבי, אכילת חובה, שרשרת אכילות, דמקה (מלכה מעופפת),
צ'אט חי, שעונים דיגיטליים, החזרת מהלך וקוד הזמנה חכם.
"""

import sys
import os
import random
import datetime
from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QComboBox, QMessageBox,
    QFrame, QTabWidget, QTextEdit, QCheckBox, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor

from checkers_engine import (
    CheckersEngine, CheckersMove, COLOR_WHITE, COLOR_BLACK, EMPTY
)
from checkers_board_widget import CheckersBoardWidget
from chess_sync import ChessSyncManager, encode_invite_code, decode_invite_code
from chess_engine import format_clock_time
from google_sheets_client import GoogleSheetsClient, extract_spreadsheet_id, load_config, save_config
from theme_style import get_gaming_stylesheet
import sound_effects


class CheckersNetworkWorker(QThread):
    finished_task = Signal(str, bool, object, str)

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
                        host_color=self.kwargs.get("host_color", "W"),
                        game_type="CHECKERS"
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
                    spreadsheet_id=self.kwargs["sheet_id"],
                    game_type_filter="CHECKERS"
                )
                self.finished_task.emit("fetch_lobby", success, games, err)

            elif self.task_type == "create_sheet":
                success, sheet_id, sheet_url = self.sync_mgr.client.create_new_spreadsheet(
                    title=self.kwargs.get("title", "משחקי דמקה ושחמט בנטפרי")
                )
                self.finished_task.emit("create_sheet", success, {"id": sheet_id, "url": sheet_url}, "" if success else sheet_id)

        except Exception as e:
            self.finished_task.emit(self.task_type, False, None, str(e))


class CheckersMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = CheckersEngine()
        self.sheets_client = GoogleSheetsClient()
        self.sync_mgr = ChessSyncManager(self.sheets_client)

        cfg = load_config()
        self.saved_mode = cfg.get("mode_index", 0)
        self.is_online = (self.saved_mode in (0, 1, 2))
        self.is_spectator = (self.saved_mode == 2)
        if self.saved_mode == 0:
            self.local_color: Optional[int] = COLOR_WHITE
        elif self.saved_mode == 1:
            self.local_color: Optional[int] = COLOR_BLACK
        else:
            self.local_color = None

        self.game_id = cfg.get("checkers_game_id") or f"Checkers_{random.randint(1000, 9999)}"
        saved_nick = cfg.get("player_nickname")
        if saved_nick:
            self.player_name = saved_nick
        else:
            self.player_name = f"{self.sheets_client.computer_name}#{random.randint(100, 999)}"
            save_config({"player_nickname": self.player_name})

        self.opponent_name = "יריב"
        self.last_chat_msg_id = 0

        # שעונים דיגיטליים
        self.white_time_seconds: Optional[int] = None
        self.black_time_seconds: Optional[int] = None
        self.increment_seconds = 0
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.on_clock_tick)

        # ניקוד סשן
        self.score_white = 0
        self.score_black = 0
        self.score_draws = 0

        # דגימה מקוונת
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_room_bundle)
        self.is_polling_active = False

        self.active_workers: List[CheckersNetworkWorker] = []
        self.is_polling_busy = False
        self.is_reviewing = False

        self.init_ui()
        self.update_game_status_display()
        self.update_score_display()
        self.update_clock_labels()
        self.update_auth_status_ui()

    def init_ui(self):
        self.setWindowTitle("דמקה מקוונת בנטפרי – פלטפורמת משחקי לוח דרך Google Sheets API")
        self.resize(1180, 800)
        self.setMinimumSize(1020, 700)
        self.setStyleSheet(get_gaming_stylesheet())

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # ------------------ צד ימין: לוח דמקה וכרטיסי שחקנים ------------------
        board_panel = QVBoxLayout()
        board_panel.setSpacing(8)

        self.card_top_player = self.create_player_card("יריב (שחור)", is_top=True)
        board_panel.addWidget(self.card_top_player)

        self.board_widget = CheckersBoardWidget(self.engine)
        self.board_widget.move_attempted.connect(self.on_player_move_attempted)
        board_panel.addWidget(self.board_widget, stretch=1)

        self.card_bottom_player = self.create_player_card(f"{self.player_name} (לבן)", is_top=False)
        board_panel.addWidget(self.card_bottom_player)

        main_layout.addLayout(board_panel, stretch=6)

        # ------------------ צד שמאל: לשוניות ניהול ------------------
        self.tabs = QTabWidget()

        # לשונית 1: משחק וצ'אט
        tab_game = QWidget()
        self.init_game_tab(tab_game)
        self.tabs.addTab(tab_game, "🎮 משחק וצ'אט")

        # לשונית 2: חדר והתחברות
        tab_room = QWidget()
        self.init_room_tab(tab_room)
        self.tabs.addTab(tab_room, "🌐 חדר והזמנה")

        # לשונית 3: לובי
        tab_lobby = QWidget()
        self.init_lobby_tab(tab_lobby)
        self.tabs.addTab(tab_lobby, "👥 לובי דמקה")

        main_layout.addWidget(self.tabs, stretch=5)

    def create_player_card(self, title: str, is_top: bool) -> QFrame:
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

        lbl_pieces = QLabel("")
        lbl_pieces.setStyleSheet("font-size: 14px; color: #34D399; font-weight: bold;")

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
        layout.addWidget(lbl_pieces)
        layout.addStretch()
        layout.addWidget(lbl_clock)

        if is_top:
            self.lbl_top_name = lbl_name
            self.lbl_top_pieces = lbl_pieces
            self.lbl_top_clock = lbl_clock
            self.card_top = card
        else:
            self.lbl_bottom_name = lbl_name
            self.lbl_bottom_pieces = lbl_pieces
            self.lbl_bottom_clock = lbl_clock
            self.card_bottom = card

        return card

    def init_game_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # באנר סטטוס
        self.banner_status = QFrame()
        self.banner_status.setStyleSheet("QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #064E3B, stop:1 #1E293B); border: 1.5px solid #059669; border-radius: 8px; padding: 6px; }")
        b_layout = QVBoxLayout(self.banner_status)
        self.lbl_turn_status = QLabel("תור הלבן")
        self.lbl_turn_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #34D399;")
        self.lbl_turn_status.setAlignment(Qt.AlignCenter)
        self.lbl_extra_status = QLabel("המשחק החל. מהלך 1")
        self.lbl_extra_status.setStyleSheet("font-size: 12px; color: #94A3B8;")
        self.lbl_extra_status.setAlignment(Qt.AlignCenter)
        b_layout.addWidget(self.lbl_turn_status)
        b_layout.addWidget(self.lbl_extra_status)
        layout.addWidget(self.banner_status)

        # סרגל פעולות
        act_layout = QHBoxLayout()
        self.btn_resign = QPushButton("🏳️ היכנע")
        self.btn_resign.clicked.connect(self.on_resign_clicked)
        self.btn_draw = QPushButton("🤝 הצע תיקו")
        self.btn_draw.clicked.connect(self.on_draw_clicked)
        self.btn_takeback = QPushButton("↩️ בקש החזרה")
        self.btn_takeback.clicked.connect(self.on_takeback_clicked)
        self.btn_new_game = QPushButton("🔄 משחק חדש")
        self.btn_new_game.clicked.connect(self.on_new_game_clicked)

        act_layout.addWidget(self.btn_resign)
        act_layout.addWidget(self.btn_draw)
        act_layout.addWidget(self.btn_takeback)
        act_layout.addWidget(self.btn_new_game)
        layout.addLayout(act_layout)

        # היסטוריית מהלכים
        hist_box = QGroupBox("היסטוריית מהלכים")
        h_layout = QVBoxLayout(hist_box)
        self.table_history = QTableWidget()
        self.table_history.setColumnCount(3)
        self.table_history.setHorizontalHeaderLabels(["תור", "לבן", "שחור"])
        self.table_history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_history.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_history.setMaximumHeight(140)
        h_layout.addWidget(self.table_history)
        layout.addWidget(hist_box)

        # צ'אט חי
        chat_box = QGroupBox("💬 צ'אט חי")
        c_layout = QVBoxLayout(chat_box)
        self.txt_chat_history = QTextEdit()
        self.txt_chat_history.setReadOnly(True)
        c_layout.addWidget(self.txt_chat_history, stretch=1)

        # תגובות מהירות
        q_layout = QHBoxLayout()
        for phrase in ["בהצלחה! 🤝", "מהלך יפה! 👏", "אופס... 😅", "תודה על המשחק! 🏆"]:
            btn_q = QPushButton(phrase)
            btn_q.clicked.connect(lambda _, p=phrase: self.send_chat_message(p))
            q_layout.addWidget(btn_q)
        c_layout.addLayout(q_layout)

        in_layout = QHBoxLayout()
        self.txt_chat_input = QLineEdit()
        self.txt_chat_input.setPlaceholderText("הקלד הודעה בצ'אט ולחץ Enter...")
        self.txt_chat_input.returnPressed.connect(self.on_chat_enter_pressed)
        btn_send = QPushButton("שלח")
        btn_send.clicked.connect(self.on_chat_enter_pressed)
        in_layout.addWidget(self.txt_chat_input)
        in_layout.addWidget(btn_send)
        c_layout.addLayout(in_layout)

        layout.addWidget(chat_box, stretch=1)

        self.lbl_session_score = QLabel("ניקוד סשן: לבן 0 | שחור 0 | תיקו 0")
        self.lbl_session_score.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_session_score)

    def init_room_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # 1. גיליון
        s_box = QGroupBox("1. חיבור גיליון Google Sheets")
        s_layout = QVBoxLayout(s_box)

        row_auth = QHBoxLayout()
        self.lbl_auth_status = QLabel("⚪ בודק חשבון...")
        row_auth.addWidget(self.lbl_auth_status, stretch=1)

        self.btn_auth_login = QPushButton("🔑 התחבר ל-Google")
        self.btn_auth_login.setObjectName("btnPrimary")
        self.btn_auth_login.clicked.connect(self.on_login_clicked)
        row_auth.addWidget(self.btn_auth_login)

        self.btn_auth_logout = QPushButton("🚪 התנתק")
        self.btn_auth_logout.setObjectName("btnDanger")
        self.btn_auth_logout.clicked.connect(self.on_logout_clicked)
        row_auth.addWidget(self.btn_auth_logout)

        s_layout.addLayout(row_auth)

        btn_create = QPushButton("📄 צור גיליון שחמט/דמקה חדש בחשבונך")
        btn_create.setObjectName("btnSuccess")
        btn_create.clicked.connect(self.on_create_new_sheet_clicked)
        s_layout.addWidget(btn_create)

        row_s = QHBoxLayout()
        row_s.addWidget(QLabel("מזהה גיליון:"))
        self.txt_sheet_id = QLineEdit(load_config().get("spreadsheet_id", ""))
        self.txt_sheet_id.textChanged.connect(lambda t: save_config({"spreadsheet_id": t.strip()}))
        row_s.addWidget(self.txt_sheet_id)
        s_layout.addLayout(row_s)
        layout.addWidget(s_box)

        # 2. אירוח
        h_box = QGroupBox("2. אירוח משחק דמקה (מארח)")
        h_layout = QVBoxLayout(h_box)

        row_tc = QHBoxLayout()
        row_tc.addWidget(QLabel("בקרת זמן:"))
        self.combo_time_control = QComboBox()
        self.combo_time_control.addItems(["ללא הגבלת זמן", "5 דקות", "10 דקות", "15 דקות + 5 שניות"])
        row_tc.addWidget(self.combo_time_control)
        h_layout.addLayout(row_tc)

        row_r = QHBoxLayout()
        row_r.addWidget(QLabel("מזהה חדר:"))
        self.txt_game_id = QLineEdit(self.game_id)
        self.txt_game_id.textChanged.connect(lambda t: save_config({"checkers_game_id": t.strip().upper()}))
        btn_new_r = QPushButton("חדר חדש")
        btn_new_r.clicked.connect(self.generate_new_room_code)
        row_r.addWidget(self.txt_game_id)
        row_r.addWidget(btn_new_r)
        h_layout.addLayout(row_r)

        self.chk_publish_lobby = QCheckBox("פרסם משחק זה בלובי המרכזי")
        self.chk_publish_lobby.setChecked(True)
        h_layout.addWidget(self.chk_publish_lobby)

        btn_start_h = QPushButton("🚀 פתח חדר דמקה והתחל כמארח")
        btn_start_h.clicked.connect(self.on_host_create_room_clicked)
        h_layout.addWidget(btn_start_h)

        row_inv = QHBoxLayout()
        row_inv.addWidget(QLabel("קוד הזמנה:"))
        self.lbl_invite_code = QLineEdit()
        self.lbl_invite_code.setReadOnly(True)
        btn_copy = QPushButton("📋 העתק")
        btn_copy.clicked.connect(self.copy_invite_code)
        row_inv.addWidget(self.lbl_invite_code)
        row_inv.addWidget(btn_copy)
        h_layout.addLayout(row_inv)
        layout.addWidget(h_box)

        # 3. הצטרפות
        j_box = QGroupBox("3. הצטרפות למשחק דמקה")
        j_layout = QVBoxLayout(j_box)
        row_code = QHBoxLayout()
        self.txt_join_code = QLineEdit()
        self.txt_join_code.setPlaceholderText("הדבק קוד הזמנה (NETFREE#...)")
        btn_join = QPushButton("⚡ הצטרף לפי קוד")
        btn_join.clicked.connect(self.on_join_by_code_clicked)
        row_code.addWidget(self.txt_join_code)
        row_code.addWidget(btn_join)
        j_layout.addLayout(row_code)

        row_role = QHBoxLayout()
        row_role.addWidget(QLabel("תפקיד:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "משחק מקוון – שחקן לבן (יוזם)",
            "משחק מקוון – שחקן שחור (מצטרף)",
            "מצב צופה (Spectator – צפייה בלבד)",
            "משחק מקומי (שני שחקנים על אותו מחשב)"
        ])
        self.combo_mode.setCurrentIndex(self.saved_mode)
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        row_role.addWidget(self.combo_mode)
        j_layout.addLayout(row_role)

        self.btn_manual_join = QPushButton("התחבר ידנית")
        self.btn_manual_join.clicked.connect(self.on_manual_connect_clicked)
        self.lbl_room_status = QLabel("מנותק")
        row_conn = QHBoxLayout()
        row_conn.addWidget(self.btn_manual_join)
        row_conn.addWidget(self.lbl_room_status)
        row_conn.addStretch()
        j_layout.addLayout(row_conn)

        layout.addWidget(j_box)
        layout.addStretch()

    def init_lobby_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        self.table_lobby = QTableWidget()
        self.table_lobby.setColumnCount(5)
        self.table_lobby.setHorizontalHeaderLabels(["חדר", "מארח", "בקרת זמן", "צבע", "שעה"])
        self.table_lobby.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_lobby.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table_lobby, stretch=1)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("🔄 רענן לובי דמקה")
        btn_refresh.clicked.connect(self.on_refresh_lobby_clicked)
        btn_join_sel = QPushButton("🎯 הצטרף למשחק הנבחר")
        btn_join_sel.clicked.connect(self.on_join_selected_lobby_game)
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_join_sel)
        layout.addLayout(btn_row)

    # ------------------ שעונים וניהול תור ------------------

    def setup_time_control(self, tc_text: str):
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
        if self.engine.is_game_over() or self.white_time_seconds is None or len(self.engine.history) == 0:
            return

        if self.engine.is_white_turn():
            self.white_time_seconds = max(0, self.white_time_seconds - 1)
            if self.white_time_seconds == 0:
                self.clock_timer.stop()
                QMessageBox.critical(self, "נגמר הזמן!", "נגמר הזמן ללבן! הניצחון לשחור!")
                self.record_game_end("opponent" if self.local_color == COLOR_WHITE else "local")
        else:
            self.black_time_seconds = max(0, self.black_time_seconds - 1)
            if self.black_time_seconds == 0:
                self.clock_timer.stop()
                QMessageBox.critical(self, "נגמר הזמן!", "נגמר הזמן לשחור! הניצחון ללבן!")
                self.record_game_end("opponent" if self.local_color == COLOR_BLACK else "local")

        self.update_clock_labels()

    def update_clock_labels(self):
        w_str = format_clock_time(self.white_time_seconds)
        b_str = format_clock_time(self.black_time_seconds)
        if self.board_widget.is_flipped:
            self.lbl_bottom_clock.setText(f"⏱️ {b_str}")
            self.lbl_top_clock.setText(f"⏱️ {w_str}")
        else:
            self.lbl_bottom_clock.setText(f"⏱️ {w_str}")
            self.lbl_top_clock.setText(f"⏱️ {b_str}")

    def update_game_status_display(self):
        status_text, is_over = self.engine.get_game_status_hebrew()
        is_white = self.engine.is_white_turn()
        move_num = len(self.engine.history) + 1
        self.lbl_extra_status.setText(f"מהלך {move_num} • {len(self.engine.history)} מסעים בוצעו")

        if is_over:
            self.lbl_turn_status.setText(status_text)
            self.lbl_turn_status.setStyleSheet("font-size: 17px; font-weight: bold; color: #D93025;")
            self.board_widget.interactive = False
            self.stop_polling()
            self.clock_timer.stop()
            return

        if self.is_spectator:
            self.board_widget.interactive = False
            self.lbl_turn_status.setText(f"מצב צופה (דמקה) – {status_text}")
            self.start_polling()
            return

        if not self.is_online or self.local_color is None:
            self.board_widget.interactive = True
            self.lbl_turn_status.setText(status_text)
        else:
            is_my_turn = (self.engine.turn == self.local_color)
            self.board_widget.interactive = is_my_turn
            if is_my_turn:
                self.lbl_turn_status.setText("תורך לשחק בדמקה!")
                self.lbl_turn_status.setStyleSheet("font-size: 17px; font-weight: bold; color: #137333;")
                self.start_polling(interval_ms=3000)
            else:
                self.lbl_turn_status.setText("ממתין למהלך היריב...")
                self.lbl_turn_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #E37400;")
                self.start_polling(interval_ms=1800)

    def update_score_display(self):
        mat = self.engine.calculate_material()
        w_txt = f"{mat['white_count']} כלים ({mat['white_kings']} דמקה)"
        b_txt = f"{mat['black_count']} כלים ({mat['black_kings']} דמקה)"

        if self.board_widget.is_flipped:
            self.lbl_bottom_name.setText(f"{self.player_name} (שחור)")
            self.lbl_top_name.setText(f"{self.opponent_name} (לבן)")
            self.lbl_bottom_pieces.setText(b_txt)
            self.lbl_top_pieces.setText(w_txt)
        else:
            self.lbl_bottom_name.setText(f"{self.player_name} (לבן)")
            self.lbl_top_name.setText(f"{self.opponent_name} (שחור)")
            self.lbl_bottom_pieces.setText(w_txt)
            self.lbl_top_pieces.setText(b_txt)

    def on_player_move_attempted(self, uci: str):
        color_code = "W" if self.engine.turn == COLOR_WHITE else "B"
        ok, san, err = self.engine.push_move(uci, self.player_name)
        if not ok:
            QMessageBox.warning(self, "מהלך לא חוקי", err)
            return

        sound_effects.play_capture_sound() if "x" in (san or "") else sound_effects.play_move_sound()
        self.update_score_display()
        self.update_game_status_display()
        self.update_history_table()

        if self.is_online and not self.is_spectator:
            sheet_id = self.txt_sheet_id.text().strip()
            move_num = len(self.engine.history)
            fen = self.engine.get_state_string()
            self.run_background_task(
                "send_move",
                sheet_id=sheet_id,
                room_id=self.game_id,
                move_num=move_num,
                player_name=self.player_name,
                color=color_code,
                move_uci=uci,
                move_san=san,
                fen=fen
            )

    def update_history_table(self):
        self.table_history.setRowCount(len(self.engine.history))
        for i, rec in enumerate(self.engine.history):
            move = rec.get("move")
            player = rec.get("player", "")
            turn_str = "לבן" if rec.get("turn") == COLOR_WHITE else "שחור"
            self.table_history.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.table_history.setItem(i, 1, QTableWidgetItem(f"{turn_str} ({player})"))
            self.table_history.setItem(i, 2, QTableWidgetItem(str(move)))
        self.table_history.scrollToBottom()

    # ------------------ דגימה מאוחדת ורשת ------------------

    def start_polling(self, interval_ms: int = 1800):
        if not self.is_online:
            return
        self.is_polling_active = True
        self.poll_timer.start(interval_ms)

    def stop_polling(self):
        self.is_polling_active = False
        self.poll_timer.stop()

    def poll_room_bundle(self):
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

    def run_background_task(self, task_type: str, **kwargs):
        if task_type == "poll_bundle":
            if self.is_polling_busy:
                return
            self.is_polling_busy = True

        worker = CheckersNetworkWorker(self.sync_mgr, task_type, **kwargs)
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

        elif task_type == "create_sheet":
            if success and data:
                new_id = data.get("id")
                self.txt_sheet_id.setText(new_id)
                save_config({"spreadsheet_id": new_id})
                self.update_invite_code_display()
                QMessageBox.information(self, "גיליון נוצר", f"נוצר גיליון חדש:\n{new_id}")

        elif task_type == "create_room":
            if success:
                self.lbl_room_status.setText(f"מארח דמקה {self.game_id} (לבן)")
                self.update_invite_code_display()
                self.tabs.setCurrentIndex(0)
                tc = self.combo_time_control.currentText()
                self.setup_time_control(tc)
                self.start_polling(1800)
                QMessageBox.information(self, "החדר נפתח", f"חדר דמקה {self.game_id} מוכן בגיליון!")

        elif task_type == "join_room":
            if success:
                info = data or {}
                h_name = info.get("host_name", "מארח")
                h_color = info.get("host_color", "W")
                tc = info.get("time_control", "NONE")
                self.opponent_name = h_name
                if not self.is_spectator:
                    if h_color == "W":
                        self.local_color = COLOR_BLACK
                        self.board_widget.set_player_color(COLOR_BLACK)
                    else:
                        self.local_color = COLOR_WHITE
                        self.board_widget.set_player_color(COLOR_WHITE)

                self.lbl_room_status.setText(f"מחובר לחדר {self.game_id}")
                self.setup_time_control(tc)
                self.tabs.setCurrentIndex(0)
                self.start_polling(1800)
                self.update_score_display()
                self.update_game_status_display()
                QMessageBox.information(self, "התחברת לחדר דמקה!", f"התחברת לחדר {self.game_id} מול {h_name}!")

        elif task_type == "fetch_lobby":
            if success and isinstance(data, list):
                self.populate_lobby_table(data)

    def process_poll_bundle_result(self, data: Dict[str, Any]):
        meta = data.get("meta", {})
        moves = data.get("moves", [])
        chat_msgs = data.get("chat", [])

        # 1. מטא
        if meta:
            guest = meta.get("guest_player", "")
            if guest and self.local_color == COLOR_WHITE and self.opponent_name != guest:
                self.opponent_name = guest
                self.update_score_display()

            action_status = meta.get("action_status", "NONE")
            opp_color_code = "B" if self.local_color == COLOR_WHITE else "W"
            if f"RESIGN_{opp_color_code}" in action_status:
                self.sync_mgr.update_action_status(self.txt_sheet_id.text().strip(), self.game_id, "NONE")
                sound_effects.play_game_end_sound(True)
                QMessageBox.information(self, "ניצחון בדמקה!", f"{self.opponent_name} נכנע!")
                self.record_game_end("local")
                return

        # 2. מהלכים
        if moves:
            for m in moves:
                uci = m.get("move_uci", "")
                p_name = m.get("player", "יריב")
                c_str = m.get("color", "")
                if not uci:
                    continue

                my_color_str = "W" if self.local_color == COLOR_WHITE else "B"
                is_opp = (c_str != my_color_str) if not self.is_spectator else True

                if is_opp:
                    self.opponent_name = p_name
                    ok, san, _ = self.engine.push_move(uci, p_name)
                    if ok:
                        sound_effects.play_capture_sound() if "x" in (san or "") else sound_effects.play_move_sound()
                        self.update_score_display()
                        self.update_game_status_display()
                        self.update_history_table()

        # 3. צ'אט
        if chat_msgs:
            played = False
            for c in chat_msgs:
                c_id = c.get("msg_id", 0)
                if c_id > self.last_chat_msg_id:
                    self.last_chat_msg_id = c_id
                    sender = c.get("sender", "")
                    if sender != self.player_name:
                        self.append_chat_message(c.get("timestamp", ""), sender, c.get("color", ""), c.get("text", ""))
                        played = True
            if played:
                sound_effects.play_chat_sound()

    # ------------------ צ'אט, חדרים ולובי ------------------

    def on_chat_enter_pressed(self):
        msg = self.txt_chat_input.text().strip()
        if msg:
            self.send_chat_message(msg)
            self.txt_chat_input.clear()

    def send_chat_message(self, text: str):
        if not self.is_online:
            self.append_chat_message(datetime.datetime.now().strftime("%H:%M:%S"), self.player_name, "מקומי", text)
            return
        sheet_id = self.txt_sheet_id.text().strip()
        if not sheet_id:
            return
        self.last_chat_msg_id += 1
        my_id = self.last_chat_msg_id
        c_str = "SPEC" if self.is_spectator else ("W" if self.local_color == COLOR_WHITE else "B")
        self.append_chat_message(datetime.datetime.now().strftime("%H:%M:%S"), self.player_name, c_str, text)
        self.run_background_task("send_chat", sheet_id=sheet_id, room_id=self.game_id, msg_id=my_id, sender=self.player_name, color=c_str, message=text)

    def append_chat_message(self, time_str: str, sender: str, color_tag: str, text: str):
        self.txt_chat_history.append(f"[{time_str}] <b>{sender}</b>: {text}")

    def generate_new_room_code(self):
        self.game_id = f"Checkers_{random.randint(1000, 9999)}"
        self.txt_game_id.setText(self.game_id)
        self.update_invite_code_display()

    def update_invite_code_display(self):
        s_id = self.txt_sheet_id.text().strip()
        r_id = self.txt_game_id.text().strip().upper()
        if s_id and r_id:
            code = encode_invite_code(s_id, r_id, game_type="CHECKERS")
            self.lbl_invite_code.setText(code)

    def copy_invite_code(self):
        c = self.lbl_invite_code.text().strip()
        if c:
            QApplication.clipboard().setText(c)
            QMessageBox.information(self, "הועתק", f"קוד ההזמנה הועתק ללוח:\n{c}")

    def update_auth_status_ui(self):
        logged_in = self.sheets_client.is_logged_in()
        if logged_in:
            self.lbl_auth_status.setText("🟢 מחובר ל-Google")
            self.lbl_auth_status.setStyleSheet("color: #34D399; font-weight: bold; background: #064E3B; border: 1px solid #059669; border-radius: 5px; padding: 4px 8px;")
            self.btn_auth_login.hide()
            self.btn_auth_logout.show()
        else:
            self.lbl_auth_status.setText("⚪ לא מחובר ל-Google")
            self.lbl_auth_status.setStyleSheet("color: #94A3B8; background: #1E293B; border: 1px solid #334155; border-radius: 5px; padding: 4px 8px;")
            self.btn_auth_login.show()
            self.btn_auth_logout.hide()

    def on_login_clicked(self):
        self.btn_auth_login.setEnabled(False)
        self.btn_auth_login.setText("מתחבר...")
        try:
            success, msg, _ = self.sheets_client.authenticate(prompt_browser=True)
            if success:
                QMessageBox.information(self, "התחברות הצליחה", "התחברת בהצלחה לחשבון Google!")
            else:
                QMessageBox.warning(self, "כשל בהתחברות", f"לא ניתן היה להתחבר:\n{msg}")
        except Exception as e:
            QMessageBox.critical(self, "שגיאה", f"תקלה בהתחברות:\n{e}")
        finally:
            self.btn_auth_login.setEnabled(True)
            self.btn_auth_login.setText("🔑 התחבר ל-Google")
            self.update_auth_status_ui()

    def on_logout_clicked(self):
        reply = QMessageBox.question(
            self, "התנתקות מחשבון Google",
            "האם ברצונך להתנתק מחשבון Google הנוכחי?\n(הפעולה תמחק את הטוקן המקומי ותאפשר לך להתחבר עם חשבון אחר)",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.sheets_client.logout()
            self.update_auth_status_ui()
            QMessageBox.information(self, "התנתקת בהצלחה", "ההתנתקות הושלמה בהצלחה.")

    def on_create_new_sheet_clicked(self):
        if not self.sheets_client.is_logged_in():
            success, msg, _ = self.sheets_client.authenticate(prompt_browser=True)
            self.update_auth_status_ui()
            if not success:
                QMessageBox.critical(self, "כשל בהתחברות Google", msg)
                return
        self.run_background_task("create_sheet", title="משחקי לוח מקוונים בנטפרי")

    def on_host_create_room_clicked(self):
        try:
            sheet_id = extract_spreadsheet_id(self.txt_sheet_id.text().strip())
            if not sheet_id:
                QMessageBox.warning(self, "חסר גיליון", "נא להזין מזהה Google Sheet.")
                return

            r_id = self.txt_game_id.text().strip().upper()
            if not r_id:
                r_id = f"CHECKERS_{random.randint(1000, 9999)}"
                self.txt_game_id.setText(r_id)
            self.game_id = r_id

            self.is_online = True
            self.is_spectator = False
            self.local_color = COLOR_WHITE
            self.board_widget.set_player_color(COLOR_WHITE)
            tc = self.combo_time_control.currentText()
            pub = self.chk_publish_lobby.isChecked()
            self.run_background_task("create_room", sheet_id=sheet_id, room_id=self.game_id, host_name=self.player_name, host_color="W", time_control=tc, publish_lobby=pub)
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בפתיחת חדר", f"אירעה שגיאה:\n{e}")

    def on_join_by_code_clicked(self):
        raw = self.txt_join_code.text().strip()
        if not raw:
            return
        sheet_id, room_id, g_type = decode_invite_code(raw)
        if not sheet_id:
            sheet_id = self.txt_sheet_id.text().strip()
            room_id = raw.upper()
        self.txt_sheet_id.setText(sheet_id)
        self.txt_game_id.setText(room_id)
        self.game_id = room_id
        self.is_online = True
        self.is_spectator = (self.combo_mode.currentIndex() == 2)
        self.run_background_task("join_room", sheet_id=sheet_id, room_id=room_id, guest_name=self.player_name)

    def on_manual_connect_clicked(self):
        idx = self.combo_mode.currentIndex()
        sheet_id = self.txt_sheet_id.text().strip()
        self.game_id = self.txt_game_id.text().strip().upper()
        if idx in (0, 1, 2):
            self.is_online = True
            if idx == 0:
                self.local_color = COLOR_WHITE
                self.board_widget.set_player_color(COLOR_WHITE)
            elif idx == 1:
                self.local_color = COLOR_BLACK
                self.board_widget.set_player_color(COLOR_BLACK)
            else:
                self.is_spectator = True
            self.run_background_task("join_room", sheet_id=sheet_id, room_id=self.game_id, guest_name=self.player_name)
        else:
            self.is_online = False
            self.board_widget.set_player_color(None)
            self.lbl_room_status.setText("משחק מקומי")
            self.stop_polling()

    def on_mode_changed(self, idx: int):
        save_config({"mode_index": idx})
        if idx == 0:
            self.is_online = True
            self.local_color = COLOR_WHITE
            self.board_widget.set_player_color(COLOR_WHITE)
        elif idx == 1:
            self.is_online = True
            self.local_color = COLOR_BLACK
            self.board_widget.set_player_color(COLOR_BLACK)
        elif idx == 2:
            self.is_online = True
            self.is_spectator = True
        else:
            self.is_online = False
            self.board_widget.set_player_color(None)
            self.stop_polling()
        self.update_score_display()
        self.update_game_status_display()

    def on_refresh_lobby_clicked(self):
        sheet_id = self.txt_sheet_id.text().strip()
        if sheet_id:
            self.run_background_task("fetch_lobby", sheet_id=sheet_id)

    def populate_lobby_table(self, games: List[Dict[str, Any]]):
        self.table_lobby.setRowCount(len(games))
        for row_idx, g in enumerate(games):
            self.table_lobby.setItem(row_idx, 0, QTableWidgetItem(g.get("room_id", "")))
            self.table_lobby.setItem(row_idx, 1, QTableWidgetItem(g.get("host_name", "")))
            self.table_lobby.setItem(row_idx, 2, QTableWidgetItem(g.get("time_control", "")))
            self.table_lobby.setItem(row_idx, 3, QTableWidgetItem("לבן" if g.get("host_color") == "W" else "שחור"))
            self.table_lobby.setItem(row_idx, 4, QTableWidgetItem(g.get("created_at", "")))

    def on_join_selected_lobby_game(self):
        row = self.table_lobby.currentRow()
        if row >= 0:
            r_id = self.table_lobby.item(row, 0).text()
            s_id = self.txt_sheet_id.text().strip()
            self.game_id = r_id
            self.txt_game_id.setText(r_id)
            self.is_online = True
            self.run_background_task("join_room", sheet_id=s_id, room_id=r_id, guest_name=self.player_name)

    def on_resign_clicked(self):
        res = QMessageBox.question(self, "כניעה", "האם להיכנע במשחק הדמקה?")
        if res == QMessageBox.Yes:
            if self.is_online:
                c_str = "W" if self.local_color == COLOR_WHITE else "B"
                self.run_background_task("send_action", sheet_id=self.txt_sheet_id.text().strip(), room_id=self.game_id, player_name=self.player_name, color=c_str, action="RESIGN")
            self.record_game_end("opponent")

    def on_draw_clicked(self):
        if self.is_online:
            c_str = "W" if self.local_color == COLOR_WHITE else "B"
            self.run_background_task("send_action", sheet_id=self.txt_sheet_id.text().strip(), room_id=self.game_id, player_name=self.player_name, color=c_str, action="DRAW_OFFER")
            QMessageBox.information(self, "תיקו", "הצעת תיקו נשלחה.")
        else:
            self.record_game_end("draw")

    def on_takeback_clicked(self):
        if not self.engine.history:
            return
        if not self.is_online:
            self.engine.pop_last_move()
            self.update_score_display()
            self.update_game_status_display()
            self.update_history_table()
            return
        c_str = "W" if self.local_color == COLOR_WHITE else "B"
        self.run_background_task("send_action", sheet_id=self.txt_sheet_id.text().strip(), room_id=self.game_id, player_name=self.player_name, color=c_str, action="TAKEBACK_REQ_1")

    def record_game_end(self, winner: str):
        self.clock_timer.stop()
        if winner == "local":
            if self.local_color == COLOR_WHITE:
                self.score_white += 1
            else:
                self.score_black += 1
        elif winner == "opponent":
            if self.local_color == COLOR_WHITE:
                self.score_black += 1
            else:
                self.score_white += 1
        elif winner == "draw":
            self.score_draws += 1
        self.lbl_session_score.setText(f"ניקוד סשן: לבן {self.score_white} | שחור {self.score_black} | תיקו {self.score_draws}")
        self.stop_polling()
        self.board_widget.interactive = False

    def on_new_game_clicked(self):
        self.engine.reset()
        self.board_widget.clear_selection()
        self.update_score_display()
        self.update_game_status_display()
        self.update_history_table()
        tc = self.combo_time_control.currentText()
        self.setup_time_control(tc)


def run_checkers():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    win = CheckersMainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    run_checkers()
