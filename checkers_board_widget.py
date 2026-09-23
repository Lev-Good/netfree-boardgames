# -*- coding: utf-8 -*-
"""
לוח דמקה אינטראקטיבי מעוצב ב-PySide6
לוח עץ אלגנטי, כלים תלת-ממדיים עם כתר מוזהב לדמקה (מלכה),
סימון מסלולי אכילה ודילוגים, ותמיכה בהיפוך לוח.
"""

from typing import Optional, List, Tuple
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QRadialGradient, QLinearGradient

from checkers_engine import (
    CheckersEngine, CheckersMove, EMPTY, WHITE_MAN, WHITE_KING,
    BLACK_MAN, BLACK_KING, COLOR_WHITE, COLOR_BLACK, square_to_coord
)

# צבעי לוח דמקה קלאסי (עץ אלגנטי)
COLOR_LIGHT_SQUARE = QColor("#EFE1CE")
COLOR_DARK_SQUARE = QColor("#8D5B3A")
COLOR_SELECTED = QColor(246, 246, 105, 180)
COLOR_LAST_MOVE = QColor(186, 202, 68, 160)
COLOR_LEGAL_DOT = QColor(34, 139, 34, 180)
COLOR_LEGAL_CAPTURE = QColor(220, 20, 60, 200)


