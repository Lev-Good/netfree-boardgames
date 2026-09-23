# -*- coding: utf-8 -*-
"""
ערכת נושא משחקית מודרנית (Gaming Dark HUD Theme)
עיצוב מקצועי בסגנון פלטפורמות המשחקים המובילות:
Dark Slate עמוק, משטחי זכוכית מעודנים, כפתורי ניאון עם זוהר עדין,
שעוני LED דיגיטליים, כרטיסיות גיימינג מודרניות ובועות צ'אט מעוצבות.
"""

# פלטת צבעי גיימינג מתקדמת
BG_DARK = "#0F141C"           # רקע ראשי עמוק
PANEL_DARK = "#18202F"        # משטחי פאנלים וכרטיסיות
PANEL_HOVER = "#222D42"       # פאנל במעבר עכבר
BORDER_COLOR = "#2B374E"      # מסגרות עדינות
BORDER_GLOW = "#3B82F6"       # מסגרת פעילה מוארת

ACCENT_BLUE = "#2563EB"       # כחול שחמט וראשי
ACCENT_GREEN = "#10B981"      # ירוק הצלחה, נטפרי מאובטח, דמקה
ACCENT_ORANGE = "#F59E0B"     # כתום/זהב שש-בש וקוביות
ACCENT_PURPLE = "#8B5CF6"     # סגול לובי וקוד הזמנה חכם
ACCENT_RED = "#EF4444"        # אדום כניעה והתרעות

TEXT_PRIMARY = "#F8FAFC"      # טקסט ראשי לבן בוהק
TEXT_SECONDARY = "#94A3B8"    # טקסט משני אפור בהיר
TEXT_MUTED = "#64748B"        # טקסט מושתק

def get_gaming_stylesheet() -> str:
    """מחזיר גיליון עיצוב QSS מלא בסגנון Gaming Dark HUD"""
    return f"""
        /* עיצוב כללי של החלון */
        QMainWindow, QWidget {{
            background-color: {BG_DARK};
            color: {TEXT_PRIMARY};
            font-family: 'Segoe UI', 'Assistant', sans-serif;
            font-size: 13px;
        }}

        /* כרטיסיות ופאנלים */
        QGroupBox {{
            background-color: {PANEL_DARK};
            border: 1px solid {BORDER_COLOR};
            border-radius: 10px;
            margin-top: 14px;
            padding: 14px 10px 10px 10px;
            font-weight: bold;
            color: #E2E8F0;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top right;
            padding: 2px 10px;
            background-color: #1E293B;
            border: 1px solid {BORDER_COLOR};
            border-radius: 5px;
            color: #60A5FA;
        }}

        /* שדות קלט טקסט */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: #0B0E14;
            color: #FFFFFF;
            border: 1.5px solid {BORDER_COLOR};
            border-radius: 7px;
            padding: 7px 10px;
            selection-background-color: {ACCENT_BLUE};
        }}
        QLineEdit:focus, QTextEdit:focus {{
            border: 1.5px solid {ACCENT_BLUE};
            background-color: #0E131C;
        }}

        /* תיבות בחירה (ComboBox) */
        QComboBox {{
            background-color: #161F2E;
            color: #FFFFFF;
            border: 1.5px solid {BORDER_COLOR};
            border-radius: 7px;
            padding: 6px 12px;
            min-height: 24px;
        }}
        QComboBox:hover {{
            border: 1.5px solid {ACCENT_BLUE};
            background-color: #1B2638;
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background-color: #161F2E;
            color: #FFFFFF;
            border: 1px solid {BORDER_COLOR};
            selection-background-color: {ACCENT_BLUE};
            selection-color: #FFFFFF;
            padding: 4px;
        }}

        /* כפתורים כלליים */
        QPushButton {{
            background-color: #1E293B;
            color: #F8FAFC;
            border: 1px solid #334155;
            border-radius: 7px;
            padding: 7px 14px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: #273549;
            border-color: #475569;
        }}
        QPushButton:pressed {{
            background-color: #151D2A;
        }}
        QPushButton:disabled {{
            background-color: #121721;
            color: #475569;
            border-color: #1E293B;
        }}

        /* כפתורי פעולה מיוחדים */
        QPushButton#btnPrimary {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1D4ED8, stop:1 #3B82F6);
            color: white;
            border: 1px solid #60A5FA;
            font-weight: bold;
        }}
        QPushButton#btnPrimary:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563EB, stop:1 #60A5FA);
        }}

        QPushButton#btnSuccess {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #047857, stop:1 #10B981);
            color: white;
            border: 1px solid #34D399;
            font-weight: bold;
        }}
        QPushButton#btnSuccess:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #34D399);
        }}

        QPushButton#btnDanger {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #B91C1C, stop:1 #EF4444);
            color: white;
            border: 1px solid #F87171;
            font-weight: bold;
        }}
        QPushButton#btnDanger:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #DC2626, stop:1 #F87171);
        }}

        QPushButton#btnWarning {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #B45309, stop:1 #F59E0B);
            color: white;
            border: 1px solid #FBBF24;
            font-weight: bold;
        }}
        QPushButton#btnWarning:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #D97706, stop:1 #FBBF24);
        }}

        /* לשוניות (QTabWidget) */
        QTabWidget::pane {{
            border: 1px solid {BORDER_COLOR};
            background-color: {PANEL_DARK};
            border-radius: 8px;
            top: -1px;
        }}
        QTabBar::tab {{
            background-color: #121824;
            color: {TEXT_SECONDARY};
            border: 1px solid {BORDER_COLOR};
            border-bottom: none;
            padding: 8px 16px;
            margin-right: 4px;
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
            font-weight: 600;
        }}
        QTabBar::tab:selected {{
            background-color: {PANEL_DARK};
            color: #FFFFFF;
            border-top: 2.5px solid {ACCENT_BLUE};
        }}
        QTabBar::tab:hover:!selected {{
            background-color: #1A2232;
            color: #E2E8F0;
        }}

        /* טבלאות (QTableWidget) */
        QTableWidget {{
            background-color: #0E131C;
            border: 1px solid {BORDER_COLOR};
            border-radius: 8px;
            gridline-color: #1E293B;
            color: #F1F5F9;
        }}
        QTableWidget::item {{
            padding: 6px;
            border-bottom: 1px solid #1E293B;
        }}
        QTableWidget::item:selected {{
            background-color: #1E3A8A;
            color: #FFFFFF;
        }}
        QHeaderView::section {{
            background-color: #182232;
            color: #93C5FD;
            font-weight: bold;
            border: none;
            border-bottom: 1.5px solid #2B374E;
            padding: 7px;
        }}

        /* תיבות סימון (QCheckBox) */
        QCheckBox {{
            color: #E2E8F0;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 17px;
            height: 17px;
            border: 1.5px solid {BORDER_COLOR};
            border-radius: 4px;
            background-color: #0B0E14;
        }}
        QCheckBox::indicator:checked {{
            background-color: {ACCENT_BLUE};
            border-color: #60A5FA;
        }}

        /* פסי גלילה מודרניים */
        QScrollBar:vertical {{
            background: #0B0E14;
            width: 10px;
            border-radius: 5px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: #334155;
            min-height: 25px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #475569;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
    """
