# -*- coding: utf-8 -*-
"""
מנוע לוגיקת שש-בש קלאסי (Backgammon / Shesh-Besh)
תומך בלוח 24 משולשים, הטלת קוביות (כולל דאבל), כניסה מהמשקוף (Bar),
אכילת כלים בודדים (Blot), הוצאת כלים (Bearing Off), וזיהוי ניצחון רגיל / מארס / מארס טורקי.
"""

import random
from typing import List, Dict, Tuple, Optional, Any

COLOR_WHITE = 1    # לבן - נע מנקודה 24 לעבר נקודה 1 (הבית שלו: 1-6)
COLOR_BLACK = -1   # שחור - נע מנקודה 1 לעבר נקודה 24 (הבית שלו: 19-24)

POINT_BAR = 0
POINT_OFF = 25


class BackgammonMove:
    def __init__(self, from_pt: int, to_pt: int, die_used: int, is_hit: bool = False, is_off: bool = False):
        self.from_pt = from_pt
        self.to_pt = to_pt
        self.die_used = die_used
        self.is_hit = is_hit
        self.is_off = is_off

    def to_uci(self) -> str:
        f = "bar" if self.from_pt == POINT_BAR else str(self.from_pt)
        t = "off" if self.is_off else str(self.to_pt)
        return f"{f}/{t}"

    def __repr__(self):
        f = "בר" if self.from_pt == POINT_BAR else str(self.from_pt)
        t = "הוצאה" if self.is_off else str(self.to_pt)
        hit_str = "*" if self.is_hit else ""
        return f"{f}->{t}{hit_str}"


