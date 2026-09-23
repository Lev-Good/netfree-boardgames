# -*- coding: utf-8 -*-
"""
רכיב לוח שש-בש אינטראקטיבי ב-PySide6
עיצוב אותנטי בסגנון לוח עץ מסורתי, 24 משולשים מדורגים,
מחיצת משקוף (Bar), מגשי הוצאת כלים, תצוגת קוביות תלת-ממדיות,
וסימון אינטראקטיבי של מסעים חוקיים.
"""

from typing import Optional, List, Tuple, Dict
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPolygonF, QRadialGradient

from backgammon_engine import BackgammonEngine, BackgammonMove, COLOR_WHITE, COLOR_BLACK, POINT_BAR

# פלטת צבעי עץ ושש-בש קלאסיים
COLOR_FRAME = QColor("#4A2E18")
COLOR_SURFACE = QColor("#D7B185")
COLOR_POINT_DARK = QColor("#8B3A2B")    # משולש אדום-חום
COLOR_POINT_LIGHT = QColor("#EFE4B0")   # משולש שנהב בהיר
COLOR_BAR = QColor("#3D2411")
COLOR_SELECTED = QColor(246, 246, 105, 180)
COLOR_DEST_HIGHLIGHT = QColor(34, 139, 34, 180)


class BackgammonBoardWidget(QWidget):
    move_attempted = Signal(object)  # פולט אובייקט BackgammonMove
    dice_roll_requested = Signal()   # פולט בקשה להטיל קוביות

    def __init__(self, engine: BackgammonEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.selected_point: Optional[int] = None   # נקודה שנבחרה (1-24 או POINT_BAR)
        self.legal_destinations: List[BackgammonMove] = []
        self.interactive = True
        self.player_color: Optional[int] = COLOR_WHITE

        self.setMinimumSize(560, 420)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_player_color(self, color: Optional[int]):
        self.player_color = color
        self.update()

    def clear_selection(self):
        self.selected_point = None
        self.legal_destinations.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()

        # מסגרת חיצונית
        margin = 10
        board_rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)
        painter.fillRect(board_rect, COLOR_FRAME)

        inner_margin = 15
        play_rect = board_rect.adjusted(inner_margin, inner_margin, -inner_margin, -inner_margin)
        painter.fillRect(play_rect, COLOR_SURFACE)

        pw = play_rect.width()
        ph = play_rect.height()
        bar_width = max(30.0, pw * 0.08)
        tray_width = max(35.0, pw * 0.09)

        # אזור המשחק השמאלי והימני
        half_width = (pw - bar_width - tray_width) / 2.0
        left_quad = QRectF(play_rect.left(), play_rect.top(), half_width, ph)
        bar_rect = QRectF(left_quad.right(), play_rect.top(), bar_width, ph)
        right_quad = QRectF(bar_rect.right(), play_rect.top(), half_width, ph)
        tray_rect = QRectF(right_quad.right(), play_rect.top(), tray_width, ph)

        # ציור המשקוף (Bar) ומגש ההוצאה
        painter.fillRect(bar_rect, COLOR_BAR)
        painter.fillRect(tray_rect, COLOR_BAR.darker(110))

        point_width = half_width / 6.0
        triangle_height = ph * 0.42

        # מיפוי 24 הנקודות למלבני המשחק:
        # עליונים: 13 עד 18 (שמאל עליון), 19 עד 24 (ימין עליון)
        # תחתונים: 12 עד 7 (שמאל תחתון), 6 עד 1 (ימין תחתון)
        point_polygons: Dict[int, QPolygonF] = {}

        # 1. ציור 12 המשולשים העליונים
        for i in range(6):
            pt_left = 13 + i
            px = left_quad.left() + i * point_width
            poly = QPolygonF([
                QPointF(px, play_rect.top()),
                QPointF(px + point_width, play_rect.top()),
                QPointF(px + point_width / 2.0, play_rect.top() + triangle_height)
            ])
            point_polygons[pt_left] = poly

            pt_right = 19 + i
            px_r = right_quad.left() + i * point_width
            poly_r = QPolygonF([
                QPointF(px_r, play_rect.top()),
                QPointF(px_r + point_width, play_rect.top()),
                QPointF(px_r + point_width / 2.0, play_rect.top() + triangle_height)
            ])
            point_polygons[pt_right] = poly_r

        # 2. ציור 12 המשולשים התחתונים
        for i in range(6):
            pt_left_b = 12 - i
            px = left_quad.left() + i * point_width
            poly_b = QPolygonF([
                QPointF(px, play_rect.bottom()),
                QPointF(px + point_width, play_rect.bottom()),
                QPointF(px + point_width / 2.0, play_rect.bottom() - triangle_height)
            ])
            point_polygons[pt_left_b] = poly_b

            pt_right_b = 6 - i
            px_r = right_quad.left() + i * point_width
            poly_rb = QPolygonF([
                QPointF(px_r, play_rect.bottom()),
                QPointF(px_r + point_width, play_rect.bottom()),
                QPointF(px_r + point_width / 2.0, play_rect.bottom() - triangle_height)
            ])
            point_polygons[pt_right_b] = poly_rb

        # ציור המשולשים על הלוח
        painter.setPen(Qt.NoPen)
        for pt_num, poly in point_polygons.items():
            color = COLOR_POINT_DARK if (pt_num % 2 == 1) else COLOR_POINT_LIGHT
            painter.setBrush(color)
            painter.drawPolygon(poly)

            # הדגשת נקודה שנבחרה
            if self.selected_point == pt_num:
                painter.setBrush(COLOR_SELECTED)
                painter.drawPolygon(poly)

            # הדגשת יעד חוקי
            if any(m.to_pt == pt_num for m in self.legal_destinations):
                painter.setBrush(COLOR_DEST_HIGHLIGHT)
                painter.drawPolygon(poly)

        # 3. ציור הכלים בכל נקודה (1-24)
        checker_radius = min(point_width * 0.44, 20.0)

        for pt_num in range(1, 25):
            count = self.engine.points[pt_num]
            if count == 0:
                continue

            poly = point_polygons[pt_num]
            base_x = (poly[0].x() + poly[1].x()) / 2.0
            is_top = (pt_num >= 13)

            is_white = count > 0
            abs_count = abs(count)
            display_count = min(abs_count, 5)

            for c_idx in range(display_count):
                if is_top:
                    cy = play_rect.top() + checker_radius + c_idx * (checker_radius * 1.9)
                else:
                    cy = play_rect.bottom() - checker_radius - c_idx * (checker_radius * 1.9)

                self._draw_checker(painter, base_x, cy, checker_radius, is_white)

            # אם יש יותר מ-5 כלים, כותבים מספר על הכלי האחרון
            if abs_count > 5:
                if is_top:
                    cy = play_rect.top() + checker_radius + 4 * (checker_radius * 1.9)
                else:
                    cy = play_rect.bottom() - checker_radius - 4 * (checker_radius * 1.9)
                painter.setFont(QFont("Segoe UI", int(checker_radius * 0.9), QFont.Bold))
                painter.setPen(QColor("#111111") if is_white else QColor("#FFFFFF"))
                painter.drawText(QRectF(base_x - checker_radius, cy - checker_radius, checker_radius * 2, checker_radius * 2), Qt.AlignCenter, str(abs_count))

        # 4. ציור כלים על הבר (משקוף)
        bar_center_x = bar_rect.center().x()
        if self.engine.white_bar > 0:
            w_bar_count = min(self.engine.white_bar, 4)
            for i in range(w_bar_count):
                cy = bar_rect.center().y() - (i + 1) * (checker_radius * 2.1)
                self._draw_checker(painter, bar_center_x, cy, checker_radius, is_white=True)

        if self.engine.black_bar > 0:
            b_bar_count = min(self.engine.black_bar, 4)
            for i in range(b_bar_count):
                cy = bar_rect.center().y() + (i + 1) * (checker_radius * 2.1)
                self._draw_checker(painter, bar_center_x, cy, checker_radius, is_white=False)

        # 5. ציור כלים שהוצאו (Trays)
        tray_center_x = tray_rect.center().x()
        painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRectF(tray_rect.left(), play_rect.top() + 10, tray_width, 25), Qt.AlignCenter, f"לבן: {self.engine.white_off}")
        painter.drawText(QRectF(tray_rect.left(), play_rect.bottom() - 35, tray_width, 25), Qt.AlignCenter, f"שחור: {self.engine.black_off}")

        if any(m.is_off for m in self.legal_destinations):
            # הדגשת מגש הוצאה אם יש מהלך הוצאה חוקי
            painter.setPen(QPen(QColor("#34A853"), 3))
            painter.drawRect(tray_rect)

        # 6. ציור קוביות (Dice)
        if self.engine.current_dice:
            dice_y = bar_rect.center().y() - 15
            d1_rect = QRectF(right_quad.left() + 25, dice_y, 32, 32)
            d2_rect = QRectF(right_quad.left() + 65, dice_y, 32, 32)

            self._draw_die(painter, d1_rect, self.engine.current_dice[0], used=(self.engine.current_dice[0] not in self.engine.remaining_moves))
            self._draw_die(painter, d2_rect, self.engine.current_dice[1], used=(self.engine.current_dice[1] not in self.engine.remaining_moves))

        # שמירת המיפויים לאירועי לחיצה
        self._last_point_polys = point_polygons
        self._last_bar_rect = bar_rect
        self._last_tray_rect = tray_rect

    def _draw_checker(self, painter: QPainter, cx: float, cy: float, radius: float, is_white: bool):
        """ציור דיסקית שש-בש עם גרדיאנט תלת-ממדי מוצלל"""
        grad = QRadialGradient(cx - radius * 0.3, cy - radius * 0.3, radius * 1.3)
        if is_white:
            grad.setColorAt(0.0, QColor("#FFFFFF"))
            grad.setColorAt(0.7, QColor("#EDEDED"))
            grad.setColorAt(1.0, QColor("#BDBDBD"))
            border_color = QColor("#757575")
        else:
            grad.setColorAt(0.0, QColor("#4A4A4A"))
            grad.setColorAt(0.7, QColor("#262626"))
            grad.setColorAt(1.0, QColor("#111111"))
            border_color = QColor("#050505")

        painter.setPen(QPen(border_color, 1.8))
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # טבעת פנימית
        painter.setPen(QPen(QColor(255, 255, 255, 50) if is_white else QColor(255, 255, 255, 30), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius * 0.65, radius * 0.65)

    def _draw_die(self, painter: QPainter, rect: QRectF, value: int, used: bool):
        """ציור קובייה תלת-ממדית עם נקודות"""
        opacity = 0.4 if used else 1.0
        bg_color = QColor(255, 255, 255, int(255 * opacity))
        dot_color = QColor(20, 20, 20, int(255 * opacity))

        painter.setPen(QPen(QColor(180, 180, 180, int(255 * opacity)), 1.5))
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, 5, 5)

        # ציור נקודות לפי הערך 1-6
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot_color)
        r = 2.4
        cx = rect.center().x()
        cy = rect.center().y()
        w = rect.width()

        dot_positions = {
            1: [(cx, cy)],
            2: [(rect.left() + w * 0.3, rect.top() + w * 0.3), (rect.right() - w * 0.3, rect.bottom() - w * 0.3)],
            3: [(rect.left() + w * 0.28, rect.top() + w * 0.28), (cx, cy), (rect.right() - w * 0.28, rect.bottom() - w * 0.28)],
            4: [
                (rect.left() + w * 0.28, rect.top() + w * 0.28), (rect.right() - w * 0.28, rect.top() + w * 0.28),
                (rect.left() + w * 0.28, rect.bottom() - w * 0.28), (rect.right() - w * 0.28, rect.bottom() - w * 0.28)
            ],
            5: [
                (rect.left() + w * 0.28, rect.top() + w * 0.28), (rect.right() - w * 0.28, rect.top() + w * 0.28),
                (cx, cy),
                (rect.left() + w * 0.28, rect.bottom() - w * 0.28), (rect.right() - w * 0.28, rect.bottom() - w * 0.28)
            ],
            6: [
                (rect.left() + w * 0.28, rect.top() + w * 0.25), (rect.right() - w * 0.28, rect.top() + w * 0.25),
                (rect.left() + w * 0.28, cy), (rect.right() - w * 0.28, cy),
                (rect.left() + w * 0.28, rect.bottom() - w * 0.25), (rect.right() - w * 0.28, rect.bottom() - w * 0.25)
            ]
        }

        for px, py in dot_positions.get(value, []):
            painter.drawEllipse(QPointF(px, py), r, r)

    def mousePressEvent(self, event):
        if not self.interactive or event.button() != Qt.LeftButton:
            return

        click_pos = event.position()

        # 1. אם נבחר מקור, בדיקה האם לחץ על יעד חוקי (נקודה 1-24 או הוצאה)
        if self.selected_point is not None:
            # בדיקת הוצאה
            if hasattr(self, '_last_tray_rect') and self._last_tray_rect.contains(click_pos):
                for move in self.legal_destinations:
                    if move.is_off:
                        self.clear_selection()
                        self.move_attempted.emit(move)
                        return

            # בדיקת נקודה
            if hasattr(self, '_last_point_polys'):
                for pt_num, poly in self._last_point_polys.items():
                    if poly.containsPoint(click_pos, Qt.OddEvenFill):
                        for move in self.legal_destinations:
                            if move.to_pt == pt_num:
                                self.clear_selection()
                                self.move_attempted.emit(move)
                                return

        # 2. בדיקת בחירת מקור
        # א. בדיקה אם לחץ על הבר
        if hasattr(self, '_last_bar_rect') and self._last_bar_rect.contains(click_pos):
            if self.engine.has_checkers_on_bar(self.engine.turn):
                moves = [m for m in self.engine.get_legal_moves() if m.from_pt == POINT_BAR]
                if moves:
                    self.selected_point = POINT_BAR
                    self.legal_destinations = moves
                    self.update()
                    return

        # ב. בדיקה אם לחץ על אחת מ-24 הנקודות
        if hasattr(self, '_last_point_polys'):
            for pt_num, poly in self._last_point_polys.items():
                if poly.containsPoint(click_pos, Qt.OddEvenFill):
                    count = self.engine.points[pt_num]
                    # האם הכלי שייך לשחקן הנוכחי
                    if (self.engine.turn == COLOR_WHITE and count > 0) or (self.engine.turn == COLOR_BLACK and count < 0):
                        moves = [m for m in self.engine.get_legal_moves() if m.from_pt == pt_num]
                        if moves:
                            self.selected_point = pt_num
                            self.legal_destinations = moves
                            self.update()
                            return

        self.clear_selection()