class CheckersBoardWidget(QWidget):
    move_attempted = Signal(str)  # פולט מהלך ב-UCI כגון 'b3c4'

    def __init__(self, engine: CheckersEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.is_flipped = False  # False = לבן למטה, True = שחור למטה
        self.selected_square: Optional[int] = None
        self.legal_destinations: List[CheckersMove] = []
        self.last_move: Optional[CheckersMove] = None
        self.interactive = True
        self.player_color: Optional[int] = COLOR_WHITE  # COLOR_WHITE / COLOR_BLACK / None

        self.setMinimumSize(420, 420)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_player_color(self, color: Optional[int]):
        self.player_color = color
        self.is_flipped = (color == COLOR_BLACK)
        self.update()

    def set_last_move(self, move: Optional[CheckersMove]):
        self.last_move = move
        self.update()

    def clear_selection(self):
        self.selected_square = None
        self.legal_destinations.clear()
        self.update()

    def square_to_screen_coords(self, sq: int, square_size: float, offset_x: float, offset_y: float) -> QRectF:
        file = sq % 8
        rank = sq // 8
        col = (7 - file) if self.is_flipped else file
        row = rank if self.is_flipped else (7 - rank)
        x = offset_x + col * square_size
        y = offset_y + row * square_size
        return QRectF(x, y, square_size, square_size)

    def screen_coords_to_square(self, x: float, y: float, square_size: float, offset_x: float, offset_y: float) -> Optional[int]:
        col = int((x - offset_x) // square_size)
        row = int((y - offset_y) // square_size)
        if 0 <= col < 8 and 0 <= row < 8:
            file = (7 - col) if self.is_flipped else col
            rank = row if self.is_flipped else (7 - row)
            return rank * 8 + file
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
        font_crown = QFont("Segoe UI Emoji", int(square_size * 0.42), QFont.Bold)

        # 1. ציור משבצות הלוח
        for sq in range(64):
            rect = self.square_to_screen_coords(sq, square_size, offset_x, offset_y)
            file = sq % 8
            rank = sq // 8
            is_dark = ((file + rank) % 2) != 0

            # צבע משבצת
            bg_color = COLOR_DARK_SQUARE if is_dark else COLOR_LIGHT_SQUARE
            painter.fillRect(rect, bg_color)

            # הדגשת מהלך אחרון
            if self.last_move and (sq == self.last_move.from_sq or sq == self.last_move.to_sq):
                painter.fillRect(rect, COLOR_LAST_MOVE)

            # הדגשת משבצת נבחרת
            if self.selected_square == sq:
                painter.fillRect(rect, COLOR_SELECTED)

            # קואורדינטות (אותיות ומספרים בשוליים)
            painter.setFont(font_coords)
            coord_color = COLOR_LIGHT_SQUARE if is_dark else COLOR_DARK_SQUARE
            painter.setPen(coord_color)

            is_left_col = (file == 7 if self.is_flipped else file == 0)
            if is_left_col:
                painter.drawText(rect.adjusted(4, 2, -2, -2), Qt.AlignTop | Qt.AlignLeft, str(rank + 1))

            is_bottom_row = (rank == 7 if self.is_flipped else rank == 0)
            if is_bottom_row:
                painter.drawText(rect.adjusted(2, 2, -4, -2), Qt.AlignBottom | Qt.AlignRight, chr(ord('a') + file))

        # 2. סימון מסעים חוקיים
        for move in self.legal_destinations:
            dest_rect = self.square_to_screen_coords(move.to_sq, square_size, offset_x, offset_y)
            center = dest_rect.center()
            if move.is_capture():
                # אכילה: טבעת אדומה מודגשת
                painter.setPen(QPen(COLOR_LEGAL_CAPTURE, square_size * 0.09))
                painter.setBrush(Qt.NoBrush)
                radius = square_size * 0.35
                painter.drawEllipse(center, radius, radius)
            else:
                # מהלך רגיל: נקודה ירוקה
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(COLOR_LEGAL_DOT))
                radius = square_size * 0.16
                painter.drawEllipse(center, radius, radius)

        # 3. ציור כלי הדמקה
        for sq in range(64):
            piece = self.engine.get_piece(sq)
            if piece == EMPTY:
                continue

            rect = self.square_to_screen_coords(sq, square_size, offset_x, offset_y)
            center = rect.center()
            radius = square_size * 0.38

            is_white = piece > 0
            is_king = abs(piece) == WHITE_KING

            # גרדיאנט תלת-ממדי עגול
            grad = QRadialGradient(center.x() - radius * 0.3, center.y() - radius * 0.3, radius * 1.3)
            if is_white:
                grad.setColorAt(0.0, QColor("#FFFFFF"))
                grad.setColorAt(0.7, QColor("#EDEDED"))
                grad.setColorAt(1.0, QColor("#BDBDBD"))
                border_color = QColor("#858585")
            else:
                grad.setColorAt(0.0, QColor("#4A4A4A"))
                grad.setColorAt(0.7, QColor("#262626"))
                grad.setColorAt(1.0, QColor("#111111"))
                border_color = QColor("#0A0A0A")

            # גוף הכלי (דסקית דמקה)
            painter.setPen(QPen(border_color, 2))
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(center, radius, radius)

            # טבעת פנימית מובלטת
            painter.setPen(QPen(QColor(255, 255, 255, 60) if is_white else QColor(255, 255, 255, 40), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, radius * 0.72, radius * 0.72)

            # כתר לדמקה (מלכה)
            if is_king:
                painter.setFont(font_crown)
                painter.setPen(QColor("#FFD700") if not is_white else QColor("#D4AF37"))
                painter.drawText(rect.adjusted(0, -2, 0, 0), Qt.AlignCenter, "👑")

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

        # 1. אם נבחר יעד חוקי להזזה
        if self.selected_square is not None:
            for move in self.legal_destinations:
                if move.to_sq == clicked_sq:
                    uci = move.to_uci()
                    self.clear_selection()
                    self.move_attempted.emit(uci)
                    return

        # 2. בחירת כלי
        piece = self.engine.get_piece(clicked_sq)
        if piece != EMPTY:
            # בדיקת צבע שחקן ותור
            is_white = piece > 0
            piece_color = COLOR_WHITE if is_white else COLOR_BLACK

            if self.player_color is not None and piece_color != self.player_color:
                self.clear_selection()
                return

            if piece_color != self.engine.turn:
                self.clear_selection()
                return

            # בדיקה האם יש לכלי זה מסעים חוקיים
            all_legal = self.engine.get_legal_moves()
            piece_moves = [m for m in all_legal if m.from_sq == clicked_sq]

            if piece_moves:
                self.selected_square = clicked_sq
                self.legal_destinations = piece_moves
                self.update()
            else:
                self.clear_selection()
        else:
            self.clear_selection()
