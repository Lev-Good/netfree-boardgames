# מדריך הגדרת Google Cloud עבור בדיקת Google Sheets API

כדי שהתוכנה תוכל להתחבר לחשבון ה-Google שלך, יש צורך בקובץ זיהוי יישומי שולחן עבודה (`credentials.json`).
**שים לב:** אין צורך בסיסמת המשתמש שלך, אין צורך ב-App Password, ואין צורך ב-Google Apps Script. מדובר במזהה אפליקציה תקני בלבד.

---

## שלבי ההגדרה (חד-פעמי לכל הניסוי):

### שלב 1: כניסה ל-Google Cloud Console
1. היכנס בדפדפן אל: [https://console.cloud.google.com](https://console.cloud.google.com)
2. צור פרויקט חדש (או בחר פרויקט קיים) ולחץ עליו.

### שלב 2: הפעלת Google Sheets API
1. בתפריט הצדדי בחר **APIs & Services** (ממשקי API ושירותים) > **Library** (ספרייה).
2. חפש: **Google Sheets API**.
3. לחץ עליו ולחץ על כפתור **Enable** (הפעל).

### שלב 3: הגדרת מסך הסכמה (OAuth consent screen)
1. עבור אל **APIs & Services** > **OAuth consent screen** (מסך הסכמה של OAuth).
2. בחר בסוג משתמש: **External** (חיצוני) ולחץ **Create**.
3. מלא שם אפליקציה (למשל: `NetFree Sheets Test`) וכתובת אימייל לתמיכה.
4. לחץ **Save and Continue** עד לסיום.
5. תחת **Test users** (משתמשי בדיקה) - לחץ **Add Users** והוסף את כתובת הג'ימייל של המשתמש שיתחבר לתוכנה.

### שלב 4: יצירת מזהה לקוח שולחני (OAuth Client ID)
1. עבור אל **APIs & Services** > **Credentials** (פרטי אימות).
2. לחץ על **Create Credentials** ובחר ב-**OAuth client ID**.
3. בסוג היישום (Application type), בחר ב-**Desktop app** (יישום לשולחן עבודה).
4. תן שם (למשל `Windows Client`) ולחץ **Create**.
5. בחלון שקופץ, לחץ על **Download JSON** (הורד קובץ JSON).

### שלב 5: העתקת הקובץ לתוכנה
1. שנה את שם הקובץ שהורדת ל: `credentials.json`
2. שמור אותו בתיקיית התוכנה (התיקייה שבה נמצא `main.py`), או השתמש בכפתור "טען credentials.json" בתוכנה.

---

## יצירת גיליון Google Sheet לבדיקה:
1. פתח גיליון חדש ב-Google Sheets ([https://sheets.new](https://sheets.new)).
2. העתק את הקישור או את מזהה הגיליון (החלק שנמצא בכתובת ה-URL בין `/d/` ל-`/edit`).
3. הדבק אותו בשדה המתאים בתוכנה.
4. ודא שלחשבון ה-Google שלך יש הרשאת עריכה בגיליון.
