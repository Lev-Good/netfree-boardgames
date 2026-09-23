# -*- coding: utf-8 -*-
"""
מודול סנכרון שחמט מתקדם דרך Google Sheets API בנטפרי
כולל:
- ניהול חדרים בריבוי משחקים (לשונית ייעודית לכל חדר Room_XXXX)
- לובי משחקים מרכזי ומציאת יריבים (Lobby)
- צ'אט חי בתוך המשחק (Chat_XXXX)
- קוד הזמנה חכם (Smart Invite Code)
- סנכרון מלא של תיקו, כניעה, החזרת מהלך (Takeback) ושעונים.
"""

import datetime
import re
from typing import List, Dict, Any, Optional, Tuple
from google_sheets_client import GoogleSheetsClient, extract_spreadsheet_id

CHESS_MOVE_HEADERS = [
    "MoveNum",      # מספר המהלך (1, 2, 3...)
    "Player",       # שם השחקן
    "Color",        # צבע (W או B)
    "MoveUCI",      # מהלך בפורמט UCI (למשל e2e4)
    "MoveSAN",      # מהלך בפורמט שחמט (למשל e4, Nf3)
    "Fen",          # מצב הלוח בפורמט FEN
    "Timestamp",    # שעת המהלך
    "Action"        # סטטוס מיוחד: MOVE, CHECK, CHECKMATE
]

LOBBY_HEADERS = [
    "RoomId",        # מזהה החדר (למשל Room_1234)
    "HostPlayer",    # שם השחקן המזמין
    "TimeControl",   # בקרת זמן (None / 5m / 10m / 15m)
    "HostColor",     # צבע המזמין (W / B / RANDOM)
    "SpreadsheetId", # מזהה הגיליון של המארח
    "Status",        # WAITING / ACTIVE / CLOSED
    "CreatedAt"      # שעת יצירה
]

CHAT_HEADERS = [
    "MsgId",         # מספר הודעה רץ
    "Timestamp",     # שעה
    "Sender",        # שם השולח
    "Color",         # צבע (W או B או SPEC)
    "Message"        # תוכן ההודעה
]


def encode_invite_code(spreadsheet_id: str, room_id: str, game_type: str = "CHESS") -> str:
    """יוצר קוד הזמנה חכם וקצר לשיתוף מהיר עם חבר עבור כל סוג משחק"""
    clean_id = extract_spreadsheet_id(spreadsheet_id)
    clean_room = room_id.strip()
    clean_game = game_type.strip().upper()
    return f"NETFREE#{clean_id}#{clean_game}#{clean_room}"


def decode_invite_code(invite_text: str) -> Tuple[Optional[str], Optional[str], str]:
    """
    מפענח קוד הזמנה חכם ומחזיר (spreadsheet_id, room_id, game_type).
    תומך בפורמט מורחב (4 חלקים) ובפורמט קלאסי (3 חלקים).
    """
    text = (invite_text or "").strip()
    if text.startswith("NETFREE#"):
        parts = text.split("#")
        if len(parts) >= 4:
            return parts[1].strip(), parts[3].strip(), parts[2].strip().upper()
        elif len(parts) == 3:
            return parts[1].strip(), parts[2].strip(), "CHESS"

    # בדיקה לתבנית כללית של ID וחדר
    parts = re.split(r'[:#|]', text)
    if len(parts) == 3:
        return parts[0].strip(), parts[2].strip(), parts[1].strip().upper()
    elif len(parts) == 2:
        return parts[0].strip(), parts[1].strip(), "CHESS"

    return None, None, "CHESS"


