# -*- coding: utf-8 -*-
"""
מנוע לוגיקת דמקה קלאסית / ישראלית - תומך בלוח 8x8, חוקי אכילת חובה,
שרשרת אכילות רצופה, והכתרת דמקה (מלכה מעופפת).
"""

from typing import List, Dict, Tuple, Optional, Any
import copy

# קבועי שחקנים וכלים
EMPTY = 0
WHITE_MAN = 1
WHITE_KING = 2
BLACK_MAN = -1
BLACK_KING = -2

COLOR_WHITE = 1
COLOR_BLACK = -1


class CheckersMove:
    def __init__(self, from_sq: int, to_sq: int, captures: Optional[List[int]] = None, path: Optional[List[int]] = None):
        self.from_sq = from_sq
        self.to_sq = to_sq
        self.captures = captures or []  # משבצות של הכלים שנאכלו
        self.path = path or [from_sq, to_sq]  # מסלול הדילוגים באכילה מרובה

    def is_capture(self) -> bool:
        return len(self.captures) > 0

    def to_uci(self) -> str:
        f_name = square_to_coord(self.from_sq)
        t_name = square_to_coord(self.to_sq)
        return f"{f_name}{t_name}"

    def __repr__(self):
        f = square_to_coord(self.from_sq)
        t = square_to_coord(self.to_sq)
        sep = "x" if self.is_capture() else "-"
        return f"{f}{sep}{t}"


def square_to_coord(sq: int) -> str:
    """ממיר אינדקס 0-63 לקואורדינטת לוח כגון a3, b4"""
    r = sq // 8
    f = sq % 8
    return f"{chr(ord('a') + f)}{r + 1}"


def coord_to_square(coord: str) -> Optional[int]:
    """ממיר קואורדינטה כגון a3 לאינדקס 0-63"""
    if len(coord) != 2:
        return None
    f = ord(coord[0].lower()) - ord('a')
    r = int(coord[1]) - 1
    if 0 <= f < 8 and 0 <= r < 8:
        return r * 8 + f
    return None


