# -*- coding: utf-8 -*-
"""
רכיב לוח שחמט אינטראקטיבי ב-PySide6
עיצוב מקצועי (סגנון Tournament), תמיכה בהיפוך לוח, סימון מסעים חוקיים,
הדגשת שח, והכתרת רגלי.
"""

from typing import Optional, List, Tuple
from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush

import chess

# צבעי לוח בסגנון טורניר מודרני
COLOR_LIGHT_SQUARE = QColor("#EEEED2")
COLOR_DARK_SQUARE = QColor("#769656")
COLOR_SELECTED = QColor(246, 246, 105, 170)
COLOR_LAST_MOVE = QColor(186, 202, 68, 170)
COLOR_CHECK = QColor(235, 60, 60, 180)
COLOR_LEGAL_DOT = QColor(20, 85, 30, 80)
COLOR_LEGAL_CAPTURE = QColor(20, 85, 30, 80)

# סמלי יוניקוד לשחמט
UNICODE_PIECES = {
    'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
}


class PromotionDialog(QDialog):
    """דיאלוג בחירת כלי בעת הכתרת רגלי"""
    def __init__(self, color: chess.Color, parent=None):
        super().__init__(parent)
        self.setWindowTitle("הכתרת רגלי - בחר כלי")
        self.setFixedSize(320, 130)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.selected_piece = chess.QUEEN

        layout = QVBoxLayout(self)
        lbl = QLabel("בחר את הכלי אליו יומר הרגלי:")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(lbl)

        btn_layout = QHBoxLayout()
        symbols = [
            ("מלכה", chess.QUEEN, 'Q' if color == chess.WHITE else 'q'),
            ("צריח", chess.ROOK, 'R' if color == chess.WHITE else 'r'),
            ("רץ", chess.BISHOP, 'B' if color == chess.WHITE else 'b'),
            ("פרש", chess.KNIGHT, 'N' if color == chess.WHITE else 'n')
        ]

        for name, piece_type, sym in symbols:
            btn = QPushButton(f"{UNICODE_PIECES[sym]}\n{name}")
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 18px;
                    font-weight: bold;
                    padding: 8px;
                    border: 1px solid #DADCE0;
                    border-radius: 6px;
                    background-color: #F8F9FA;
                }
                QPushButton:hover {
                    background-color: #E8F0FE;
                    border-color: #1A73E8;
                }
            """)
            btn.clicked.connect(lambda _, pt=piece_type: self.choose(pt))
            btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)

    def choose(self, piece_type: chess.PieceType):
        self.selected_piece = piece_type
        self.accept()


class ChessBoardWidget(QWidget):
    """לוח שחמט אינטראקטיבי 8x8"""
    move_attempted = Signal(str)  # פולט מהלך ב-UCI, למשל 'e2e4' או 'e7e8q'

    def __init__(self, board: chess.Board, parent=None):
        super().__init__(parent)
        self.board = board
        self.is_flipped = False           # False: לבן למטה, True: שחור למטה
        self.selected_square: Optional[int] = None
        self.legal_destinations: List[int] = []
        self.last_move: Optional[chess.Move] = None
        self.interactive = True           # האם השחקן יכול להזיז כרגע
        self.player_color: Optional[chess.Color] = None  # chess.WHITE / chess.BLACK / None (שניהם)

        self.setMinimumSize(420, 420)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_player_color(self, color: Optional[chess.Color]):
        """קביעת צבע השחקן המקומי והיפוך הלוח בהתאם"""
        self.player_color = color
        self.is_flipped = (color == chess.BLACK)
        self.update()

    def set_last_move(self, move: Optional[chess.Move]):
        self.last_move = move
        self.update()

    def clear_selection(self):
        self.selected_square = None
        self.legal_destinations.clear()
        self.update()

    def square_to_screen_coords(self, sq: int, square_size: float, offset_x: float, offset_y: float) -> QRectF:
        """מחשב את מלבן המסך של משבצת נתונה"""
        file = chess.square_file(sq)
        rank = chess.square_rank(sq)

        col = (7 - file) if self.is_flipped else file
        row = rank if self.is_flipped else (7 - rank)

        x = offset_x + col * square_size
        y = offset_y + row * square_size
        return QRectF(x, y, square_size, square_size)

    def screen_coords_to_square(self, x: float, y: float, square_size: float, offset_x: float, offset_y: float) -> Optional[int]:
        """מחשב איזה משבצת נלחצה במסך"""
        col = int((x - offset_x) // square_size)
        row = int((y - offset_y) // square_size)

        if 0 <= col < 8 and 0 <= row < 8:
            file = (7 - col) if self.is_flipped else col
            rank = row if self.is_flipped else (7 - row)
            return chess.square(file, rank)
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        board_size = min(w, h)
        square_size = board_size / 8.0
        offset_x = (w - board_size) / 2.0
        offset_y = (h - board_size) / 2.0

        font_coords = QFont("Arial", int(square_size * 0.16), QFont.Bold)
        font_piece = QFont("Segoe UI Symbol", int(square_size * 0.72))

        # 1. ציור משבצות הלוח
        for sq in chess.SQUARES:
            rect = self.square_to_screen_coords(sq, square_size, offset_x, offset_y)
            file = chess.square_file(sq)
            rank = chess.square_rank(sq)
            is_light = ((file + rank) % 2) != 0

            # צבע משבצת בסיס
            bg_color = COLOR_LIGHT_SQUARE if is_light else COLOR_DARK_SQUARE
            painter.fillRect(rect, bg_color)

            # הדגשת מהלך אחרון
            if self.last_move and (sq == self.last_move.from_square or sq == self.last_move.to_square):
                painter.fillRect(rect, COLOR_LAST_MOVE)

            # הדגשת משבצת שנבחרה
            if self.selected_square == sq:
                painter.fillRect(rect, COLOR_SELECTED)

            # הדגשת מלך בשח
            piece = self.board.piece_at(sq)
            if piece and piece.piece_type == chess.KING and piece.color == self.board.turn and self.board.is_check():
                painter.fillRect(rect, COLOR_CHECK)

            # אותיות ומספרים בשוליים של המשבצות
            painter.setFont(font_coords)
            coord_color = COLOR_DARK_SQUARE if is_light else COLOR_LIGHT_SQUARE
            painter.setPen(coord_color)

            # מספר שורה (בטור השמאלי ביותר על המסך)
            is_left_col = (file == 7 if self.is_flipped else file == 0)
            if is_left_col:
                rank_str = str(rank + 1)
                painter.drawText(rect.adjusted(4, 2, -2, -2), Qt.AlignTop | Qt.AlignLeft, rank_str)

            # אות עמודה (בשורה התחתונה ביותר על המסך)
            is_bottom_row = (rank == 7 if self.is_flipped else rank == 0)
            if is_bottom_row:
                file_str = chr(ord('a') + file)
                painter.drawText(rect.adjusted(2, 2, -4, -2), Qt.AlignBottom | Qt.AlignRight, file_str)

        # 2. ציור נקודות של מסעים חוקיים
        for dest_sq in self.legal_destinations:
            dest_rect = self.square_to_screen_coords(dest_sq, square_size, offset_x, offset_y)
            has_target_piece = self.board.piece_at(dest_sq) is not None

            if has_target_piece:
                # עיגול חלול סביב הכלי שניתן לאכול
                painter.setPen(QPen(COLOR_LEGAL_CAPTURE, square_size * 0.08))
                painter.setBrush(Qt.NoBrush)
                margin = square_size * 0.1
                painter.drawEllipse(dest_rect.adjusted(margin, margin, -margin, -margin))
            else:
                # נקודה עגולה במרכז המשבצת הפנויה
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(COLOR_LEGAL_DOT))
                center = dest_rect.center()
                radius = square_size * 0.15
                painter.drawEllipse(center, radius, radius)

        # 3. ציור כלי השחמט
        painter.setFont(font_piece)
        for sq in chess.SQUARES:
            piece = self.board.piece_at(sq)
            if not piece:
                continue

            rect = self.square_to_screen_coords(sq, square_size, offset_x, offset_y)
            sym = UNICODE_PIECES.get(piece.symbol(), "")

            if piece.color == chess.WHITE:
                # כלי לבן: טקסט לבן עם קו מתאר דק
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(rect, Qt.AlignCenter, sym)
                # קו מתאר
                painter.setPen(QPen(QColor("#202124"), 1))
                painter.drawText(rect.adjusted(1, 1, 0, 0), Qt.AlignCenter, sym)
            else:
                # כלי שחור: טקסט שחור מובהק
                painter.setPen(QColor("#111111"))
                painter.drawText(rect, Qt.AlignCenter, sym)

    def mousePressEvent(self, event):
        if not self.interactive or event.button() != Qt.LeftButton:
            return

        w = self.width()
        h = self.height()
        board_size = min(w, h)
        square_size = board_size / 8.0
        offset_x = (w - board_size) / 2.0
        offset_y = (h - board_size) / 2.0

        clicked_sq = self.screen_coords_to_square(event.position().x(), event.position().y(), square_size, offset_x, offset_y)
        if clicked_sq is None:
            self.clear_selection()
            return

        # 1. אם נבחרה משבצת חוקית להזזה
        if self.selected_square is not None and clicked_sq in self.legal_destinations:
            from_sq = self.selected_square
            to_sq = clicked_sq

            # בדיקה האם זו הכתרת רגלי
            moving_piece = self.board.piece_at(from_sq)
            is_promo = (
                moving_piece and moving_piece.piece_type == chess.PAWN and
                ((moving_piece.color == chess.WHITE and chess.square_rank(to_sq) == 7) or
                 (moving_piece.color == chess.BLACK and chess.square_rank(to_sq) == 0))
            )

            promotion_char = ""
            if is_promo:
                dialog = PromotionDialog(moving_piece.color, self)
                if dialog.exec():
                    promo_map = {chess.QUEEN: 'q', chess.ROOK: 'r', chess.BISHOP: 'b', chess.KNIGHT: 'n'}
                    promotion_char = promo_map.get(dialog.selected_piece, 'q')
                else:
                    self.clear_selection()
                    return

            from_str = chess.square_name(from_sq)
            to_str = chess.square_name(to_sq)
            uci = f"{from_str}{to_str}{promotion_char}"

            self.clear_selection()
            self.move_attempted.emit(uci)
            return

        # 2. בחירת כלי
        piece = self.board.piece_at(clicked_sq)
        if piece:
            # אם מוגדר צבע שחקן, מותר לבחור רק כלים בצבע שלו ובתורו
            if self.player_color is not None and piece.color != self.player_color:
                self.clear_selection()
                return

            if piece.color != self.board.turn:
                self.clear_selection()
                return

            self.selected_square = clicked_sq
            # חישוב משבצות יעד חוקיות
            self.legal_destinations = [
                m.to_square for m in self.board.legal_moves if m.from_square == clicked_sq
            ]
            self.update()
        else:
            self.clear_selection()
