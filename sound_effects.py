# -*- coding: utf-8 -*-
"""
מודול אפקטים קוליים עבור שחמט מקוון בנטפרי
מבוסס על צלילי מערכת נקיים של Windows (winsound) הרצים בתהליך נפרד (Thread)
כדי לא לעכב את ממשק המשתמש לרגע.
"""

import sys
import threading
import platform

sound_enabled = True

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False


def _run_in_thread(target):
    t = threading.Thread(target=target, daemon=True)
    t.start()


def play_move_sound():
    """צליל ביצוע מהלך רגיל (נקי ועדין)"""
    if not sound_enabled or not HAS_WINSOUND:
        return

    def _play():
        try:
            winsound.Beep(520, 35)
        except Exception:
            pass
    _run_in_thread(_play)


def play_capture_sound():
    """צליל אכילת כלי (שני צלילים יורדים)"""
    if not sound_enabled or not HAS_WINSOUND:
        return

    def _play():
        try:
            winsound.Beep(680, 45)
            winsound.Beep(440, 50)
        except Exception:
            pass
    _run_in_thread(_play)


def play_check_sound():
    """צליל התרעת שח (צליל הדגשה חד)"""
    if not sound_enabled or not HAS_WINSOUND:
        return

    def _play():
        try:
            winsound.Beep(880, 70)
            winsound.Beep(880, 80)
        except Exception:
            pass
    _run_in_thread(_play)


def play_chat_sound():
    """צליל קבלת הודעה בצ'אט (צפצוף רך)"""
    if not sound_enabled or not HAS_WINSOUND:
        return

    def _play():
        try:
            winsound.Beep(950, 40)
        except Exception:
            pass
    _run_in_thread(_play)


def play_game_end_sound(won: bool = True):
    """צליל סיום משחק (מנגינת ניצחון או הפסד)"""
    if not sound_enabled or not HAS_WINSOUND:
        return

    def _play():
        try:
            if won:
                # מנגינת ניצחון קצרה
                for freq in [523, 659, 784, 1046]:
                    winsound.Beep(freq, 70)
            else:
                # מנגינת הפסד יורדת
                for freq in [440, 370, 311]:
                    winsound.Beep(freq, 110)
        except Exception:
            pass
    _run_in_thread(_play)


def play_dice_sound():
    """צליל הטלת קוביות (גלגול קוביות מהיר)"""
    if not sound_enabled or not HAS_WINSOUND:
        return

    def _play():
        try:
            for freq in [750, 850, 920]:
                winsound.Beep(freq, 25)
        except Exception:
            pass
    _run_in_thread(_play)


def set_sound_enabled(enabled: bool):
    global sound_enabled
    sound_enabled = enabled


def is_sound_enabled() -> bool:
    return sound_enabled
