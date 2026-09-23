# מדריך פרסום ואימות הפרויקט ב-Google Cloud Console

מדריך זה מפרט שלב-אחר-שלב כיצד להגדיר את הפרויקט ב-Google Cloud Console כפרויקט פומבי מאושר, כדי שכל משתמש יוכל להתחבר לחשבון ה-Google שלו ללא אזהרות אבטחה ("אפליקציה לא מאומתת").

---

## שלב 1: העלאת דפי האינטרנט ל-GitHub Pages (בחינם תוך 2 דקות)

Google דורשת עבור אימות אפליקציה 3 קישורים פומביים:
1. **דף הבית של האפליקציה (Application Home Page)**
2. **מדיניות פרטיות (Privacy Policy)**
3. **תנאי שימוש (Terms of Service)**

כל הקבצים המוכנים נמצאים בתיקיית `web/`:
* `web/index.html`
* `web/privacy.html`
* `web/terms.html`

### כיצד להעלות ל-GitHub Pages:
1. היכנס לחשבון [GitHub](https://github.com) ופתח מאגר חדש (New Repository) פומבי, למשל בשם: `netfree-chess`.
2. העלה את שלושת הקבצים שבתיקיית `web/` ישירות לשורש המאגר (או בתיקיית `/docs`).
3. היכנס במאגר ל-**Settings** -> **Pages**.
4. תחת **Branch**, בחר ב-`main` ושמור (**Save**).
5. תוך דקה תקבל כתובת אתר רשמית ומאובטחת ב-HTTPS, למשל:
   * דף בית: `https://your-username.github.io/netfree-chess/`
   * פרטיות: `https://your-username.github.io/netfree-chess/privacy.html`
   * תנאי שימוש: `https://your-username.github.io/netfree-chess/terms.html`

---

## שלב 2: הגדרת מסך ההסכמה (OAuth Consent Screen) ב-Google Cloud

1. היכנס ל-[Google Cloud Console](https://console.cloud.google.com/).
2. ודא שנבחר הפרויקט שלך (למעלה בתפריט הפרויקטים).
3. בתפריט הצדדי בחר: **APIs & Services** -> **OAuth consent screen**.
4. סוג משתמש (**User Type**): בחר **External** (חיצוני) ולחץ **Create**.
5. הזן את פרטי האפליקציה:
   * **App name:** `שחמט מקוון בנטפרי` (או `NetFree Online Chess`)
   * **User support email:** כתובת הג'ימייל שלך
   * **Application home page:** `https://your-username.github.io/netfree-chess/`
   * **Application privacy policy link:** `https://your-username.github.io/netfree-chess/privacy.html`
   * **Application terms of service link:** `https://your-username.github.io/netfree-chess/terms.html`
   * **Authorized domains:** הוסף `github.io`
   * **Developer contact email:** כתובת הג'ימייל שלך
6. לחץ **Save and Continue**.

---

## שלב 3: הגדרת ההרשאות (Scopes)

1. במסך ה-Scopes לחץ על **Add or Remove Scopes**.
2. חפש וסמן את ההרשאה הבאה:
   * `.../auth/spreadsheets` (*See, edit, create, and delete all your Google Sheets spreadsheets*)
3. לחץ **Update** ולאחר מכן **Save and Continue**.

---

## שלב 4: פרסום האפליקציה (Publishing Status)

1. תחת **Publishing status**, לחץ על הכפתור **Publish App**.
2. יופיע חלון אישור: "Push to production?". לחץ **Confirm**.
3. **מזל טוב!** כעת האפליקציה במצב ייצור (Production). כל משתמש עם כל חשבון Google יוכל להתחבר לאפליקציה.

> **הערה לגבי אימות Google (Verification):**
> כאשר האפליקציה עוברת ל-Production, משתמשים יוכלו להתחבר. אם מופיע חלון "Google hasn't verified this app", המשתמש פשוט לוחץ על **מתקדם (Advanced)** -> **עבור אל שחמט מקוון (Go to NetFree Chess)**.
> כדי להסיר לחלוטין את החלון הזה, לוחצים על **Submit for verification** ומצרפים את קישורי ה-GitHub Pages שהכנו לעיל. גוגל מאשרים אפליקציות שחמט/כלים פתוחים תוך מספר ימי עסקים.

---

## שלב 5: הורדת `credentials.json` המעודכן

1. היכנס ל-**APIs & Services** -> **Credentials**.
2. תחת **OAuth 2.0 Client IDs**, ודא שהסוג הוא **Desktop app**.
3. לחץ על סמל ההורדה (חץ למטה) להורדת קובץ ה-JSON.
4. שנה את שמו ל-`credentials.json` והנח אותו בתיקיית התוכנה לצד `NetFreeChess.exe`.