class BackgammonEngine:
    def __init__(self):
        # מערך 26 אינדקסים:
        # נקודות 1 עד 24: מספר חיובי מייצג כלים לבנים, מספר שלילי מייצג כלים שחורים
        # אינדקס 0 ו-25 שמורים
        self.points: List[int] = [0] * 25
        self.white_bar: int = 0
        self.black_bar: int = 0
        self.white_off: int = 0
        self.black_off: int = 0

        self.turn: int = COLOR_WHITE
        self.current_dice: List[int] = []         # תוצאות הקוביות הנוכחיות, למשל [3, 5]
        self.remaining_moves: List[int] = []      # מהלכים שטרם נוצלו (אם דאבל 4-4: [4, 4, 4, 4])
        self.history: List[Dict[str, Any]] = []

        self.reset()

    def reset(self):
        """אתחול לוח שש-בש קלאסי (15 כלים לכל שחקן)"""
        self.points = [0] * 25
        self.white_bar = 0
        self.black_bar = 0
        self.white_off = 0
        self.black_off = 0

        # סידור כלים סטנדרטי (White חיובי, Black שלילי)
        # לבן:
        self.points[24] = 2   # 2 כלים בנקודה 24
        self.points[13] = 5   # 5 כלים בנקודה 13
        self.points[8]  = 3   # 3 כלים בנקודה 8
        self.points[6]  = 5   # 5 כלים בנקודה 6

        # שחור:
        self.points[1]  = -2  # 2 כלים בנקודה 1
        self.points[12] = -5  # 5 כלים בנקודה 12
        self.points[17] = -3  # 3 כלים בנקודה 17
        self.points[19] = -5  # 5 כלים בנקודה 19

        self.turn = COLOR_WHITE
        self.current_dice = []
        self.remaining_moves = []
        self.history.clear()

    def roll_dice(self, d1: Optional[int] = None, d2: Optional[int] = None) -> List[int]:
        """הטלת שתי קוביות (אם לא סופקו ערכים ספציפיים)"""
        die1 = d1 if d1 is not None else random.randint(1, 6)
        die2 = d2 if d2 is not None else random.randint(1, 6)

        self.current_dice = [die1, die2]
        if die1 == die2:
            # דאבל - 4 מהלכים
            self.remaining_moves = [die1, die1, die1, die1]
        else:
            self.remaining_moves = [die1, die2]

        return self.current_dice

    def is_white_turn(self) -> bool:
        return self.turn == COLOR_WHITE

    def get_turn_name_hebrew(self) -> str:
        return "לבן" if self.turn == COLOR_WHITE else "שחור"

    def has_checkers_on_bar(self, color: int) -> bool:
        return (self.white_bar > 0) if color == COLOR_WHITE else (self.black_bar > 0)

    def can_bear_off(self, color: int) -> bool:
        """האם השחקן רשאי להוציא כלים (כל כליו הגיעו לבית)"""
        if self.has_checkers_on_bar(color):
            return False

        if color == COLOR_WHITE:
            # הבית של לבן הוא נקודות 1 עד 6
            # אסור שיהיו כלים לבנים בנקודות 7 עד 24
            for pt in range(7, 25):
                if self.points[pt] > 0:
                    return False
            return True
        else:
            # הבית של שחור הוא נקודות 19 עד 24
            # אסור שיהיו כלים שחורים בנקודות 1 עד 18
            for pt in range(1, 19):
                if self.points[pt] < 0:
                    return False
            return True

    def get_legal_moves(self) -> List[BackgammonMove]:
        """חישוב כל המהלכים החוקיים עבור השחקן שתורו כעת בהתאם לקוביות שנותרו"""
        if not self.remaining_moves:
            return []

        moves: List[BackgammonMove] = []
        distinct_dice = set(self.remaining_moves)

        # 1. חובת יציאה מהבר (משקוף)
        if self.has_checkers_on_bar(self.turn):
            for die in distinct_dice:
                if self.turn == COLOR_WHITE:
                    target_pt = 25 - die  # לבן נכנס לנקודות 19-24
                    if self._is_open_point(target_pt, COLOR_WHITE):
                        is_hit = (self.points[target_pt] == -1)
                        moves.append(BackgammonMove(POINT_BAR, target_pt, die, is_hit=is_hit))
                else:
                    target_pt = die  # שחור נכנס לנקודות 1-6
                    if self._is_open_point(target_pt, COLOR_BLACK):
                        is_hit = (self.points[target_pt] == 1)
                        moves.append(BackgammonMove(POINT_BAR, target_pt, die, is_hit=is_hit))
            return moves

        # 2. מהלכים רגילים על הלוח והוצאת כלים
        can_off = self.can_bear_off(self.turn)

        for pt in range(1, 25):
            # האם יש לשחקן כלי בנקודה זו
            count = self.points[pt]
            if (self.turn == COLOR_WHITE and count <= 0) or (self.turn == COLOR_BLACK and count >= 0):
                continue

            for die in distinct_dice:
                if self.turn == COLOR_WHITE:
                    dest_pt = pt - die
                    if dest_pt >= 1:
                        if self._is_open_point(dest_pt, COLOR_WHITE):
                            is_hit = (self.points[dest_pt] == -1)
                            moves.append(BackgammonMove(pt, dest_pt, die, is_hit=is_hit))
                    elif can_off:
                        # הוצאת כלי עבור לבן
                        if dest_pt == 0:
                            # הוצאה מדויקת
                            moves.append(BackgammonMove(pt, 0, die, is_off=True))
                        elif dest_pt < 0:
                            # הוצאה עם קובייה גדולה יותר (רק אם אין כלים מאחור)
                            no_higher = all(self.points[higher_pt] <= 0 for higher_pt in range(pt + 1, 7))
                            if no_higher:
                                moves.append(BackgammonMove(pt, 0, die, is_off=True))

                else:  # BLACK
                    dest_pt = pt + die
                    if dest_pt <= 24:
                        if self._is_open_point(dest_pt, COLOR_BLACK):
                            is_hit = (self.points[dest_pt] == 1)
                            moves.append(BackgammonMove(pt, dest_pt, die, is_hit=is_hit))
                    elif can_off:
                        # הוצאת כלי עבור שחור
                        if dest_pt == 25:
                            moves.append(BackgammonMove(pt, 25, die, is_off=True))
                        elif dest_pt > 25:
                            no_higher = all(self.points[higher_pt] >= 0 for higher_pt in range(19, pt))
                            if no_higher:
                                moves.append(BackgammonMove(pt, 25, die, is_off=True))

        return moves

    def _is_open_point(self, pt: int, player_color: int) -> bool:
        """נקודה פתוחה אם היא ריקה, שייכת לנו, או מכילה בדיוק כלי יריב אחד (Blot)"""
        val = self.points[pt]
        if player_color == COLOR_WHITE:
            return val >= -1  # פתוח אם 0, חיובי, או -1 (אכילה)
        else:
            return val <= 1   # פתוח אם 0, שלילי, או 1 (אכילה)

    def push_move(self, move: BackgammonMove, player_name: str = "") -> Tuple[bool, Optional[str], Optional[str]]:
        """ביצוע מהלך שש-בש ועדכון הלוח והקוביות שנותרו"""
        legal_moves = self.get_legal_moves()
        matched_move = None
        for lm in legal_moves:
            if lm.from_pt == move.from_pt and lm.to_pt == move.to_pt and lm.die_used in self.remaining_moves:
                matched_move = lm
                break

        if not matched_move:
            return False, None, "מהלך לא חוקי בשש-בש!"

        # שמירת מצב קודם
        state_record = {
            "points": list(self.points),
            "white_bar": self.white_bar,
            "black_bar": self.black_bar,
            "white_off": self.white_off,
            "black_off": self.black_off,
            "turn": self.turn,
            "remaining_moves": list(self.remaining_moves),
            "move": matched_move,
            "player": player_name
        }
        self.history.append(state_record)

        # 1. גריעת הכלי ממקורו
        if matched_move.from_pt == POINT_BAR:
            if self.turn == COLOR_WHITE:
                self.white_bar -= 1
            else:
                self.black_bar -= 1
        else:
            if self.turn == COLOR_WHITE:
                self.points[matched_move.from_pt] -= 1
            else:
                self.points[matched_move.from_pt] += 1

        # 2. הוספת הכלי ליעדו (או הוצאה)
        if matched_move.is_off:
            if self.turn == COLOR_WHITE:
                self.white_off += 1
            else:
                self.black_off += 1
        else:
            # בדיקת אכילת כלי בודד
            if matched_move.is_hit:
                if self.turn == COLOR_WHITE:
                    self.black_bar += 1
                    self.points[matched_move.to_pt] = 1
                else:
                    self.white_bar += 1
                    self.points[matched_move.to_pt] = -1
            else:
                if self.turn == COLOR_WHITE:
                    self.points[matched_move.to_pt] += 1
                else:
                    self.points[matched_move.to_pt] -= 1

        # 3. גריעת הקובייה שנוצלה
        if matched_move.die_used in self.remaining_moves:
            self.remaining_moves.remove(matched_move.die_used)

        # 4. בדיקה האם נותרו מהלכים אפשריים
        if not self.remaining_moves or not self.get_legal_moves():
            self.end_turn()

        return True, str(matched_move), None

    def end_turn(self):
        """העברת תור לשחקן הבא ואיפוס קוביות"""
        self.turn = COLOR_BLACK if self.turn == COLOR_WHITE else COLOR_WHITE
        self.remaining_moves.clear()
        self.current_dice.clear()

    def pop_last_move(self) -> Tuple[bool, Optional[str]]:
        """ביטול מהלך אחרון (Takeback)"""
        if not self.history:
            return False, None
        last_state = self.history.pop()
        self.points = last_state["points"]
        self.white_bar = last_state["white_bar"]
        self.black_bar = last_state["black_bar"]
        self.white_off = last_state["white_off"]
        self.black_off = last_state["black_off"]
        self.turn = last_state["turn"]
        self.remaining_moves = last_state["remaining_moves"]
        m = last_state.get("move")
        return True, str(m) if m else None

    def is_game_over(self) -> bool:
        """המשחק מסתיים כאשר אחד השחקנים הוציא את כל 15 כליו"""
        return self.white_off == 15 or self.black_off == 15

    def get_game_status_hebrew(self) -> Tuple[str, bool, int]:
        """
        מחזיר (סטטוס, האם הסתיים, נקודות ניצחון 1/2/3).
        ניקוד:
        - 1 נקודה: ניצחון רגיל (היריב הוציא לפחות כלי אחד).
        - 2 נקודות: מארס (Gammon) – היריב לא הוציא אף כלי!
        - 3 נקודות: מארס טורקי (Backgammon) – היריב לא הוציא אף כלי ועדיין יש לו כלי בבר או בבית המנצח!
        """
        if self.white_off == 15:
            # לבן ניצח - בדיקת סוג ניצחון
            if self.black_off > 0:
                return "ניצחון רגיל ללבן! (נקודה 1)", True, 1
            # היריב לא הוציא כלים: בדיקה אם מארס טורקי
            has_in_white_home_or_bar = (self.black_bar > 0) or any(self.points[pt] < 0 for pt in range(1, 7))
            if has_in_white_home_or_bar:
                return "מארס טורקי ללבן! (Backgammon - 3 נקודות)", True, 3
            return "מארס ללבן! (Gammon - 2 נקודות)", True, 2

        if self.black_off == 15:
            if self.white_off > 0:
                return "ניצחון רגיל לשחור! (נקודה 1)", True, 1
            has_in_black_home_or_bar = (self.white_bar > 0) or any(self.points[pt] > 0 for pt in range(19, 25))
            if has_in_black_home_or_bar:
                return "מארס טורקי לשחור! (Backgammon - 3 נקודות)", True, 3
            return "מארס לשחור! (Gammon - 2 נקודות)", True, 2

        turn_name = self.get_turn_name_hebrew()
        if not self.current_dice:
            return f"תור ה{turn_name} – נא להטיל קוביות", False, 0
        rem_str = ", ".join(map(str, self.remaining_moves)) if self.remaining_moves else "אין"
        return f"תור ה{turn_name} • קוביות: {self.current_dice} • מהלכים שנותרו: {rem_str}", False, 0

    def get_state_string(self) -> str:
        """מחרוזת סנכרון לשיטס עבור לוח שש-בש"""
        pts_str = ",".join(str(p) for p in self.points[1:25])
        bars = f"{self.white_bar},{self.black_bar}"
        offs = f"{self.white_off},{self.black_off}"
        d_str = ",".join(str(d) for d in self.current_dice)
        rem_str = ",".join(str(r) for r in self.remaining_moves)
        t_str = "W" if self.turn == COLOR_WHITE else "B"
        return f"{pts_str}|{bars}|{offs}|{d_str}|{rem_str}|{t_str}"

    def load_from_state_string(self, s: str):
        """טעינת מצב לוח שש-בש ממחרוזת סנכרון"""
        try:
            parts = s.split("|")
            pts = list(map(int, parts[0].split(",")))
            for i, val in enumerate(pts):
                self.points[i + 1] = val

            bars = list(map(int, parts[1].split(",")))
            self.white_bar, self.black_bar = bars[0], bars[1]

            offs = list(map(int, parts[2].split(",")))
            self.white_off, self.black_off = offs[0], offs[1]

            self.current_dice = list(map(int, parts[3].split(","))) if parts[3] else []
            self.remaining_moves = list(map(int, parts[4].split(","))) if parts[4] else []
            self.turn = COLOR_WHITE if parts[5] == "W" else COLOR_BLACK
        except Exception:
            pass