class ChessSyncManager:
    def __init__(self, sheets_client: GoogleSheetsClient):
        self.client = sheets_client

    # ------------------ ניהול חדר משחק (Room_XXXX) ------------------

    def get_room_tab_name(self, room_id: str) -> str:
        r = room_id.strip()
        if not r.startswith("Room_") and not r.startswith("CHESS-"):
            return f"Room_{r}"
        return r.replace("-", "_")

    def get_chat_tab_name(self, room_id: str) -> str:
        r_tab = self.get_room_tab_name(room_id)
        return r_tab.replace("Room_", "Chat_")

    def create_room(
        self,
        spreadsheet_id: str,
        room_id: str,
        host_name: str,
        host_color: str = "W",
        time_control: str = "NONE"
    ) -> Tuple[bool, str]:
        """יוצר לשונית חדר חדשה בגיליון עם שורת Metadata וכותרות מהלכים"""
        try:
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            room_tab = self.get_room_tab_name(room_id)
            curr_time = datetime.datetime.now().strftime("%H:%M:%S")

            # 1. יצירת לשונית החדר אם אינה קיימת
            self.client.ensure_sheet_tab_exists(clean_id, room_tab)

            # 2. שורת Metadata (שורה 1)
            meta_row = [
                "ROOM_META",
                room_tab,
                host_name.strip(),
                "",                 # guest_name עדיין ריק
                host_color,
                time_control,
                "WAITING",          # סטטוס חדר: WAITING / ACTIVE / FINISHED
                "NONE",             # סטטוס פעולה: NONE / DRAW_OFFER_W / וכו'
                curr_time
            ]

            # 3. שורת כותרות מהלכים (שורה 2)
            body = {
                'values': [
                    meta_row,
                    CHESS_MOVE_HEADERS
                ]
            }

            service = self.client.get_service()
            service.spreadsheets().values().update(
                spreadsheetId=clean_id,
                range=f"'{room_tab}'!A1:I2",
                valueInputOption="USER_ENTERED",
                body=body
            ).execute()

            # יצירת לשונית צ'אט במקביל
            self.ensure_chat_tab(clean_id, room_id)

            return True, "החדר נוצר בהצלחה!"
        except Exception as e:
            return False, str(e)

    def join_room(self, spreadsheet_id: str, room_id: str, guest_name: str) -> Tuple[bool, Dict[str, Any], str]:
        """הצטרפות שחקן מוזמן לחדר קיים: קריאת נתוני המארח ועדכון שמו של האורח"""
        try:
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            room_tab = self.get_room_tab_name(room_id)

            # קריאת שורת ה-Metadata
            success, rows, err = self.client.read_sheet(clean_id, room_tab, "A1:I1")
            if not success or not rows or not rows[0]:
                return False, {}, f"החדר {room_tab} לא נמצא בגיליון. ודא שהמארח פתח אותו."

            meta = rows[0]
            host_name = meta[2] if len(meta) > 2 else "מארח"
            host_color = meta[4] if len(meta) > 4 else "W"
            time_control = meta[5] if len(meta) > 5 else "NONE"

            # הקצאת צבע נגדי לאורח
            guest_color = "B" if host_color == "W" else "W"

            # עדכון שורת ה-Metadata עם פרטי האורח ומצב ACTIVE
            meta[3] = guest_name.strip()
            meta[6] = "ACTIVE"

            service = self.client.get_service()
            service.spreadsheets().values().update(
                spreadsheetId=clean_id,
                range=f"'{room_tab}'!A1:I1",
                valueInputOption="USER_ENTERED",
                body={'values': [meta]}
            ).execute()

            self.ensure_chat_tab(clean_id, room_id)

            room_info = {
                "room_id": room_tab,
                "host_name": host_name,
                "host_color": host_color,
                "guest_name": guest_name,
                "guest_color": guest_color,
                "time_control": time_control
            }
            return True, room_info, ""
        except Exception as e:
            return False, {}, str(e)

    def read_room_meta(self, spreadsheet_id: str, room_id: str) -> Tuple[bool, Dict[str, Any], str]:
        """קריאת מצב ה-Metadata של חדר (זיהוי הצטרפות יריב, הצעת תיקו וכו')"""
        try:
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            room_tab = self.get_room_tab_name(room_id)
            success, rows, err = self.client.read_sheet(clean_id, room_tab, "A1:I1")
            if not success or not rows or not rows[0]:
                return False, {}, "לא נמצא חדר"

            meta = rows[0]
            info = {
                "room_id": meta[1] if len(meta) > 1 else room_tab,
                "host_player": meta[2] if len(meta) > 2 else "",
                "guest_player": meta[3] if len(meta) > 3 else "",
                "host_color": meta[4] if len(meta) > 4 else "W",
                "time_control": meta[5] if len(meta) > 5 else "NONE",
                "game_status": meta[6] if len(meta) > 6 else "WAITING",
                "action_status": meta[7] if len(meta) > 7 else "NONE",
                "created_at": meta[8] if len(meta) > 8 else ""
            }
            return True, info, ""
        except Exception as e:
            return False, {}, str(e)

    def update_action_status(self, spreadsheet_id: str, room_id: str, action_status: str, game_status: Optional[str] = None) -> bool:
        """עדכון סטטוס פעולה (תיקו, כניעה, החזרת מהלך) ב-Metadata"""
        try:
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            room_tab = self.get_room_tab_name(room_id)
            success, rows, _ = self.client.read_sheet(clean_id, room_tab, "A1:I1")
            if success and rows and rows[0]:
                meta = rows[0]
                while len(meta) < 8:
                    meta.append("")
                meta[7] = action_status
                if game_status:
                    meta[6] = game_status

                service = self.client.get_service()
                service.spreadsheets().values().update(
                    spreadsheetId=clean_id,
                    range=f"'{room_tab}'!A1:I1",
                    valueInputOption="USER_ENTERED",
                    body={'values': [meta]}
                ).execute()
                return True
        except Exception:
            pass
        return False

    def send_special_action(
        self,
        spreadsheet_id: str,
        room_id: str,
        player_name: str,
        color: str,
        action: str
    ) -> Tuple[bool, str]:
        """שליחת פעולה מיוחדת (כניעה, בקשת תיקו, בקשת החזרת מהלך וכו')"""
        clean_id = extract_spreadsheet_id(spreadsheet_id)
        room_tab = self.get_room_tab_name(room_id)
        action_val = f"{action}_{color}" if "_" not in action else action
        game_status = "FINISHED" if "RESIGN" in action else None

        updated = self.update_action_status(clean_id, room_id, action_val, game_status)
        if not updated:
            # אם החדר לא קיים ב-Metadata (למשל לשונית ישנה ChessMoves), ננסה לכתוב שורה
            curr_time = datetime.datetime.now().strftime("%H:%M:%S")
            row = ["0", player_name, color, "", "", "", curr_time, action]
            success, res, _ = self.client.write_row(clean_id, room_tab, row)
            return success, str(res)
        return True, "הפעולה עודכנה"

    def remove_last_moves(self, spreadsheet_id: str, room_id: str, count: int = 1) -> bool:
        """מוחק את שורות המהלכים האחרונים מהגיליון לצורך החזרת מהלך נקייה (Takeback)"""
        try:
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            room_tab = self.get_room_tab_name(room_id)
            success, rows, _ = self.client.read_sheet(clean_id, room_tab, "A3:H150")
            if not success or not rows:
                return True

            total_moves = len(rows)
            if total_moves == 0:
                return True

            start_row = max(3, 2 + total_moves - count + 1)
            end_row = 2 + total_moves
            clear_range = f"'{room_tab}'!A{start_row}:H{end_row}"

            service = self.client.get_service()
            service.spreadsheets().values().clear(
                spreadsheetId=clean_id,
                range=clear_range
            ).execute()
            return True
        except Exception:
            return False

    def batch_poll_room(
        self,
        spreadsheet_id: str,
        room_id: str,
        after_move_num: int = 0,
        after_msg_id: int = 0
    ) -> Tuple[bool, Dict[str, Any], str]:
        """
        שליפת כל עדכוני החדר בבקשת HTTP אחת מהירה (batchGet):
        - מצב מטא-דאטה (Metadata)
        - מהלכים חדשים (Moves)
        - הודעות צ'אט חדשות (Chat)
        """
        clean_id = extract_spreadsheet_id(spreadsheet_id)
        room_tab = self.get_room_tab_name(room_id)
        chat_tab = self.get_chat_tab_name(room_id)

        ranges = [
            f"'{room_tab}'!A1:I1",
            f"'{room_tab}'!A3:H150",
            f"'{chat_tab}'!A2:E100"
        ]

        try:
            service = self.client.get_service()
            res = service.spreadsheets().values().batchGet(
                spreadsheetId=clean_id,
                ranges=ranges
            ).execute()

            val_ranges = res.get("valueRanges", [])

            # 1. ניתוח מטא
            meta_info = {}
            if len(val_ranges) > 0:
                meta_rows = val_ranges[0].get("values", [])
                if meta_rows and meta_rows[0]:
                    m = meta_rows[0]
                    meta_info = {
                        "room_id": m[1] if len(m) > 1 else room_tab,
                        "host_player": m[2] if len(m) > 2 else "",
                        "guest_player": m[3] if len(m) > 3 else "",
                        "host_color": m[4] if len(m) > 4 else "W",
                        "time_control": m[5] if len(m) > 5 else "NONE",
                        "game_status": m[6] if len(m) > 6 else "WAITING",
                        "action_status": m[7] if len(m) > 7 else "NONE",
                        "created_at": m[8] if len(m) > 8 else ""
                    }

            # 2. ניתוח מהלכים
            new_moves = []
            if len(val_ranges) > 1:
                moves_rows = val_ranges[1].get("values", [])
                for r in moves_rows:
                    if not r or len(r) < 5:
                        continue
                    try:
                        m_num = int(str(r[0]).strip())
                    except ValueError:
                        continue
                    if m_num > after_move_num:
                        new_moves.append({
                            "move_num": m_num,
                            "player": str(r[1]).strip() if len(r) > 1 else "",
                            "color": str(r[2]).strip() if len(r) > 2 else "W",
                            "move_uci": str(r[3]).strip() if len(r) > 3 else "",
                            "move_san": str(r[4]).strip() if len(r) > 4 else "",
                            "fen": str(r[5]).strip() if len(r) > 5 else "",
                            "timestamp": str(r[6]).strip() if len(r) > 6 else "",
                            "action": str(r[7]).strip() if len(r) > 7 else "MOVE"
                        })
                new_moves.sort(key=lambda x: x["move_num"])

            # 3. ניתוח צ'אט
            new_chat = []
            if len(val_ranges) > 2:
                chat_rows = val_ranges[2].get("values", [])
                for r in chat_rows:
                    if not r or len(r) < 5:
                        continue
                    try:
                        c_id = int(str(r[0]).strip())
                    except ValueError:
                        continue
                    if c_id > after_msg_id:
                        new_chat.append({
                            "msg_id": c_id,
                            "timestamp": str(r[1]).strip(),
                            "sender": str(r[2]).strip(),
                            "color": str(r[3]).strip(),
                            "text": str(r[4]).strip()
                        })
                new_chat.sort(key=lambda x: x["msg_id"])

            return True, {"meta": meta_info, "moves": new_moves, "chat": new_chat}, ""

        except Exception as e:
            # במקרה של שגיאה (למשל לשונית צ'אט שעדיין לא קיימת) - נבצע פנייה רגילה
            _, moves, _ = self.fetch_game_moves(clean_id, room_id, after_move_num)
            _, meta, _ = self.read_room_meta(clean_id, room_id)
            _, chat, _ = self.fetch_chat_messages(clean_id, room_id, after_msg_id)
            return True, {"meta": meta, "moves": moves, "chat": chat}, str(e)


    def send_move(
        self,
        spreadsheet_id: str,
        room_id: str,
        move_num: int,
        player_name: str,
        color: str,
        move_uci: str,
        move_san: str,
        fen: str,
        action: str = "MOVE"
    ) -> Tuple[bool, str]:
        """כתיבת מהלך ללשונית החדר"""
        clean_id = extract_spreadsheet_id(spreadsheet_id)
        room_tab = self.get_room_tab_name(room_id)
        curr_time = datetime.datetime.now().strftime("%H:%M:%S")

        row = [
            str(move_num),
            player_name.strip(),
            color,
            move_uci,
            move_san,
            fen,
            curr_time,
            action
        ]
        success, res, err = self.client.write_row(clean_id, room_tab, row)
        if success:
            return True, "המהלך נשלח בהצלחה."
        return False, str(res or err)

    def fetch_game_moves(
        self,
        spreadsheet_id: str,
        room_id: str,
        after_move_num: int = 0
    ) -> Tuple[bool, List[Dict[str, Any]], str]:
        """משיכת כל המהלכים מחדר המשחק (החל משורה 3)"""
        clean_id = extract_spreadsheet_id(spreadsheet_id)
        room_tab = self.get_room_tab_name(room_id)

        # קריאת שורות מהלך (A3 ומטה)
        success, rows, err = self.client.read_sheet(clean_id, room_tab, "A3:H150")
        if not success:
            return False, [], str(rows or err)

        if not rows:
            return True, [], ""

        new_moves = []
        for r in rows:
            if not r or len(r) < 5:
                continue

            try:
                m_num = int(str(r[0]).strip())
            except ValueError:
                continue

            if m_num > after_move_num:
                new_moves.append({
                    "move_num": m_num,
                    "player": str(r[1]).strip() if len(r) > 1 else "",
                    "color": str(r[2]).strip() if len(r) > 2 else "W",
                    "move_uci": str(r[3]).strip() if len(r) > 3 else "",
                    "move_san": str(r[4]).strip() if len(r) > 4 else "",
                    "fen": str(r[5]).strip() if len(r) > 5 else "",
                    "timestamp": str(r[6]).strip() if len(r) > 6 else "",
                    "action": str(r[7]).strip() if len(r) > 7 else "MOVE"
                })

        new_moves.sort(key=lambda x: x["move_num"])
        return True, new_moves, ""

    # ------------------ צ'אט חי בתוך המשחק ------------------

    def ensure_chat_tab(self, spreadsheet_id: str, room_id: str) -> bool:
        """מוודא שלשונית הצ'אט קיימת ומכילה כותרות"""
        try:
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            chat_tab = self.get_chat_tab_name(room_id)
            self.client.ensure_sheet_tab_exists(clean_id, chat_tab)

            success, rows, _ = self.client.read_sheet(clean_id, chat_tab, "A1:E1")
            if not rows or len(rows) == 0:
                self.client.write_row(clean_id, chat_tab, CHAT_HEADERS)
            return True
        except Exception:
            return False

    def send_chat_message(
        self,
        spreadsheet_id: str,
        room_id: str,
        msg_id: int,
        sender: str,
        color: str,
        message: str
    ) -> Tuple[bool, str]:
        """שליחת הודעת צ'אט ללשונית ה-Chat_XXXX"""
        clean_id = extract_spreadsheet_id(spreadsheet_id)
        chat_tab = self.get_chat_tab_name(room_id)
        curr_time = datetime.datetime.now().strftime("%H:%M:%S")

        row = [
            str(msg_id),
            curr_time,
            sender.strip(),
            color,
            message.strip()
        ]
        success, res, err = self.client.write_row(clean_id, chat_tab, row)
        if success:
            return True, "הודעה נשלחה"
        return False, str(res or err)

    def fetch_chat_messages(
        self,
        spreadsheet_id: str,
        room_id: str,
        after_msg_id: int = 0
    ) -> Tuple[bool, List[Dict[str, Any]], str]:
        """משיכת הודעות צ'אט חדשות"""
        clean_id = extract_spreadsheet_id(spreadsheet_id)
        chat_tab = self.get_chat_tab_name(room_id)

        success, rows, err = self.client.read_sheet(clean_id, chat_tab, "A2:E100")
        if not success:
            return False, [], str(rows or err)

        new_messages = []
        for r in rows:
            if not r or len(r) < 5:
                continue
            try:
                m_id = int(str(r[0]).strip())
            except ValueError:
                continue

            if m_id > after_msg_id:
                new_messages.append({
                    "msg_id": m_id,
                    "timestamp": str(r[1]).strip(),
                    "sender": str(r[2]).strip(),
                    "color": str(r[3]).strip(),
                    "text": str(r[4]).strip()
                })

        new_messages.sort(key=lambda x: x["msg_id"])
        return True, new_messages, ""

    # ------------------ לובי משחקים מרכזי (Lobby) ------------------

    def ensure_lobby(self, spreadsheet_id: str) -> bool:
        """מוודא שלשונית Lobby קיימת בגיליון ומכילה כותרות"""
        try:
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            self.client.ensure_sheet_tab_exists(clean_id, "Lobby")
            success, rows, _ = self.client.read_sheet(clean_id, "Lobby", "A1:G1")
            if not rows or len(rows) == 0:
                self.client.write_row(clean_id, "Lobby", LOBBY_HEADERS)
            return True
        except Exception:
            return False

    def publish_room_to_lobby(
        self,
        spreadsheet_id: str,
        room_id: str,
        host_name: str,
        time_control: str,
        host_color: str,
        game_type: str = "CHESS"
    ) -> Tuple[bool, str]:
        """פרסום חדר בלובי המרכזי כדי ששחקנים אחרים יוכלו לראות ולהצטרף"""
        try:
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            self.ensure_lobby(clean_id)
            curr_time = datetime.datetime.now().strftime("%H:%M:%S")

            row = [
                room_id.strip(),
                host_name.strip(),
                time_control,
                host_color,
                clean_id,
                "WAITING",
                curr_time,
                game_type.strip().upper()
            ]
            success, res, err = self.client.write_row(clean_id, "Lobby", row)
            return success, str(res or err)
        except Exception as e:
            return False, str(e)

    def fetch_lobby_games(self, spreadsheet_id: str, game_type_filter: Optional[str] = None) -> Tuple[bool, List[Dict[str, Any]], str]:
        """קריאת רשימת החדרים הפתוחים מהלובי (סטטוס WAITING), עם אפשרות סינון לפי סוג משחק"""
        try:
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            self.ensure_lobby(clean_id)
            success, rows, err = self.client.read_sheet(clean_id, "Lobby", "A2:H50")
            if not success:
                return False, [], str(rows or err)

            games = []
            for r in rows:
                if not r or len(r) < 6:
                    continue
                status = str(r[5]).strip().upper()
                if status == "WAITING":
                    g_type = str(r[7]).strip().upper() if len(r) > 7 and str(r[7]).strip() else "CHESS"
                    if game_type_filter and game_type_filter.upper() != "ALL" and g_type != game_type_filter.upper():
                        continue

                    games.append({
                        "room_id": str(r[0]).strip(),
                        "host_name": str(r[1]).strip(),
                        "time_control": str(r[2]).strip(),
                        "host_color": str(r[3]).strip(),
                        "spreadsheet_id": str(r[4]).strip(),
                        "created_at": str(r[6]).strip() if len(r) > 6 else "",
                        "game_type": g_type
                    })

            return True, games, ""
        except Exception as e:
            return False, [], str(e)
