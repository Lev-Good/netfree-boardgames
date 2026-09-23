# -*- coding: utf-8 -*-
"""
מודול תקשורת מול Google Sheets API
מיועד לפעול תחת סינון נטפרי ומבצע זיהוי ואבחון מדויק של שגיאות,
כולל תמיכה מובנית בתעודת האבטחה של נטפרי (למניעת שגיאות SSL) ויצירה אוטומטית של לשוניות.
"""

import os
import sys
import json
import socket
import datetime
import uuid
import re
from typing import Tuple, Dict, Any, Optional, List, Callable

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import httplib2
import google_auth_httplib2

# תעודת השורש הרשמית של נטפרי (NetFree Root CA)
NETFREE_ROOT_CA = """-----BEGIN CERTIFICATE-----
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
AiH5GAGaSCVrseI=
-----END CERTIFICATE-----"""

# היקף ההרשאות הדרוש לקריאה וכתיבה בגיליונות גוגל
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

DEFAULT_CREDENTIALS_FILE = 'credentials.json'
DEFAULT_TOKEN_FILE = 'token.json'


class SheetsErrorType:
    NETFREE_BLOCKED = "NETFREE_BLOCKED"       # אפשרות א': API אינו נגיש / נחסם
    AUTH_FAILED = "AUTH_FAILED"               # אפשרות ב': ההתחברות לחשבון נכשלה
    PERMISSION_DENIED = "PERMISSION_DENIED"   # אפשרות ג': אין הרשאה לגיליון (403/404)
    OTHER_ERROR = "OTHER_ERROR"               # שגיאה כללית


