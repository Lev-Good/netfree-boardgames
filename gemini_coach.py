# -*- coding: utf-8 -*-
"""
מודול ייעוץ שחמט מבוסס AI (Google Gemini) המותאם לנטפרי.
תומך באיתור דינמי של המודל העדכני ביותר של Gemini (כולל מודלי דור 3 / 2.5),
עם טיפול הרמטי בתעודת השורש של נטפרי (SSL CA Bundle).
"""

import os
import sys
import json
import ssl
import urllib.request
import urllib.error
from typing import Optional, Tuple, List, Dict, Any

from google_sheets_client import get_app_dir, load_config, save_config, setup_netfree_ca_bundle


class GeminiChessCoach:
    def __init__(self):
        self.ca_bundle = setup_netfree_ca_bundle()
        self._cached_best_model: Optional[str] = None

    def get_api_key(self) -> str:
        cfg = load_config()
        return cfg.get("gemini_api_key", "").strip()

    def set_api_key(self, api_key: str):
        save_config({"gemini_api_key": api_key.strip()})
        self._cached_best_model = None

    def _get_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context(cafile=self.ca_bundle if os.path.exists(self.ca_bundle) else None)
        return ctx

    def get_latest_model_name(self, api_key: str) -> str:
        """
        פונה לרשימת המודלים של Google Gemini API ומאתרת את המודל העדכני ביותר
        התומך ב-generateContent (למשל gemini-3, gemini-2.5, flash / pro).
        """
        if self._cached_best_model:
            return self._cached_best_model

        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        ctx = self._get_ssl_context()
        req = urllib.request.Request(url, headers={"User-Agent": "NetFreeChess/2.0"})

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=8) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    models = data.get("models", [])
                    # סינון מודלים שתומכים ביצירת טקסט
                    gen_models = [
                        m.get("name", "").replace("models/", "")
                        for m in models
                        if "generateContent" in m.get("supportedGenerationMethods", [])
                        and "gemini" in m.get("name", "").lower()
                    ]

                    # סדר עדיפויות: דור 3 Flash/Pro > דור 2.5 Flash/Pro > fallback
                    gen_models.sort(reverse=True)
                    for candidate in gen_models:
                        # נעדיף flash לביצועים מהירים ותגובה מיידית
                        if "flash" in candidate.lower() and not "preview" in candidate.lower() and not "exp" in candidate.lower():
                            self._cached_best_model = candidate
                            return candidate

                    if gen_models:
                        self._cached_best_model = gen_models[0]
                        return self._cached_best_model

        except Exception as e:
            print(f"[GeminiCoach] Notice: Could not list models dynamically: {e}", file=sys.stderr)

        # Fallback אם אין מענה או אין גישה לרשימה:
        fallback = "gemini-2.5-flash"
        self._cached_best_model = fallback
        return fallback

    def get_chess_hint(self, fen: str, is_check: bool, turn: str, move_history: List[str]) -> Tuple[bool, str]:
        """
        מנתחת את העמדה ושולחת בקשה ל-Gemini.
        מחזירה (success, hint_or_error_message).
        """
        api_key = self.get_api_key()
        if not api_key:
            return False, "לא מוגדר מפתח Gemini API. לחץ על 'הגדר מפתח API' כדי להזין מפתח."

        try:
            model_name = self.get_latest_model_name(api_key)
            prompt = self.build_prompt(fen, is_check, turn, move_history)

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "NetFreeChess/2.0"
            }
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.4,
                    "maxOutputTokens": 400
                }
            }

            req_data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")
            ctx = self._get_ssl_context()

            with urllib.request.urlopen(req, context=ctx, timeout=12) as response:
                result_json = json.loads(response.read().decode('utf-8'))
                candidates = result_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        hint_text = parts[0]["text"].strip()
                        return True, hint_text

                return False, "לא התקבלה תשובה מ-Gemini."

        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode('utf-8')
            except Exception:
                pass
            if e.code == 400 or "API_KEY_INVALID" in err_body:
                return False, "מפתח Gemini API שגוי או לא פעיל. אנא בדוק את המפתח."
            elif e.code == 429:
                return False, "חריגה ממגבלת הבקשות של Google Gemini (Rate Limit). אנא נסה שוב בעוד רגע."
            return False, f"שגיאת תקשורת עם Gemini (קוד {e.code})."

        except urllib.error.URLError as e:
            return False, f"שגיאת רשת בחיבור ל-Gemini: {e.reason}"

        except Exception as e:
            return False, f"שגיאה בלתי צפויה: {str(e)}"

    def build_prompt(self, fen: str, is_check: bool, turn: str, move_history: List[str]) -> str:
        color_str = "לבן" if turn.upper() == "W" else "שחור"
        recent_moves = ", ".join(move_history[-6:]) if move_history else "תחילת משחק"

        prompt = f"""אתה רב-אמן ומאמן שחמט מומחה בעל ידע מעמיק.
אנא נתח בקצרה את העמדה הבאה ותן עצה מעשית, חכמה ותכליתית (2-3 משפטים בעברית) לשחקן שזהו תורו כעת.

נתוני העמדה:
- מצב לוח (FEN): {fen}
- תור נוכחי: {color_str}
- האם המלך בשח: {'כן! המלך מאוים בשח' if is_check else 'לא'}
- מהלכים אחרונים ששוחקו: {recent_moves}

הנחיות לתשובה:
1. ציין מהו המהלך המומלץ ביותר או הרעיון הטקטי המרכזי (למשל איום על כלי, שמירה, יציאה משח או פיתוח עמדה).
2. הסבר בקצרה את הנימוק מאחורי המהלך בעברית ברורה ותמציתית.
3. שמור על תשובה קצרה וממוקדת (עד 3 משפטים בלבד)."""
        return prompt