class CheckersEngine:
    def __init__(self):
        self.board: List[int] = [EMPTY] * 64
        self.turn: int = COLOR_WHITE  # 1 = White, -1 = Black
        self.history: List[Dict[str, Any]] = []
        self.reset()

    def reset(self):
        """אתחול לוח דמקה 8x8 קלאסי: 12 כלים לכל שחקן על המשבצות השחורות"""
        self.board = [EMPTY] * 64
        self.turn = COLOR_WHITE
        self.history.clear()

        # שורות 0, 1, 2: כלים לבנים (תחתית הלוח)
        for r in range(3):
            for f in range(8):
                if (r + f) % 2 != 0:  # משבצת כהה
                    self.board[r * 8 + f] = WHITE_MAN

        # שורות 5, 6, 7: כלים שחורים (ראש הלוח)
        for r in range(5, 8):
            for f in range(8):
                if (r + f) % 2 != 0:  # משבצת כהה
                    self.board[r * 8 + f] = BLACK_MAN

    def get_piece(self, sq: int) -> int:
        if 0 <= sq < 64:
            return self.board[sq]
        return EMPTY

    def is_white_turn(self) -> bool:
        return self.turn == COLOR_WHITE

    def get_turn_name_hebrew(self) -> str:
        return "לבן" if self.turn == COLOR_WHITE else "שחור"

    def get_legal_moves(self) -> List[CheckersMove]:
        """
        חישוב כל המסעים החוקיים של השחקן שתורו כעת.
        אם יש אכילה אפשרית – חובת אכילה (מותרים רק מסעי אכילה!).
        """
        capture_moves: List[CheckersMove] = []
        regular_moves: List[CheckersMove] = []

        for sq in range(64):
            piece = self.board[sq]
            if piece == EMPTY:
                continue

            # בדיקה האם הכלי שייך לשחקן הנוכחי
            if (self.turn == COLOR_WHITE and piece > 0) or (self.turn == COLOR_BLACK and piece < 0):
                caps = self._get_captures_for_square(sq, self.board)
                if caps:
                    capture_moves.extend(caps)
                else:
                    regs = self._get_regular_moves_for_square(sq)
                    regular_moves.extend(regs)

        # חוק אכילה חובה: אם קיימות אכילות, מחזירים אך ורק אותן
        if capture_moves:
            # מציאת האכילות הארוכות ביותר (אם רוצים אכילה מקסימלית) או כל האכילות
            return capture_moves

        return regular_moves

    def _get_regular_moves_for_square(self, sq: int) -> List[CheckersMove]:
        """תנועה רגילה באלכסון (צעד 1 לחייל, מרחק בלתי מוגבל לדמקה/מלכה)"""
        moves = []
        piece = self.board[sq]
        r = sq // 8
        f = sq % 8

        # כיווני תנועה: חייל לבן עולה (+1), חייל שחור יורד (-1), דמקה לשני הכיוונים
        directions = []
        if piece == WHITE_MAN:
            directions = [(1, -1), (1, 1)]
        elif piece == BLACK_MAN:
            directions = [(-1, -1), (-1, 1)]
        elif abs(piece) == WHITE_KING:  # דמקה
            directions = [(1, -1), (1, 1), (-1, -1), (-1, 1)]

        is_king = abs(piece) == WHITE_KING

        for dr, df in directions:
            nr = r + dr
            nf = f + df
            if is_king:
                # מלכה מעופפת: צועדת לכל אורך האלכסון עד שנתקלת בכלי או בקצה
                while 0 <= nr < 8 and 0 <= nf < 8:
                    dest_sq = nr * 8 + nf
                    if self.board[dest_sq] == EMPTY:
                        moves.append(CheckersMove(sq, dest_sq))
                    else:
                        break
                    nr += dr
                    nf += df
            else:
                # חייל רגיל: צעד בודד
                if 0 <= nr < 8 and 0 <= nf < 8:
                    dest_sq = nr * 8 + nf
                    if self.board[dest_sq] == EMPTY:
                        moves.append(CheckersMove(sq, dest_sq))

        return moves

    def _get_captures_for_square(self, sq: int, current_board: List[int]) -> List[CheckersMove]:
        """מחשב את כל מסלולי האכילה הרצופים עבור כלי נתון (רקורסיה לשרשרת אכילות)"""
        piece = current_board[sq]
        r = sq // 8
        f = sq % 8
        is_king = abs(piece) == WHITE_KING
        player_color = COLOR_WHITE if piece > 0 else COLOR_BLACK

        results: List[CheckersMove] = []

        directions = [(1, -1), (1, 1), (-1, -1), (-1, 1)]

        for dr, df in directions:
            if not is_king:
                # חייל רגיל קופץ מעל יריב סמוך למשבצת הריקה שמעברו
                mid_r = r + dr
                mid_f = f + df
                end_r = r + 2 * dr
                end_f = f + 2 * df

                if 0 <= end_r < 8 and 0 <= end_f < 8:
                    mid_sq = mid_r * 8 + mid_f
                    end_sq = end_r * 8 + end_f
                    mid_piece = current_board[mid_sq]

                    # האם הכלי שבאמצע שייך ליריב והמשבצת שאחריו ריקה
                    if mid_piece != EMPTY and ((player_color == COLOR_WHITE and mid_piece < 0) or (player_color == COLOR_BLACK and mid_piece > 0)):
                        if current_board[end_sq] == EMPTY:
                            # ביצוע סימולציה של האכילה
                            new_b = list(current_board)
                            new_b[sq] = EMPTY
                            new_b[mid_sq] = EMPTY

                            # בדיקת הכתרה לדמקה באמצע שרשרת אכילות
                            promoted = (player_color == COLOR_WHITE and end_r == 7) or (player_color == COLOR_BLACK and end_r == 0)
                            new_b[end_sq] = (player_color * WHITE_KING) if promoted else piece

                            # בדיקה האם יש המשך אכילה מהמשבצת החדשה
                            further = self._get_captures_for_square(end_sq, new_b)
                            if further:
                                for f_move in further:
                                    results.append(CheckersMove(
                                        from_sq=sq,
                                        to_sq=f_move.to_sq,
                                        captures=[mid_sq] + f_move.captures,
                                        path=[sq] + f_move.path
                                    ))
                            else:
                                results.append(CheckersMove(
                                    from_sq=sq,
                                    to_sq=end_sq,
                                    captures=[mid_sq],
                                    path=[sq, end_sq]
                                ))
            else:
                # דמקה מעופפת: יכולה לצלוח מרחק באלכסון, לאכול כלי יריב, ולנחות בכל משבצת ריקה לאחריו
                step = 1
                found_opp = None
                while True:
                    cur_r = r + step * dr
                    cur_f = f + step * df
                    if not (0 <= cur_r < 8 and 0 <= cur_f < 8):
                        break
                    cur_sq = cur_r * 8 + cur_f
                    cur_piece = current_board[cur_sq]

                    if found_opp is None:
                        if cur_piece == EMPTY:
                            step += 1
                            continue
                        elif (player_color == COLOR_WHITE and cur_piece > 0) or (player_color == COLOR_BLACK and cur_piece < 0):
                            # כלי משלנו חוסם
                            break
                        else:
                            # מצאנו כלי יריב שניתן לאכול
                            found_opp = cur_sq
                            step += 1
                            continue
                    else:
                        # כבר מצאנו כלי יריב, כעת כל משבצת ריקה היא נחיתה אפשרית
                        if cur_piece == EMPTY:
                            new_b = list(current_board)
                            new_b[sq] = EMPTY
                            new_b[found_opp] = EMPTY
                            new_b[cur_sq] = piece

                            further = self._get_captures_for_square(cur_sq, new_b)
                            if further:
                                for f_move in further:
                                    results.append(CheckersMove(
                                        from_sq=sq,
                                        to_sq=f_move.to_sq,
                                        captures=[found_opp] + f_move.captures,
                                        path=[sq] + f_move.path
                                    ))
                            else:
                                results.append(CheckersMove(
                                    from_sq=sq,
                                    to_sq=cur_sq,
                                    captures=[found_opp],
                                    path=[sq, cur_sq]
                                ))
                            step += 1
                        else:
                            # נתקלנו בכלי נוסף שחוסם נחיתה
                            break

        return results

    def push_move(self, uci_or_move: Any, player_name: str = "") -> Tuple[bool, Optional[str], Optional[str]]:
        """
        ביצוע מהלך בלוח הדמקה.
        מקבל מחרוזת UCI כגון 'c3d4' או אובייקט CheckersMove.
        """
        legal_moves = self.get_legal_moves()
        if not legal_moves:
            return False, None, "אין מסעים חוקיים. המשחק הסתיים!"

        chosen_move: Optional[CheckersMove] = None

        if isinstance(uci_or_move, str):
            uci_str = uci_or_move.strip().lower()
            if len(uci_str) == 4:
                from_sq = coord_to_square(uci_str[:2])
                to_sq = coord_to_square(uci_str[2:])
                for lm in legal_moves:
                    if lm.from_sq == from_sq and lm.to_sq == to_sq:
                        chosen_move = lm
                        break
        elif isinstance(uci_or_move, CheckersMove):
            for lm in legal_moves:
                if lm.from_sq == uci_or_move.from_sq and lm.to_sq == uci_or_move.to_sq:
                    chosen_move = lm
                    break

        if not chosen_move:
            has_captures = any(m.is_capture() for m in legal_moves)
            if has_captures:
                return False, None, "מהלך לא חוקי: חובת אכילה קיימת!"
            return False, None, "מהלך לא חוקי!"

        # שמירת מצב קודם להיסטוריה
        state_record = {
            "board": list(self.board),
            "turn": self.turn,
            "move": chosen_move,
            "player": player_name,
            "fen": self.get_state_string()
        }
        self.history.append(state_record)

        # 1. הזזת הכלי
        moving_piece = self.board[chosen_move.from_sq]
        self.board[chosen_move.from_sq] = EMPTY

        # 2. הסרת כלים שנאכלו
        for cap_sq in chosen_move.captures:
            self.board[cap_sq] = EMPTY

        # 3. בדיקת הכתרה לדמקה (מלכה)
        dest_rank = chosen_move.to_sq // 8
        if moving_piece == WHITE_MAN and dest_rank == 7:
            moving_piece = WHITE_KING
        elif moving_piece == BLACK_MAN and dest_rank == 0:
            moving_piece = BLACK_KING

        self.board[chosen_move.to_sq] = moving_piece

        # 4. העברת תור
        self.turn = COLOR_BLACK if self.turn == COLOR_WHITE else COLOR_WHITE

        san_str = str(chosen_move)
        return True, san_str, None

    def pop_last_move(self) -> Tuple[bool, Optional[str]]:
        """ביטול מהלך אחרון (Takeback)"""
        if not self.history:
            return False, None
        last_state = self.history.pop()
        self.board = last_state["board"]
        self.turn = last_state["turn"]
        move = last_state.get("move")
        return True, str(move) if move else None

    def is_game_over(self) -> bool:
        """המשחק מסתיים אם לאחד השחקנים נגמרו הכלים או אין לו שום מהלך חוקי"""
        white_count = sum(1 for p in self.board if p > 0)
        black_count = sum(1 for p in self.board if p < 0)
        if white_count == 0 or black_count == 0:
            return True
        return len(self.get_legal_moves()) == 0

    def get_game_status_hebrew(self) -> Tuple[str, bool]:
        """מחזיר סטטוס משחק והאם המשחק הסתיים"""
        white_count = sum(1 for p in self.board if p > 0)
        black_count = sum(1 for p in self.board if p < 0)

        if white_count == 0:
            return "ניצחון לשחור! ללבן לא נותרו כלים.", True
        if black_count == 0:
            return "ניצחון ללבן! לשחור לא נותרו כלים.", True

        legal = self.get_legal_moves()
        if not legal:
            winner = "שחור" if self.turn == COLOR_WHITE else "לבן"
            loser = "הלבן" if self.turn == COLOR_WHITE else "השחור"
            return f"ניצחון ל{winner}! ל{loser} אין מסעים חוקיים.", True

        has_captures = any(m.is_capture() for m in legal)
        turn_str = "לבן" if self.turn == COLOR_WHITE else "שחור"
        if has_captures:
            return f"תור ה{turn_str} (חובת אכילה!)", False
        return f"תור ה{turn_str}", False

    def calculate_material(self) -> Dict[str, Any]:
        """חישוב מספר כלים ודמקאות לכל צד"""
        white_men = sum(1 for p in self.board if p == WHITE_MAN)
        white_kings = sum(1 for p in self.board if p == WHITE_KING)
        black_men = sum(1 for p in self.board if p == BLACK_MAN)
        black_kings = sum(1 for p in self.board if p == BLACK_KING)

        white_total = white_men + white_kings * 3
        black_total = black_men + black_kings * 3

        return {
            "white_men": white_men,
            "white_kings": white_kings,
            "white_count": white_men + white_kings,
            "black_men": black_men,
            "black_kings": black_kings,
            "black_count": black_men + black_kings,
            "diff": white_total - black_total
        }

    def get_state_string(self) -> str:
        """מחרוזת FEN-like המייצגת את מצב לוח הדמקה"""
        res = []
        for p in self.board:
            if p == EMPTY:
                res.append(".")
            elif p == WHITE_MAN:
                res.append("w")
            elif p == WHITE_KING:
                res.append("W")
            elif p == BLACK_MAN:
                res.append("b")
            elif p == BLACK_KING:
                res.append("B")
        t = "W" if self.turn == COLOR_WHITE else "B"
        return f"{''.join(res)}:{t}"

    def load_from_state_string(self, state_str: str):
        """טעינת מצב לוח ממחרוזת"""
        parts = state_str.split(":")
        b_str = parts[0]
        t_str = parts[1] if len(parts) > 1 else "W"

        mapping = {'.': EMPTY, 'w': WHITE_MAN, 'W': WHITE_KING, 'b': BLACK_MAN, 'B': BLACK_KING}
        for i, char in enumerate(b_str[:64]):
            self.board[i] = mapping.get(char, EMPTY)
        self.turn = COLOR_WHITE if t_str == "W" else COLOR_BLACK