def get_app_dir() -> str:
    """מחזיר את נתיב התיקייה שבה רצה התוכנה (תואם לקובץ EXE נייד או קובץ Python רגיל)"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(get_app_dir(), "config.json")


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(data: dict):
    try:
        curr = load_config()
        curr.update(data)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(curr, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def setup_netfree_ca_bundle() -> str:
    """יוצר מאגר תעודות CA משולב המכיל את תעודת השורש של נטפרי ותעודות מערכת Windows"""
    target_dir = get_app_dir()
    bundle_path = os.path.join(target_dir, "ca_bundle_netfree.pem")

    base_bundle = ""
    try:
        import certifi
        with open(certifi.where(), 'r', encoding='utf-8', errors='ignore') as f:
            base_bundle = f.read()
    except Exception:
        pass

    win_certs = []
    try:
        import ssl
        for store in ['ROOT', 'CA']:
            for cert_bytes, _, _ in ssl.enum_certificates(store):
                try:
                    win_certs.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
                except Exception:
                    pass
    except Exception:
        pass

    # שילוב תעודת השורש הרשמית של נטפרי
    combined = base_bundle + "\n" + "\n".join(win_certs) + "\n" + NETFREE_ROOT_CA + "\n"
    try:
        with open(bundle_path, 'w', encoding='utf-8') as f:
            f.write(combined)
    except Exception:
        pass

    os.environ['SSL_CERT_FILE'] = bundle_path
    os.environ['REQUESTS_CA_BUNDLE'] = bundle_path
    httplib2.CA_CERTS = bundle_path
    return bundle_path


# אתחול תעודות נטפרי מיד עם טעינת המודול
DEFAULT_CA_BUNDLE = setup_netfree_ca_bundle()


def extract_spreadsheet_id(text_or_url: str) -> str:
    """מחלץ מזהה גיליון מתוך מחרוזת פשוטה או מתוך כתובת URL מלאה של Google Sheets."""
    text = (text_or_url or "").strip()
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', text)
    if match:
        return match.group(1)
    return text


class GoogleSheetsClient:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or get_app_dir()
        self.credentials_path = os.path.join(self.base_dir, DEFAULT_CREDENTIALS_FILE)
        self.token_path = os.path.join(self.base_dir, DEFAULT_TOKEN_FILE)
        self.ca_bundle_path = setup_netfree_ca_bundle()
        self.creds: Optional[Credentials] = None
        self.service = None
        self.computer_name = socket.gethostname()

    def set_credentials_file(self, filepath: str):
        """מעדכן נתיב לקובץ credentials.json"""
        self.credentials_path = filepath

    def credentials_file_exists(self) -> bool:
        return os.path.exists(self.credentials_path)

    def is_logged_in(self) -> bool:
        """בודק האם יש טוקן שמור ותקף"""
        try:
            if os.path.exists(self.token_path):
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
                if creds and (creds.valid or creds.refresh_token):
                    return True
        except Exception:
            pass
        return False

    def logout(self):
        """מוחק את הטוקן השמור ומנתק את המשתמש"""
        self.creds = None
        self.service = None
        if os.path.exists(self.token_path):
            try:
                os.remove(self.token_path)
            except Exception:
                pass

    def authenticate(self, prompt_browser: bool = True) -> Tuple[bool, str, Optional[str]]:
        """
        מתחבר ל-Google באמצעות OAuth 2.0 Desktop Flow עם תמיכה מלאה בתעודות נטפרי.
        """
        if not os.path.exists(self.credentials_path):
            return False, f"קובץ ההגדרות '{os.path.basename(self.credentials_path)}' לא נמצא. יש להוריד אותו מ-Google Cloud Console.", SheetsErrorType.AUTH_FAILED

        creds = None
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception:
                try:
                    os.remove(self.token_path)
                except Exception:
                    pass
                creds = None

        try:
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except Exception as refresh_err:
                        err_str = str(refresh_err)
                        if any(term in err_str.lower() for term in ["connection", "failed to establish", "timeout", "ssl", "certificate"]):
                            return False, f"❌ לא ניתן להגיע לשרתי Google (חסימת נטפרי או שגיאת תעודת אבטחה): {err_str}", SheetsErrorType.NETFREE_BLOCKED
                        creds = None

                if not creds:
                    if not prompt_browser:
                        return False, "לא נמצאה התחברות שמורה. יש לבצע התחברות ראשונית.", SheetsErrorType.AUTH_FAILED

                    # התחברות חדשה דרך הדפדפן
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0, prompt='consent')

                if creds:
                    with open(self.token_path, 'w', encoding='utf-8') as token_file:
                        token_file.write(creds.to_json())

            self.creds = creds
            # חיבור מבוסס httplib2 מאובטח עם תעודת נטפרי
            base_http = httplib2.Http(ca_certs=self.ca_bundle_path, timeout=30)
            auth_http = google_auth_httplib2.AuthorizedHttp(self.creds, http=base_http)
            self.service = build('sheets', 'v4', http=auth_http, cache_discovery=False)
            return True, "✅ התחברות ל-Google הצליחה.", None

        except Exception as e:
            err_str = str(e)
            if any(term in err_str.lower() for term in ["connection", "network", "offline", "failed to establish", "ssl", "cert", "timeout", "getaddrinfo"]):
                return False, f"❌ לא ניתן להגיע ל-Google Sheets API (שגיאת רשת/SSL בנטפרי): {err_str}", SheetsErrorType.NETFREE_BLOCKED
            return False, f"❌ ההתחברות לחשבון Google נכשלה: {err_str}", SheetsErrorType.AUTH_FAILED

    def get_service(self):
        """מחזיר את אובייקט ה-Service המחובר"""
        if self.service is None:
            success, msg, _ = self.authenticate(prompt_browser=False)
            if not success:
                raise RuntimeError(msg)
        return self.service

    def create_new_spreadsheet(self, title: str = "פלטפורמת שחמט מקוון בנטפרי") -> Tuple[bool, str, str]:
        """יוצר קובץ Google Spreadsheet חדש בחשבון המשתמש ומחזיר (הצלחה, spreadsheet_id, spreadsheet_url)"""
        try:
            service = self.get_service()
            body = {
                'properties': {
                    'title': title
                }
            }
            res = service.spreadsheets().create(body=body).execute()
            sheet_id = res.get('spreadsheetId', '')
            sheet_url = res.get('spreadsheetUrl', f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
            return True, sheet_id, sheet_url
        except Exception as e:
            return False, str(e), ""


    def check_api_reachability(self) -> Tuple[bool, str, Optional[str]]:
        """שלב 2: בודק נגישות ישירה של Google Sheets API"""
        try:
            h = httplib2.Http(ca_certs=self.ca_bundle_path, timeout=10)
            resp, _ = h.request("https://sheets.googleapis.com/$discovery/rest?version=v4")
            return True, "✅ ניתן להגיע ל-Google Sheets API דרך נטפרי.", None
        except Exception as e:
            err_str = str(e)
            return False, f"❌ לא ניתן להגיע ל-Google Sheets API: {err_str}", SheetsErrorType.NETFREE_BLOCKED

    def ensure_sheet_tab_exists(self, spreadsheet_id: str, sheet_name: str) -> bool:
        """מוודא שלשונית ספציפית קיימת בגיליון. אם לא - יוצר אותה אוטומטית."""
        try:
            service = self.get_service()
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            meta = service.spreadsheets().get(spreadsheetId=clean_id).execute()
            sheets = meta.get('sheets', [])
            titles = [s.get('properties', {}).get('title', '') for s in sheets]

            if sheet_name in titles:
                return True

            # יצירת הלשונית החדשה
            body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': sheet_name
                        }
                    }
                }]
            }
            service.spreadsheets().batchUpdate(spreadsheetId=clean_id, body=body).execute()
            return True
        except Exception:
            return False

    def read_sheet(self, spreadsheet_id: str, sheet_name: str = "Sheet1", range_cells: str = "A1:Z100") -> Tuple[bool, Any, Optional[str]]:
        """פעולה א' - קריאת נתונים מגיליון קיים"""
        try:
            service = self.get_service()
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            full_range = f"'{sheet_name}'!{range_cells}" if range_cells else f"'{sheet_name}'"

            try:
                result = service.spreadsheets().values().get(
                    spreadsheetId=clean_id,
                    range=full_range
                ).execute()
                rows = result.get('values', [])
                return True, rows, None
            except HttpError as read_err:
                if "Unable to parse range" in str(read_err) or read_err.resp.status == 400:
                    # הלשונית עדיין לא קיימת - ניצור אותה ונחזיר רשימה ריקה
                    self.ensure_sheet_tab_exists(clean_id, sheet_name)
                    return True, [], None
                raise read_err

        except HttpError as error:
            status_code = error.resp.status
            if status_code in (403, 404):
                return False, f"❌ אין הרשאת גישה לגיליון (שגיאה {status_code}). ודא שהמזהה תקין ושהגיליון שותף עם החשבון.", SheetsErrorType.PERMISSION_DENIED
            return False, f"❌ שגיאת API ({status_code}): {error}", SheetsErrorType.OTHER_ERROR
        except Exception as e:
            err_str = str(e)
            if any(term in err_str.lower() for term in ["connection", "failed to establish", "network", "timeout", "ssl", "cert"]):
                return False, f"❌ לא ניתן להגיע ל-Google Sheets API (שגיאת רשת/SSL): {err_str}", SheetsErrorType.NETFREE_BLOCKED
            return False, f"❌ שגיאה בקריאת הנתונים: {err_str}", SheetsErrorType.OTHER_ERROR

    def write_row(self, spreadsheet_id: str, sheet_name: str = "Sheet1", row_values: Optional[List[str]] = None) -> Tuple[bool, List[str], Optional[str]]:
        """פעולה ב' - כתיבת שורה חדשה לגיליון עם יצירה אוטומטית של לשונית אם חסרה"""
        try:
            service = self.get_service()
            clean_id = extract_spreadsheet_id(spreadsheet_id)
            current_time = datetime.datetime.now().strftime("%H:%M:%S")

            if row_values is None:
                row_values = ["בדיקת תקשורת", current_time, self.computer_name, "הצלחה"]

            body = {
                'values': [row_values]
            }

            safe_range = f"'{sheet_name}'"

            try:
                service.spreadsheets().values().append(
                    spreadsheetId=clean_id,
                    range=safe_range,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body=body
                ).execute()
            except HttpError as append_err:
                # אם הלשונית חסרה (Unable to parse range) - ניצור אותה ונוסיף שוב
                if "Unable to parse range" in str(append_err) or append_err.resp.status == 400:
                    self.ensure_sheet_tab_exists(clean_id, sheet_name)
                    service.spreadsheets().values().append(
                        spreadsheetId=clean_id,
                        range=safe_range,
                        valueInputOption="USER_ENTERED",
                        insertDataOption="INSERT_ROWS",
                        body=body
                    ).execute()
                else:
                    raise append_err

            return True, row_values, None

        except HttpError as error:
            status_code = error.resp.status
            if status_code in (403, 404):
                return False, f"❌ אין הרשאת גישה לגיליון (שגיאה {status_code} בעת כתיבה). ודא שיש הרשאת עריכה (Editor).", SheetsErrorType.PERMISSION_DENIED
            return False, f"❌ שגיאת API בכתיבה ({status_code}): {error}", SheetsErrorType.OTHER_ERROR
        except Exception as e:
            err_str = str(e)
            if any(term in err_str.lower() for term in ["connection", "failed to establish", "network", "timeout", "ssl", "cert"]):
                return False, f"❌ לא ניתן להגיע ל-Google Sheets API (שגיאת SSL/רשת): {err_str}", SheetsErrorType.NETFREE_BLOCKED
            return False, f"❌ שגיאה בכתיבת הנתונים: {err_str}", SheetsErrorType.OTHER_ERROR

    def ensure_headers(self, spreadsheet_id: str, sheet_name: str = "Sheet1") -> bool:
        """בודק האם יש כותרות בגיליון, ואם הגיליון ריק - מוסיף שורת כותרות"""
        try:
            self.ensure_sheet_tab_exists(spreadsheet_id, sheet_name)
            success, rows, _ = self.read_sheet(spreadsheet_id, sheet_name, "A1:D1")
            if success and not rows:
                headers = ["פעולה", "שעה", "מחשב", "תוצאה"]
                self.write_row(spreadsheet_id, sheet_name, headers)
                return True
        except Exception:
            pass
        return False

    def run_full_test(self, spreadsheet_id: str, sheet_name: str = "Sheet1", progress_cb: Optional[Callable[[int, str, bool], None]] = None) -> Dict[str, Any]:
        """בדיקה מלאה (5 שלבים)"""
        report = {
            "overall_success": False,
            "steps": [],
            "error_type": None,
            "summary_title": "",
            "summary_detail": ""
        }

        def record_step(step_num: int, title: str, success: bool, message: str):
            report["steps"].append({
                "step": step_num,
                "title": title,
                "success": success,
                "message": message
            })
            if progress_cb:
                progress_cb(step_num, message, success)

        clean_id = extract_spreadsheet_id(spreadsheet_id)
        if not clean_id:
            report["summary_title"] = "# הבדיקה נכשלה"
            report["summary_detail"] = "מזהה ה-Google Sheet ריק. יש להזין מזהה תקין או קישור מלא."
            report["error_type"] = SheetsErrorType.OTHER_ERROR
            return report

        # שלב 1 – התחברות
        success, msg, err_type = self.authenticate(prompt_browser=True)
        record_step(1, "שלב 1 – התחברות", success, msg)
        if not success:
            report["summary_title"] = "# הבדיקה נכשלה"
            report["summary_detail"] = msg
            report["error_type"] = err_type
            return report

        # שלב 2 – Google Sheets API נגישות
        success, msg, err_type = self.check_api_reachability()
        record_step(2, "שלב 2 – Google Sheets API", success, msg)
        if not success:
            report["summary_title"] = "# הבדיקה נכשלה"
            report["summary_detail"] = msg
            report["error_type"] = err_type
            return report

        # וידוא לשונית
        self.ensure_sheet_tab_exists(clean_id, sheet_name)

        # שלב 3 – קריאה
        success, rows, err_type = self.read_sheet(clean_id, sheet_name, "A1:D50")
        if success:
            record_step(3, "שלב 3 – קריאה", True, f"✅ קריאת נתונים הצליחה. נמצאו {len(rows)} שורות בגיליון.")
        else:
            record_step(3, "שלב 3 – קריאה", False, str(rows))
            report["summary_title"] = "# הבדיקה נכשלה"
            report["summary_detail"] = str(rows)
            report["error_type"] = err_type
            return report

        # שלב 4 – כתיבה
        unique_token = f"TEST-{uuid.uuid4().hex[:6]}"
        curr_time = datetime.datetime.now().strftime("%H:%M:%S")
        test_row = ["בדיקת תקשורת", curr_time, self.computer_name, unique_token]

        success, written, err_type = self.write_row(clean_id, sheet_name, test_row)
        if success:
            record_step(4, "שלב 4 – כתיבה", True, f"✅ כתיבת נתונים הצליחה (מזהה בדיקה שנכתב: {unique_token}).")
        else:
            record_step(4, "שלב 4 – כתיבה", False, str(written))
            report["summary_title"] = "# הבדיקה נכשלה"
            report["summary_detail"] = str(written)
            report["error_type"] = err_type
            return report

        # שלב 5 – קריאה חוזרת
        success, rows_after, err_type = self.read_sheet(clean_id, sheet_name, "A1:D100")
        if not success:
            record_step(5, "שלב 5 – קריאה חוזרת", False, f"נכשל בניסיון קריאה חוזרת: {rows_after}")
            report["summary_title"] = "# הבדיקה נכשלה"
            report["summary_detail"] = str(rows_after)
            report["error_type"] = err_type
            return report

        found = any(unique_token in row for row in rows_after)
        if found:
            record_step(5, "שלב 5 – קריאה חוזרת", True, f"✅ הנתון שנכתב ({unique_token}) נמצא בגיליון!")
            report["overall_success"] = True
            report["summary_title"] = "# הבדיקה הצליחה"
            report["summary_detail"] = "✅ Google Sheets API נגיש וניתן לקרוא ולכתוב נתונים דרך חיבור נטפרי ללא צורך ב-Apps Script!"
        else:
            record_step(5, "שלב 5 – קריאה חוזרת", False, "❌ השורה שנכתבה לא נמצאה בעת קריאה חוזרת מהגיליון.")
            report["summary_title"] = "# הבדיקה נכשלה"
            report["summary_detail"] = "הכתיבה דיווחה הצלחה, אך הנתון לא אותר בקריאה חוזרת."
            report["error_type"] = SheetsErrorType.OTHER_ERROR

        return report

    def send_game_message(self, spreadsheet_id: str, sheet_name: str, player_name: str, message: str) -> Tuple[bool, str]:
        curr_time = datetime.datetime.now().strftime("%H:%M:%S")
        row = ["מהלך", curr_time, player_name or self.computer_name, message]
        success, res, _ = self.write_row(spreadsheet_id, sheet_name, row)
        if success:
            return True, f"נשלח בהצלחה: {message}"
        return False, str(res)

    def read_all_moves(self, spreadsheet_id: str, sheet_name: str) -> Tuple[bool, List[List[str]], str]:
        success, rows, err = self.read_sheet(spreadsheet_id, sheet_name, "A1:D200")
        if success:
            return True, rows, ""
        return False, [], str(rows)
