# תיקונים נדרשים לקוד PBX:

## 1. תוספת להוספה ב-DatabaseHandler הגיבוי:

class DatabaseHandler:
    # ... הקוד הקיים ...
    
    def create_customer(self, phone_number: str, name: str = None, email: str = None, 
                       subscription_start_date: str = None, subscription_end_date: str = None) -> int:
        """יצירת לקוח חדש"""
        import datetime
        
        conn = self.get_connection()
        c = conn.cursor()
        
        # אם לא ניתן תאריך התחלה, נתחיל מהיום
        if not subscription_start_date:
            subscription_start_date = datetime.datetime.now().strftime('%Y-%m-%d')
        
        # אם לא ניתן תאריך סיום, נוסיף שנה מהיום
        if not subscription_end_date:
            end_date = datetime.datetime.now() + datetime.timedelta(days=365)
            subscription_end_date = end_date.strftime('%Y-%m-%d')
        
        c.execute('''
            INSERT INTO customers (phone_number, name, email, subscription_start_date, subscription_end_date, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (phone_number, name, email, subscription_start_date, subscription_end_date))
        
        conn.commit()
        customer_id = c.lastrowid
        conn.close()
        return customer_id

## 2. תיקון process_new_customer_id:

def process_new_customer_id(self, call_id: str, tz: str) -> Dict:
    phone = self.current_calls.get(call_id, {}).get('PBXphone')
    if not phone:
        logger.error("לא נמצא מספר טלפון לשיחה %s", call_id)
        return show_main_menu()
    
    try:
        # בדיקה האם כבר קיים לקוח
        existing = self.db.get_customer_by_phone(phone)
        if existing:
            logger.info("לקוח כבר קיים עבור טלפון %s", phone)
            # אם כבר קיים, בדוק מנוי והמשך
            if self.is_subscription_active(existing):
                return show_main_menu()
            else:
                return handle_subscription_renewal()
        
        # יצירת לקוח חדש
        logger.info("יוצר לקוח חדש עבור טלפון %s עם ת.ז %s", phone, tz)
        customer_id = self.db.create_customer(
            phone_number=phone,
            name=f"לקוח {tz}",  # שם זמני
            subscription_start_date=datetime.now().strftime('%Y-%m-%d'),
            subscription_end_date=(datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
        )
        
        # שמירת פרטי הלקוח בשיחה הנוכחית
        self.current_calls[call_id]['customer_id'] = customer_id
        self.current_calls[call_id]['customer_tz'] = tz
        
        logger.info("נוצר לקוח חדש בהצלחה. ID: %s", customer_id)
        
        # הודעת הצלחה ומעבר לתפריט
        return {
            "type": "simpleMenu",
            "name": "registrationSuccess",
            "times": 1,
            "timeout": 10,
            "enabledKeys": "0",
            "setMusic": "no",
            "files": [{
                "text": "הרשמה הושלמה בהצלחה! ברוך הבא למערכת שלנו. לחץ 0 למעבר לתפריט הראשי.",
                "activatedKeys": "0"
            }]
        }
        
    except Exception as e:
        logger.error("שגיאה ברישום לקוח חדש: %s", e)
        return {
            "type": "simpleMenu",
            "name": "registrationFail",
            "times": 1,
            "timeout": 10,
            "enabledKeys": "1,0",
            "setMusic": "no",
            "files": [{
                "text": "הרשמה נכשלה. לחץ 1 לנסות שוב או 0 לחזרה לתפריט הקודם.",
                "activatedKeys": "1,0"
            }]
        }

## 3. תוספת טיפול בהודעת ההצלחה:

def handle_user_input(self, call_id: str, input_name: str, input_value: str) -> Dict:
    # ... הקוד הקיים ...
    
    # הוסף את השורות האלה לתחילת הפונקציה:
    if input_name == 'registrationSuccess' and input_value == '0':
        return show_main_menu()
    elif input_name == 'registrationFail':
        if input_value == '1':
            return {
                "type": "getDTMF",
                "name": "newCustomerID",
                "max": 10,
                "min": 9,
                "timeout": 30,
                "confirmType": "digits",
                "setMusic": "no",
                "files": [{
                    "text": "אנא הכנס את מספר הזהות שלך שוב.",
                    "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
                }]
            }
        else:  # '0'
            return handle_new_customer()
    
    # ... שאר הקוד הקיים ...

## 4. שיפור handle_pbx_request:

# הוסף לוגיקה טובה יותר לבדיקת פרמטרים בסדר נכון:

# במקום הקוד הנוכחי, השתמש בזה:
PRIORITY = [
    # שלבי רישום
    'registrationSuccess',
    'registrationFail', 
    'newCustomerID',
    'newCustomer',
    'renewSubscription',
    # שלבי הזנה מתקדמים
    'receiptDescription',
    'receiptAmount',
    'cancelReceiptId',
    'numChildren',
    'spouse2_workplaces', 
    'spouse1_workplaces',
    'annualReport',
    'customerMessage',
    # תפריט ראשי בסוף
    'mainMenu',
]

## 5. הוספת imports נדרשים:

# הוסף בתחילת הקובץ:
from datetime import datetime, timedelta
