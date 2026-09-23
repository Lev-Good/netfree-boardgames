# -*- coding: utf-8 -*-
"""
חלון משחק שש-בש מקוון בנטפרי - כולל סנכרון מקוון דרך Google Sheets API,
לוח עץ אותנטי, הטלת קוביות תלת-ממדיות, כניסה מהמשקוף (Bar), אכילת כלים (Blot),
הוצאת כלים (Bearing Off), זיהוי מארס ומארס טורקי, צ'אט חי, שעונים דיגיטליים וקוד הזמנה חכם.
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

from backgammon_engine import (
    BackgammonEngine, BackgammonMove, COLOR_WHITE, COLOR_BLACK, POINT_BAR, POINT_OFF
)
from backgammon_board_widget import BackgammonBoardWidget
from chess_sync import ChessSyncManager, encode_invite_code, decode_invite_code
from chess_engine import format_clock_time
from google_sheets_client import GoogleSheetsClient, extract_spreadsheet_id, load_config, save_config, setup_netfree_ca_bundle
from theme_style import get_gaming_stylesheet
import sound_effects


class BackgammonNetworkWorker(QThread):
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
                        game_type="BACKGAMMON"
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
                    game_type_filter="BACKGAMMON"
                )
                self.finished_task.emit("fetch_lobby", success, games, err)

            elif self.task_type == "create_sheet":
                success, sheet_id, sheet_url = self.sync_mgr.client.create_new_spreadsheet(
                    title=self.kwargs.get("title", "משחקי שש-בש ושחמט בנטפרי")
                )
                self.finished_task.emit("create_sheet", success, {"id": sheet_id, "url": sheet_url}, "" if success else sheet_id)

        except Exception as e:
            self.finished_task.emit(self.task_type, False, None, str(e))


class BackgammonMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = BackgammonEngine()
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

        self.game_id = cfg.get("backgammon_game_id") or f"Backgammon_{random.randint(1000, 9999)}"
        self.player_name = cfg.get("player_name") or f"שחקן#{random.randint(100, 999)}"
        self.spreadsheet_id = cfg.get("spreadsheet_id") or ""

        self.white_time_left = 600.0
        self.black_time_left = 600.0
        self.time_control_mode = "10_MIN"
        self.clock_running = False

        self.last_synced_move_num = 0
        self.last_synced_msg_id = 0
        self.active_workers: List[BackgammonNetworkWorker] = []

        self.init_ui()
        self.init_timers()
        self.update_status_display()
        self.check_netfree_ca()
        self.update_auth_status_ui()

    def check_netfree_ca(self):
        try:
            bundle_path = setup_netfree_ca_bundle()
            if os.path.exists(bundle_path):
                self.netfree_badge.setText("🛡️ נטפרי פעיל ומאובטח")
                self.netfree_badge.setStyleSheet("color: #4CAF50; font-weight: bold; background: #E8F5E9; border-radius: 4px; padding: 2px 6px;")
            else:
                self.netfree_badge.setText("🌐 אינטרנט רגיל")
                self.netfree_badge.setStyleSheet("color: #757575; background: #EEEEEE; border-radius: 4px; padding: 2px 6px;")
        except Exception:
            self.netfree_badge.setText("🌐 אינטרנט רגיל")
            self.netfree_badge.setStyleSheet("color: #757575; background: #EEEEEE; border-radius: 4px; padding: 2px 6px;")

    def init_ui(self):
        self.setWindowTitle("שש-בש מקוון בנטפרי – Gaming HUD Online")
        self.resize(1120, 780)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(get_gaming_stylesheet())

        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # ---------------- עמודה ימנית: לוח שש-בש ושעונים ----------------
        board_col = QVBoxLayout()
        board_col.setSpacing(8)

        # שעון עליון (שחור)
        self.black_clock_frame = self._create_clock_widget("שחקן שחור", "10:00", "#333333")
        board_col.addWidget(self.black_clock_frame)

        # לוח השש-בש האינטראקטיבי
        self.board_widget = BackgammonBoardWidget(self.engine)
        self.board_widget.set_player_color(self.local_color)
        self.board_widget.move_attempted.connect(self.on_board_move_attempted)
        self.board_widget.dice_roll_requested.connect(self.on_roll_dice_clicked)
        board_col.addWidget(self.board_widget, stretch=1)

        # שעון תחתון (לבן)
        self.white_clock_frame = self._create_clock_widget("שחקן לבן", "10:00", "#FFFFFF")
        board_col.addWidget(self.white_clock_frame)

        # שורת פעולות לוח: כפתור הטלת קוביות גדול ומבצע
        dice_bar = QHBoxLayout()
        self.roll_dice_btn = QPushButton("🎲 הטל קוביות (גלגל עכשיו!)")
        self.roll_dice_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #D97706, stop:1 #F59E0B);
                color: white;
                font-size: 15px;
                font-weight: bold;
                padding: 10px 18px;
                border-radius: 8px;
                border: 1px solid #FBBF24;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #B45309, stop:1 #FBBF24); }
            QPushButton:disabled { background: #1E293B; color: #64748B; border: 1px solid #334155; }
        """)
        self.roll_dice_btn.clicked.connect(self.on_roll_dice_clicked)
        dice_bar.addWidget(self.roll_dice_btn, stretch=2)

        self.pass_turn_btn = QPushButton("העבר תור (אין מסע אפשרי)")
        self.pass_turn_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                font-size: 12px;
                padding: 8px 12px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #78909C; }
            QPushButton:disabled { background-color: #CFD8DC; color: #90A4AE; }
        """)
        self.pass_turn_btn.setEnabled(False)
        self.pass_turn_btn.clicked.connect(self.on_pass_turn_clicked)
        dice_bar.addWidget(self.pass_turn_btn, stretch=1)
        board_col.addLayout(dice_bar)

        # סרגל פעולות משחק: כניעה, החזרת מהלך, משחק חדש
        actions_bar = QHBoxLayout()
        self.btn_takeback = QPushButton("↩️ בקש החזרת מסע")
        self.btn_takeback.clicked.connect(self.on_takeback_clicked)
        actions_bar.addWidget(self.btn_takeback)

        self.btn_resign = QPushButton("🏳️ היכנע")
        self.btn_resign.clicked.connect(self.on_resign_clicked)
        actions_bar.addWidget(self.btn_resign)

        self.btn_new_game = QPushButton("🔄 משחק חדש")
        self.btn_new_game.clicked.connect(self.on_new_game_clicked)
        actions_bar.addWidget(self.btn_new_game)

        board_col.addLayout(actions_bar)

        # שורת סטטוס משחק והתרעות נטפרי
        status_bar = QHBoxLayout()
        self.lbl_game_status = QLabel("מוכן למשחק שש-בש")
        self.lbl_game_status.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.lbl_game_status.setStyleSheet("color: #2E7D32;")
        status_bar.addWidget(self.lbl_game_status, stretch=1)

        self.netfree_badge = QLabel("🛡️ בדיקת נטפרי...")
        status_bar.addWidget(self.netfree_badge)
        board_col.addLayout(status_bar)

        main_layout.addLayout(board_col, stretch=6)

        # ---------------- עמודה שמאלית: לשוניות חדרים, צ'אט, מהלכים ----------------
        control_col = QVBoxLayout()
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.RightToLeft)

        # 1. לשונית ניהול חדר וחיבור מקוון
        tab_room = QWidget()
        tab_room_layout = QVBoxLayout(tab_room)
        self._init_room_tab(tab_room_layout)
        self.tabs.addTab(tab_room, "🌐 חדר והתחברות")

        # 2. לשונית היסטוריית מהלכים
        tab_moves = QWidget()
        tab_moves_layout = QVBoxLayout(tab_moves)
        self._init_moves_tab(tab_moves_layout)
        self.tabs.addTab(tab_moves, "📜 מסעים וקוביות")

        # 3. לשונית צ'אט חי
        tab_chat = QWidget()
        tab_chat_layout = QVBoxLayout(tab_chat)
        self._init_chat_tab(tab_chat_layout)
        self.tabs.addTab(tab_chat, "💬 צ'אט חי")

        # 4. לשונית רשימת חדרים (Lobby)
        tab_lobby = QWidget()
        tab_lobby_layout = QVBoxLayout(tab_lobby)
        self._init_lobby_tab(tab_lobby_layout)
        self.tabs.addTab(tab_lobby, "📋 לובי חדרים")

        control_col.addWidget(self.tabs)
        main_layout.addLayout(control_col, stretch=4)

        self.setCentralWidget(main_widget)

    def _create_clock_widget(self, title: str, default_time: str, text_color: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #161F2E;
                border-radius: 8px;
                border: 1.5px solid #2B374E;
                padding: 4px;
            }
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 4, 12, 4)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #F8FAFC; font-weight: bold; font-size: 13px;")
        layout.addWidget(lbl_title)

        lbl_time = QLabel(default_time)
        lbl_time.setFont(QFont("Consolas", 18, QFont.Bold))
        lbl_time.setStyleSheet("color: #38BDF8; background-color: #0B0E14; border: 1.5px solid #1E293B; border-radius: 6px; padding: 3px 12px;")
        layout.addWidget(lbl_time, alignment=Qt.AlignLeft)

        if "שחור" in title:
            self.lbl_black_time = lbl_time
            self.lbl_black_title = lbl_title
        else:
            self.lbl_white_time = lbl_time
            self.lbl_white_title = lbl_title

        return frame

    def _init_room_tab(self, layout: QVBoxLayout):
        grp_settings = QGroupBox("הגדרות שחקן וחיבור")
        f_layout = QVBoxLayout(grp_settings)

        h_name = QHBoxLayout()
        h_name.addWidget(QLabel("כינוי:"))
        self.txt_player_name = QLineEdit(self.player_name)
        self.txt_player_name.textChanged.connect(self._on_player_name_changed)
        h_name.addWidget(self.txt_player_name)
        f_layout.addLayout(h_name)

        h_mode = QHBoxLayout()
        h_mode.addWidget(QLabel("מצב משחק:"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["מקוון - שחקן לבן (יוצר)", "מקוון - שחקן שחור (מצטרף)", "מקוון - צופה", "מקומי - שני שחקנים במחשב זה"])
        self.cmb_mode.setCurrentIndex(self.saved_mode)
        self.cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        h_mode.addWidget(self.cmb_mode)
        f_layout.addLayout(h_mode)

        h_time = QHBoxLayout()
        h_time.addWidget(QLabel("שעון:"))
        self.cmb_time_control = QComboBox()
        self.cmb_time_control.addItems(["10 דקות לשחקן", "5 דקות (בליץ)", "15 דקות", "ללא הגבלת זמן"])
        self.cmb_time_control.currentIndexChanged.connect(self._on_time_control_changed)
        h_time.addWidget(self.cmb_time_control)
        f_layout.addLayout(h_time)

        layout.addWidget(grp_settings)

        # קוד הזמנה חכם
        grp_invite = QGroupBox("קוד הזמנה חכם (Smart Invite Code)")
        inv_layout = QVBoxLayout(grp_invite)

        self.txt_smart_invite = QLineEdit()
        self.txt_smart_invite.setPlaceholderText("הדבק קוד הזמנה שהתקבל מחבר...")
        inv_layout.addWidget(self.txt_smart_invite)

        h_inv_btns = QHBoxLayout()
        self.btn_copy_invite = QPushButton("📋 העתק קוד לשיתוף")
        self.btn_copy_invite.clicked.connect(self.on_copy_invite_clicked)
        h_inv_btns.addWidget(self.btn_copy_invite)

        self.btn_join_invite = QPushButton("🚀 הצטרף עם קוד זה")
        self.btn_join_invite.clicked.connect(self.on_join_smart_invite_clicked)
        h_inv_btns.addWidget(self.btn_join_invite)
        inv_layout.addLayout(h_inv_btns)

        layout.addWidget(grp_invite)

        # יצירת חדר או גליון חדש
        grp_cloud = QGroupBox("Google Sheets API (ניהול חשבון וגליונות)")
        cloud_layout = QVBoxLayout(grp_cloud)

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

        cloud_layout.addLayout(row_auth)

        h_sheet = QHBoxLayout()
        h_sheet.addWidget(QLabel("ID גליון:"))
        self.txt_sheet_id = QLineEdit(self.spreadsheet_id)
        self.txt_sheet_id.setPlaceholderText("מזהה ה-Spreadsheet...")
        self.txt_sheet_id.textChanged.connect(self._on_sheet_id_changed)
        h_sheet.addWidget(self.txt_sheet_id)
        cloud_layout.addLayout(h_sheet)

        h_room = QHBoxLayout()
        h_room.addWidget(QLabel("שם חדר:"))
        self.txt_room_id = QLineEdit(self.game_id)
        self.txt_room_id.textChanged.connect(self._on_room_id_changed)
        h_room.addWidget(self.txt_room_id)
        cloud_layout.addLayout(h_room)

        self.chk_publish_lobby = QCheckBox("פרסם חדר זה בלובי הציבורי")
        self.chk_publish_lobby.setChecked(True)
        cloud_layout.addWidget(self.chk_publish_lobby)

        h_cloud_btns = QHBoxLayout()
        self.btn_create_room = QPushButton("✨ צור חדר בשיטס")
        self.btn_create_room.clicked.connect(self.on_create_room_clicked)
        h_cloud_btns.addWidget(self.btn_create_room)

        self.btn_new_sheet = QPushButton("📄 צור גליון שיטס חדש")
        self.btn_new_sheet.clicked.connect(self.on_create_sheet_clicked)
        h_cloud_btns.addWidget(self.btn_new_sheet)
        cloud_layout.addLayout(h_cloud_btns)

        layout.addWidget(grp_cloud)
        layout.addStretch()

    def _init_moves_tab(self, layout: QVBoxLayout):
        self.table_moves = QTableWidget(0, 3)
        self.table_moves.setHorizontalHeaderLabels(["#", "שחקן", "מסע"])
        self.table_moves.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_moves.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table_moves)

    def _init_chat_tab(self, layout: QVBoxLayout):
        self.txt_chat_history = QTextEdit()
        self.txt_chat_history.setReadOnly(True)
        layout.addWidget(self.txt_chat_history)

        h_quick = QHBoxLayout()
        for q_msg in ["שלום! 👋", "בהצלחה!", "שש בש! 🎲", "מארס!", "משחק מצוין!"]:
            btn = QPushButton(q_msg)
            btn.setStyleSheet("font-size: 11px; padding: 3px 6px;")
            btn.clicked.connect(lambda _, m=q_msg: self.send_chat_message(m))
            h_quick.addWidget(btn)
        layout.addLayout(h_quick)

        h_input = QHBoxLayout()
        self.txt_chat_input = QLineEdit()
        self.txt_chat_input.setPlaceholderText("כתוב הודעה בצ'אט...")
        self.txt_chat_input.returnPressed.connect(self.on_send_chat_clicked)
        h_input.addWidget(self.txt_chat_input)

        self.btn_send_chat = QPushButton("שלח")
        self.btn_send_chat.clicked.connect(self.on_send_chat_clicked)
        h_input.addWidget(self.btn_send_chat)
        layout.addLayout(h_input)

    def _init_lobby_tab(self, layout: QVBoxLayout):
        h_bar = QHBoxLayout()
        self.btn_refresh_lobby = QPushButton("🔄 רענן רשימת חדרים")
        self.btn_refresh_lobby.clicked.connect(self.on_refresh_lobby_clicked)
        h_bar.addWidget(self.btn_refresh_lobby)
        layout.addLayout(h_bar)

        self.table_lobby = QTableWidget(0, 4)
        self.table_lobby.setHorizontalHeaderLabels(["שם חדר", "מארח", "זמן", "פעולה"])
        self.table_lobby.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_lobby.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table_lobby)

    def init_timers(self):
        # טיימר שעון משחק
        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self.on_clock_tick)
        self.clock_timer.start()

        # טיימר סנכרון מקוון (Polling) כל 1.8 שניות
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1800)
        self.poll_timer.timeout.connect(self.on_poll_timer)
        if self.is_online:
            self.poll_timer.start()

    def update_status_display(self):
        status_txt, is_over, win_pts = self.engine.get_game_status_hebrew()
        self.lbl_game_status.setText(status_txt)

        if is_over:
            self.clock_running = False
            self.roll_dice_btn.setEnabled(False)
            self.pass_turn_btn.setEnabled(False)
        else:
            can_roll = (len(self.engine.remaining_moves) == 0)
            is_my_turn = (self.local_color is None or self.engine.turn == self.local_color)
            self.roll_dice_btn.setEnabled(can_roll and is_my_turn and not self.is_spectator)

            # בדיקה האם יש מהלכים אפשריים אם נזרקו קוביות
            has_moves = len(self.engine.get_legal_moves()) > 0
            if not can_roll and not has_moves and is_my_turn and not self.is_spectator:
                self.pass_turn_btn.setEnabled(True)
                self.lbl_game_status.setText(f"{status_txt} (אין מסעים אפשריים - לחץ העבר תור)")
            else:
                self.pass_turn_btn.setEnabled(False)

        self.board_widget.update()
        self.update_invite_code_display()

    def update_invite_code_display(self):
        if self.spreadsheet_id and self.game_id:
            code = encode_invite_code(self.spreadsheet_id, self.game_id, "BACKGAMMON")
            self.txt_smart_invite.setText(code)

    def on_roll_dice_clicked(self):
        """לחיצה על הטלת קוביות"""
        if self.engine.is_game_over():
            return
        if self.is_online and not self.is_spectator and self.local_color is not None:
            if self.engine.turn != self.local_color:
                QMessageBox.information(self, "לא תורך", "המתן לתור השחקן השני להטיל קוביות.")
                return

        dice = self.engine.roll_dice()
        sound_effects.play_dice_sound()
        self.clock_running = True

        move_san = f"🎲 הטלת קוביות: {dice[0]}, {dice[1]}"
        if dice[0] == dice[1]:
            move_san += f" (דאבל! 4 מהלכים של {dice[0]})"

        self._record_move_in_table(self.player_name, move_san)
        self.update_status_display()

        # סנכרון הטלת קוביות בשיטס
        if self.is_online and self.spreadsheet_id:
            move_num = len(self.engine.history) + 1
            c_str = "W" if self.engine.turn == COLOR_WHITE else "B"
            self._start_worker("send_move",
                sheet_id=self.spreadsheet_id,
                room_id=self.game_id,
                move_num=move_num,
                player_name=self.player_name,
                color=c_str,
                move_uci=f"ROLL:{dice[0]},{dice[1]}",
                move_san=move_san,
                fen=self.engine.get_state_string(),
                action="ROLL"
            )

    def on_pass_turn_clicked(self):
        """העברת תור כאשר אין מהלכים חוקיים"""
        if self.engine.is_game_over():
            return
        self.engine.end_turn()
        self._record_move_in_table(self.player_name, "העברת תור (חסום)")
        self.update_status_display()

        if self.is_online and self.spreadsheet_id:
            move_num = len(self.engine.history) + 1
            c_str = "W" if self.engine.turn == COLOR_BLACK else "B"
            self._start_worker("send_move",
                sheet_id=self.spreadsheet_id,
                room_id=self.game_id,
                move_num=move_num,
                player_name=self.player_name,
                color=c_str,
                move_uci="PASS",
                move_san="העברת תור",
                fen=self.engine.get_state_string(),
                action="PASS"
            )

    def on_board_move_attempted(self, move: BackgammonMove):
        """ביצוע מהלך מהלוח"""
        if self.engine.is_game_over():
            return
        if self.is_online and not self.is_spectator and self.local_color is not None:
            if self.engine.turn != self.local_color:
                QMessageBox.information(self, "לא תורך", "המתן לתורך!")
                return

        prev_turn = self.engine.turn
        success, desc, err = self.engine.push_move(move, self.player_name)
        if not success:
            QMessageBox.warning(self, "מהלך לא חוקי", err or "מסע בלתי חוקי בשש-בש!")
            return

        if move.is_hit:
            sound_effects.play_capture_sound()
        else:
            sound_effects.play_move_sound()

        self._record_move_in_table(self.player_name, desc or str(move))
        self.update_status_display()

        # סנכרון מהלך לשיטס
        if self.is_online and self.spreadsheet_id:
            move_num = len(self.engine.history)
            c_str = "W" if prev_turn == COLOR_WHITE else "B"
            self._start_worker("send_move",
                sheet_id=self.spreadsheet_id,
                room_id=self.game_id,
                move_num=move_num,
                player_name=self.player_name,
                color=c_str,
                move_uci=move.to_uci(),
                move_san=desc or str(move),
                fen=self.engine.get_state_string(),
                action="MOVE"
            )

        if self.engine.is_game_over():
            status, _, _ = self.engine.get_game_status_hebrew()
            sound_effects.play_game_end_sound(won=True)
            QMessageBox.information(self, "המשחק הסתיים!", status)

    def _record_move_in_table(self, player: str, desc: str):
        row = self.table_moves.rowCount()
        self.table_moves.insertRow(row)
        self.table_moves.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.table_moves.setItem(row, 1, QTableWidgetItem(player))
        self.table_moves.setItem(row, 2, QTableWidgetItem(desc))
        self.table_moves.scrollToBottom()

    def on_clock_tick(self):
        if not self.clock_running or self.engine.is_game_over() or len(self.engine.history) == 0:
            return

        if self.engine.turn == COLOR_WHITE:
            self.white_time_left = max(0.0, self.white_time_left - 1.0)
            self.lbl_white_time.setText(format_clock_time(self.white_time_left))
            if self.white_time_left <= 0:
                self.clock_running = False
                sound_effects.play_game_end_sound(won=False)
                QMessageBox.information(self, "נגמר הזמן!", "זמנו של השחקן הלבן אזל! השחור מנצח בזמן.")
        else:
            self.black_time_left = max(0.0, self.black_time_left - 1.0)
            self.lbl_black_time.setText(format_clock_time(self.black_time_left))
            if self.black_time_left <= 0:
                self.clock_running = False
                sound_effects.play_game_end_sound(won=False)
                QMessageBox.information(self, "נגמר הזמן!", "זמנו של השחקן השחור אזל! הלבן מנצח בזמן.")

    def on_poll_timer(self):
        if not self.is_online or not self.spreadsheet_id or not self.game_id:
            return
        self._start_worker("poll_bundle",
            sheet_id=self.spreadsheet_id,
            room_id=self.game_id,
            after_move_num=self.last_synced_move_num,
            after_msg_id=self.last_synced_msg_id
        )

    def on_network_task_finished(self, task_type: str, success: bool, data: Any, err: str):
        if not success:
            if task_type in ("create_room", "join_room", "create_sheet"):
                QMessageBox.warning(self, "שגיאת רשת / נטפרי", f"הפעולה נכשלה:\n{err}")
            return

        if task_type == "poll_bundle" and data:
            moves = data.get("moves", [])
            chats = data.get("chats", [])
            actions = data.get("actions", [])

            # עיבוד מהלכים והטלות קוביות
            for m in moves:
                m_num = int(m.get("move_num", 0))
                if m_num > self.last_synced_move_num:
                    self.last_synced_move_num = m_num
                    p_name = m.get("player_name", "")
                    c_str = m.get("color", "")
                    m_uci = m.get("move_uci", "")
                    m_san = m.get("move_san", "")
                    fen = m.get("fen", "")

                    my_color_str = "W" if self.local_color == COLOR_WHITE else "B"
                    # אם המהלך בוצע על ידי היריב או שאנחנו צופים
                    if self.is_spectator or c_str != my_color_str:
                        if m_uci.startswith("ROLL:"):
                            parts = m_uci.split(":")[1].split(",")
                            d1, d2 = int(parts[0]), int(parts[1])
                            self.engine.roll_dice(d1, d2)
                            sound_effects.play_dice_sound()
                            self._record_move_in_table(p_name, m_san)
                        elif m_uci == "PASS":
                            self.engine.end_turn()
                            self._record_move_in_table(p_name, m_san)
                        else:
                            # טעינת מצב לוח מלא מ-FEN של שש-בש
                            if fen:
                                self.engine.load_from_state_string(fen)
                            if "*" in m_san:
                                sound_effects.play_capture_sound()
                            else:
                                sound_effects.play_move_sound()
                            self._record_move_in_table(p_name, m_san)

                        self.clock_running = True
                        self.update_status_display()

            # עיבוד צ'אט
            for c in chats:
                c_id = int(c.get("msg_id", 0))
                if c_id > self.last_synced_msg_id:
                    self.last_synced_msg_id = c_id
                    sender = c.get("sender", "שחקן")
                    msg = c.get("message", "")
                    self._append_chat(sender, msg)
                    if sender != self.player_name:
                        sound_effects.play_chat_sound()

            # עיבוד פעולות מיוחדות (כניעה, תיקו, ביטול מהלך)
            for a in actions:
                act = a.get("action", "")
                p_name = a.get("player_name", "")
                c_str = a.get("color", "")
                my_color_str = "W" if self.local_color == COLOR_WHITE else "B"

                if act == "RESIGN" and c_str != my_color_str:
                    QMessageBox.information(self, "כניעה", f"{p_name} נכנע. ניצחת במשחק!")
                    self.clock_running = False
                elif act == "TAKEBACK_REQUEST" and c_str != my_color_str:
                    res = QMessageBox.question(self, "בקשת החזרת מסע", f"{p_name} מבקש לבטל את מסעו האחרון. האם לאשר?", QMessageBox.Yes | QMessageBox.No)
                    if res == QMessageBox.Yes:
                        self.engine.pop_last_move()
                        self.sync_mgr.remove_last_moves(self.spreadsheet_id, self.game_id, 1)
                        self._start_worker("send_action", sheet_id=self.spreadsheet_id, room_id=self.game_id, player_name=self.player_name, color=my_color_str, action="TAKEBACK_ACCEPT")
                        self.update_status_display()
                    else:
                        self._start_worker("send_action", sheet_id=self.spreadsheet_id, room_id=self.game_id, player_name=self.player_name, color=my_color_str, action="TAKEBACK_DECLINE")
                elif act == "TAKEBACK_ACCEPT":
                    self.engine.pop_last_move()
                    self.update_status_display()
                    QMessageBox.information(self, "החזרת מסע", "בקשתך התקבלה! המסע האחרון בוטל.")
                elif act == "TAKEBACK_DECLINE":
                    QMessageBox.information(self, "החזרת מסע", "היריב דחה את בקשת החזרת המסע.")

        elif task_type == "create_room":
            QMessageBox.information(self, "חדר נוצר", f"החדר '{self.game_id}' נוצר בהצלחה בגליון!\nקוד ההזמנה מוכן להעתקה.")
            self.update_invite_code_display()

        elif task_type == "join_room":
            QMessageBox.information(self, "הצטרפות הצליחה", f"התחברת בהצלחה לחדר {self.game_id}!")
            self.last_synced_move_num = 0
            self.on_poll_timer()

        elif task_type == "create_sheet":
            sheet_id = data.get("id")
            self.txt_sheet_id.setText(sheet_id)
            self.spreadsheet_id = sheet_id
            QMessageBox.information(self, "גליון נוצר", f"נוצר גליון גוגל חדש ייעודי למשחקים!\nID: {sheet_id}")

        elif task_type == "fetch_lobby":
            self._update_lobby_table(data or [])

    def on_copy_invite_clicked(self):
        code = self.txt_smart_invite.text().strip()
        if not code:
            code = encode_invite_code(self.spreadsheet_id, self.game_id, "BACKGAMMON")
            self.txt_smart_invite.setText(code)
        QApplication.clipboard().setText(code)
        QMessageBox.information(self, "הועתק", "קוד ההזמנה החכם הועתק ללוח! שלח אותו ליריב שלך.")

    def on_join_smart_invite_clicked(self):
        code = self.txt_smart_invite.text().strip()
        sheet_id, room_id, g_type = decode_invite_code(code)
        if not sheet_id or not room_id:
            QMessageBox.warning(self, "קוד שגוי", "קוד ההזמנה אינו תקין.")
            return

        self.spreadsheet_id = sheet_id
        self.game_id = room_id
        self.txt_sheet_id.setText(sheet_id)
        self.txt_room_id.setText(room_id)
        self.cmb_mode.setCurrentIndex(1)  # שחור (מצטרף)
        self.local_color = COLOR_BLACK
        self.board_widget.set_player_color(COLOR_BLACK)

        self._start_worker("join_room", sheet_id=sheet_id, room_id=room_id, guest_name=self.player_name)

    def on_create_room_clicked(self):
        try:
            sheet_id = extract_spreadsheet_id(self.spreadsheet_id or self.txt_sheet_id.text().strip())
            if not sheet_id:
                QMessageBox.warning(self, "חסרים נתונים", "נא להזין ID גליון.")
                return

            if not self.game_id:
                self.game_id = f"BACKGAMMON_{random.randint(1000, 9999)}"
                self.txt_room_id.setText(self.game_id)

            c_str = "W" if self.local_color == COLOR_WHITE else "B"
            publish = self.chk_publish_lobby.isChecked()
            self._start_worker("create_room",
                sheet_id=sheet_id,
                room_id=self.game_id,
                host_name=self.player_name,
                host_color=c_str,
                time_control=self.time_control_mode,
                publish_lobby=publish
            )
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בפתיחת חדר", f"אירעה שגיאה:\n{e}")

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

    def on_create_sheet_clicked(self):
        if not self.sheets_client.is_logged_in():
            success, msg, _ = self.sheets_client.authenticate(prompt_browser=True)
            self.update_auth_status_ui()
            if not success:
                QMessageBox.critical(self, "כשל בהתחברות Google", msg)
                return
        self._start_worker("create_sheet", title="משחקי שש-בש מקוונים בנטפרי")

    def on_refresh_lobby_clicked(self):
        if not self.spreadsheet_id:
            QMessageBox.information(self, "נדרש גליון", "נא להזין ID גליון על מנת למשוך את רשימת החדרים.")
            return
        self._start_worker("fetch_lobby", sheet_id=self.spreadsheet_id)

    def _update_lobby_table(self, games: List[Dict[str, Any]]):
        self.table_lobby.setRowCount(0)
        for g in games:
            row = self.table_lobby.rowCount()
            self.table_lobby.insertRow(row)
            r_id = g.get("room_id", "")
            host = g.get("host_name", "")
            tc = g.get("time_control", "")
            self.table_lobby.setItem(row, 0, QTableWidgetItem(r_id))
            self.table_lobby.setItem(row, 1, QTableWidgetItem(host))
            self.table_lobby.setItem(row, 2, QTableWidgetItem(tc))

            btn_join = QPushButton("הצטרף")
            btn_join.clicked.connect(lambda _, rid=r_id: self._join_room_from_lobby(rid))
            self.table_lobby.setCellWidget(row, 3, btn_join)

    def _join_room_from_lobby(self, room_id: str):
        self.game_id = room_id
        self.txt_room_id.setText(room_id)
        self.cmb_mode.setCurrentIndex(1)
        self.local_color = COLOR_BLACK
        self.board_widget.set_player_color(COLOR_BLACK)
        self._start_worker("join_room", sheet_id=self.spreadsheet_id, room_id=room_id, guest_name=self.player_name)

    def on_takeback_clicked(self):
        if not self.engine.history:
            QMessageBox.information(self, "החזרת מסע", "טרם בוצעו מסעים במשחק.")
            return

        if self.is_online and not self.is_spectator:
            c_str = "W" if self.local_color == COLOR_WHITE else "B"
            self._start_worker("send_action", sheet_id=self.spreadsheet_id, room_id=self.game_id, player_name=self.player_name, color=c_str, action="TAKEBACK_REQUEST")
            QMessageBox.information(self, "בקשת החזרה", "נשלחה בקשת החזרת מסע ליריב.")
        else:
            self.engine.pop_last_move()
            self.update_status_display()

    def on_resign_clicked(self):
        res = QMessageBox.question(self, "כניעה", "האם אתה בטוח שברצונך להיכנע?", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            if self.is_online and not self.is_spectator:
                c_str = "W" if self.local_color == COLOR_WHITE else "B"
                self._start_worker("send_action", sheet_id=self.spreadsheet_id, room_id=self.game_id, player_name=self.player_name, color=c_str, action="RESIGN")
            sound_effects.play_game_end_sound(won=False)
            self.clock_running = False
            QMessageBox.information(self, "סיום משחק", "נכנעת במשחק.")

    def on_new_game_clicked(self):
        res = QMessageBox.question(self, "משחק חדש", "האם לאפס את הלוח ולהתחיל משחק שש-בש חדש?", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            self.engine.reset()
            self.table_moves.setRowCount(0)
            self.clock_running = False
            self.white_time_left = 600.0
            self.black_time_left = 600.0
            self.lbl_white_time.setText("10:00")
            self.lbl_black_time.setText("10:00")
            self.update_status_display()

    def send_chat_message(self, msg: str):
        if not msg.strip():
            return
        self._append_chat(self.player_name, msg)
        if self.is_online and self.spreadsheet_id:
            c_str = "W" if self.local_color == COLOR_WHITE else "B"
            self._start_worker("send_chat", sheet_id=self.spreadsheet_id, room_id=self.game_id, msg_id=self.last_synced_msg_id + 1, sender=self.player_name, color=c_str, message=msg)

    def on_send_chat_clicked(self):
        msg = self.txt_chat_input.text().strip()
        if msg:
            self.send_chat_message(msg)
            self.txt_chat_input.clear()

    def _append_chat(self, sender: str, msg: str):
        now_str = datetime.datetime.now().strftime("%H:%M")
        self.txt_chat_history.append(f"[{now_str}] <b>{sender}:</b> {msg}")
        self.txt_chat_history.verticalScrollBar().setValue(self.txt_chat_history.verticalScrollBar().maximum())

    def _start_worker(self, task_type: str, **kwargs):
        worker = BackgammonNetworkWorker(self.sync_mgr, task_type, **kwargs)
        self.active_workers.append(worker)

        def _cleanup(t_type, s_ok, d_res, e_msg):
            if worker in self.active_workers:
                self.active_workers.remove(worker)
            self.on_network_task_finished(t_type, s_ok, d_res, e_msg)

        worker.finished_task.connect(_cleanup)
        worker.start()

    def _on_player_name_changed(self, text: str):
        self.player_name = text.strip()
        cfg = load_config()
        cfg["player_name"] = self.player_name
        save_config(cfg)

    def _on_sheet_id_changed(self, text: str):
        self.spreadsheet_id = extract_spreadsheet_id(text.strip())
        cfg = load_config()
        cfg["spreadsheet_id"] = self.spreadsheet_id
        save_config(cfg)
        self.update_invite_code_display()

    def _on_room_id_changed(self, text: str):
        self.game_id = text.strip()
        cfg = load_config()
        cfg["backgammon_game_id"] = self.game_id
        save_config(cfg)
        self.update_invite_code_display()

    def _on_mode_changed(self, idx: int):
        self.saved_mode = idx
        self.is_online = (idx in (0, 1, 2))
        self.is_spectator = (idx == 2)
        if idx == 0:
            self.local_color = COLOR_WHITE
        elif idx == 1:
            self.local_color = COLOR_BLACK
        else:
            self.local_color = None

        self.board_widget.set_player_color(self.local_color)
        if self.is_online and not self.poll_timer.isActive():
            self.poll_timer.start()
        elif not self.is_online and self.poll_timer.isActive():
            self.poll_timer.stop()

        cfg = load_config()
        cfg["mode_index"] = idx
        save_config(cfg)
        self.update_status_display()

    def _on_time_control_changed(self, idx: int):
        times = [600.0, 300.0, 900.0, 999999.0]
        self.white_time_left = times[idx]
        self.black_time_left = times[idx]
        t_str = format_clock_time(self.white_time_left)
        self.lbl_white_time.setText(t_str)
        self.lbl_black_time.setText(t_str)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BackgammonMainWindow()
    window.show()
    sys.exit(app.exec())
