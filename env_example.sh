# הגדרות שרת
HOST=0.0.0.0
PORT=5000
DEBUG=True

# מאגר נתונים
DATABASE_PATH=pbx_system.db

# הגדרות iCount API
ICOUNT_API_URL=https://api.icount.co.il
ICOUNT_CID=your_company_id_here
ICOUNT_USER=your_username_here
ICOUNT_PASS=your_password_here

# הגדרות SMS (אופציונלי)
SMS_API_KEY=your_sms_api_key_here
SMS_SENDER=MySystem

# נתיבים
RECORDINGS_PATH=./recordings

# לוגים
LOG_LEVEL=INFO
LOG_FILE=pbx_system.log

# סביבה (development/production)
FLASK_ENV=development