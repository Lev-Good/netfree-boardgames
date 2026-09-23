# -*- coding: utf-8 -*-
"""
מנוע לוגיקת שחמט - ניהול חוקי משחק, ניקוד והיסטוריה
מבוסס על ספריית python-chess.
"""

from typing import List, Dict, Tuple, Optional, Any
import chess
import chess.pgn
import datetime
import io

# ערכי כלים סטנדרטיים לצורך חישוב ניקוד והפרש כלים
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0
}

# סמלי יוניקוד עבור הכלים
PIECE_SYMBOLS_UNICODE = {
    'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
}


def format_clock_time(seconds: Optional[int]) -> str:
    """מעצב שניות למחרוזת שעון דיגיטלית כגון 05:00 או 10:35"""
    if seconds is None:
        return "--:--"
    if seconds < 0:
        seconds = 0
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"


class MoveRecord:

    def __init__(self, move_num: int, uci: str, san: str, fen_after: str, player_name: str, color: str):
        self.move_num = move_num
        self.uci = uci
        self.san = san
        self.fen_after = fen_after
        self.player_name = player_name
        self.color = color  # "W" or "B"
        self.timestamp = datetime.datetime.now().strftime("%H:%M:%S")


class ChessEngine:
    def __init__(self):
        self.board = chess.Board()
        self.history: List[MoveRecord] = []
        self.review_move_index: Optional[int] = None  # לצורך דפדוף בהיסטוריה

    def reset(self):
        """איפוס המשחק למצב התחלתי"""
        self.board.reset()
        self.history.clear()
        self.review_move_index = None

    def get_turn(self) -> chess.Color:
        """מחזיר את התור הנוכחי: chess.WHITE או chess.BLACK"""
        return self.board.turn

    def is_white_turn(self) -> bool:
        return self.board.turn == chess.WHITE

    def get_turn_name_hebrew(self) -> str:
        return "לבן" if self.board.turn == chess.WHITE else "שחור"

    def get_legal_moves_for_square(self, square: int) -> List[int]:
        """מחזיר את כל משבצות היעד החוקיות עבור כלי במשבצת נתונה"""
        destinations = []
        for move in self.board.legal_moves:
            if move.from_square == square:
                destinations.append(move.to_square)
        return destinations

    def is_promotion(self, from_sq: int, to_sq: int) -> bool:
        """בודק האם מהלך זה מהווה הכתרת רגלי"""
        piece = self.board.piece_at(from_sq)
        if not piece or piece.piece_type != chess.PAWN:
            return False
        dest_rank = chess.square_rank(to_sq)
        return (piece.color == chess.WHITE and dest_rank == 7) or (piece.color == chess.BLACK and dest_rank == 0)

    def push_move(self, uci_or_move, player_name: str = "") -> Tuple[bool, Optional[str], Optional[str]]:
        """
        ביצוע מהלך בלוח.
        מקבל uci_str (למשל 'e2e4') או אובייקט chess.Move.
        מחזיר (הצלחה, SAN של המהלך, הודעת שגיאה).
        """
        try:
            if isinstance(uci_or_move, str):
                move = chess.Move.from_uci(uci_or_move)
            else:
                move = uci_or_move

            if move not in self.board.legal_moves:
                # בדיקה אם זו הכתרה שלא צוין בה כלי (ברירת מחדל מלכה)
                if self.is_promotion(move.from_square, move.to_square) and not move.promotion:
                    move = chess.Move(move.from_square, move.to_square, promotion=chess.QUEEN)

                if move not in self.board.legal_moves:
                    return False, None, f"המהלך {move.uci()} אינו חוקי במצב הלוח הנוכחי."

            # שמירת ה-SAN לפני ביצוע המהלך
            san = self.board.san(move)
            color_str = "W" if self.board.turn == chess.WHITE else "B"
            move_num = len(self.history) + 1

            self.board.push(move)

            record = MoveRecord(
                move_num=move_num,
                uci=move.uci(),
                san=san,
                fen_after=self.board.fen(),
                player_name=player_name,
                color=color_str
            )
            self.history.append(record)
            self.review_move_index = None  # חזרה למהלך האחרון

            return True, san, None

        except Exception as e:
            return False, None, str(e)

    def pop_last_move(self) -> Tuple[bool, Optional[str]]:
        """ביטול המהלך האחרון (Takeback) והחזרת הלוח וההיסטוריה צעד אחד אחורה"""
        try:
            if self.board.move_stack:
                self.board.pop()
                popped_record = self.history.pop() if self.history else None
                san = popped_record.san if popped_record else None
                return True, san
        except Exception:
            pass
        return False, None

    def is_game_over(self) -> bool:
        return self.board.is_game_over(claim_draw=True)

    def get_game_status_hebrew(self) -> Tuple[str, bool]:
        """
        מחזיר תיאור מצב המשחק בעברית והאם המשחק הסתיים.
        (הודעה, האם הסתיים)
        """
        if self.board.is_checkmate():
            winner = "שחור" if self.board.turn == chess.WHITE else "לבן"
            return f"מט! ניצחון ל{winner}!", True

        if self.board.is_stalemate():
            return "תיקו עקב פט (Stalemate)!", True

        if self.board.is_insufficient_material():
            return "תיקו עקב חוסר בחומר מספיק למט!", True

        if self.board.is_fivefold_repetition() or self.board.is_seventyfive_moves():
            return "תיקו אוטומטי (חוק 75 מסעים / חזרה מחומשת)!", True

        if self.board.can_claim_threefold_repetition():
            return "תיקו! הושגה חזרה משולשת על מסעים!", True

        if self.board.can_claim_fifty_moves():
            return "תיקו! הופעל חוק 50 המסעים ללא הכאה/רגלי!", True

        if self.board.is_check():
            turn = self.get_turn_name_hebrew()
            return f"שח על ה{turn}!", False

        turn = self.get_turn_name_hebrew()
        return f"תור ה{turn}", False

    def calculate_material_and_captures(self) -> Dict[str, Any]:
        """
        מחשב ניקוד חומר וכלים שנאכלו עבור שני הצדדים.
        """
        # הרכב כלים התחלתי
        starting_pieces = {
            chess.PAWN: 8,
            chess.KNIGHT: 2,
            chess.BISHOP: 2,
            chess.ROOK: 2,
            chess.QUEEN: 1
        }

        white_current = {t: 0 for t in starting_pieces}
        black_current = {t: 0 for t in starting_pieces}

        for sq in chess.SQUARES:
            piece = self.board.piece_at(sq)
            if piece and piece.piece_type in starting_pieces:
                if piece.color == chess.WHITE:
                    white_current[piece.piece_type] += 1
                else:
                    black_current[piece.piece_type] += 1

        white_material = sum(white_current[t] * PIECE_VALUES[t] for t in starting_pieces)
        black_material = sum(black_current[t] * PIECE_VALUES[t] for t in starting_pieces)

        # כלים ששחקן לבן לקח (כלומר חסרים לשחור)
        captured_by_white = []
        for t, count in starting_pieces.items():
            missing = max(0, count - black_current[t])
            sym = PIECE_SYMBOLS_UNICODE[chess.Piece(t, chess.BLACK).symbol()]
            captured_by_white.extend([sym] * missing)

        # כלים ששחקן שחור לקח (חסרים ללבן)
        captured_by_black = []
        for t, count in starting_pieces.items():
            missing = max(0, count - white_current[t])
            sym = PIECE_SYMBOLS_UNICODE[chess.Piece(t, chess.WHITE).symbol()]
            captured_by_black.extend([sym] * missing)

        diff = white_material - black_material

        return {
            "white_material": white_material,
            "black_material": black_material,
            "diff": diff,  # >0 יתרון ללבן, <0 יתרון לשחור
            "captured_by_white": "".join(captured_by_white),
            "captured_by_black": "".join(captured_by_black)
        }

    def get_paired_history(self) -> List[Dict[str, Any]]:
        """מחזיר היסטוריית מהלכים מקובצת לפי מספרי תור: 1. e4 e5"""
        pairs = []
        current_pair = {}

        for rec in self.history:
            if rec.color == "W":
                turn_num = (rec.move_num + 1) // 2
                current_pair = {
                    "turn": turn_num,
                    "white": rec.san,
                    "white_fen": rec.fen_after,
                    "black": "",
                    "black_fen": ""
                }
                pairs.append(current_pair)
            else:
                if current_pair and current_pair.get("black") == "":
                    current_pair["black"] = rec.san
                    current_pair["black_fen"] = rec.fen_after
                else:
                    turn_num = rec.move_num // 2
                    pairs.append({
                        "turn": turn_num,
                        "white": "...",
                        "white_fen": "",
                        "black": rec.san,
                        "black_fen": rec.fen_after
                    })
        return pairs

    def export_pgn(self, white_player: str = "Player 1", black_player: str = "Player 2", event: str = "NetFree Chess") -> str:
        """מייצא את המשחק לפורמט PGN תקני לצורך שמירה ושיתוף"""
        game = chess.pgn.Game()
        game.headers["Event"] = event
        game.headers["Site"] = "Google Sheets NetFree Platform"
        game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        game.headers["White"] = white_player
        game.headers["Black"] = black_player

        status_text, is_over = self.get_game_status_hebrew()
        if self.board.is_checkmate():
            game.headers["Result"] = "0-1" if self.board.turn == chess.WHITE else "1-0"
        elif is_over:
            game.headers["Result"] = "1/2-1/2"
        else:
            game.headers["Result"] = "*"

        # שחזור המהלכים על ה-PGN
        temp_board = chess.Board()
        node = game
        for rec in self.history:
            move = chess.Move.from_uci(rec.uci)
            node = node.add_variation(move)
            temp_board.push(move)

        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        return game.accept(exporter)

    def load_from_fen(self, fen: str):
        """טוען מצב לוח מתוך FEN"""
        self.board.set_fen(fen)
