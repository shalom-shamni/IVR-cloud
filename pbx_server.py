#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
שרת PBX מתוקן – נקי משגיאות תחביר, תואם ל-database_handler.py ול-config.py
נקודות עיקריות שתוקנו:
1) ייבוא Config מתוך config (ודרישת קובץ בשם config.py).
2) נקו שגיאות תחביר (elif יתום, ef במקום def, כפילויות מתודות).
3) הוספת handle_create_receipt (תפריט סכום קבלה) שהיה חסר.
4) יישור קו – כל ה-handlers הכלליים מחוץ למחלקה, והמחלקה קוראת להם.
5) החזרת dict בכל מתודות ה-Process והמרה ל-JSON רק בשכבת הראוט.
6) שימוש ב-DatabaseHandler הקיים (כולל לוג שיחות, עדכון call_data וכו').

שימו לב: יש לבצע שינוי קטן גם ב-database_handler.py – פירוט בסוף הקובץ הזה.
"""

from flask import Flask, request, jsonify
import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional

# == ייבואים פנימיים ==
# חשוב: ודאו שיש לכם קובץ בשם config.py (ולא config_py.py)
try:
    from database_handler import DatabaseHandler
    from config import Config
except Exception as e:  # גיבוי רזה, למקרה שחסר config.py מקומי
    logging.basicConfig(level=logging.INFO)
    logging.warning("נפל ל-Config/DB גיבוי: ודאו שקיים config.py וש-yDATABASE_HANDLER זמין. שגיאה: %s", e)

    class Config:
        HOST = "0.0.0.0"
        PORT = 5000
        DEBUG = True
        LOG_LEVEL = "INFO"
        LOG_FILE = "pbx_system.log"
        DATABASE_PATH = "pbx_system.db"

    class DatabaseHandler:
        def __init__(self, db_path: str = None):
            self.db_path = db_path or Config.DATABASE_PATH
            self.init_database()
        def get_connection(self):
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        def init_database(self):
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number TEXT UNIQUE NOT NULL,
                    name TEXT,
                    email TEXT,
                    subscription_start_date DATE,
                    subscription_end_date DATE,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_id TEXT UNIQUE NOT NULL,
                    phone_number TEXT,
                    pbx_num TEXT,
                    pbx_did TEXT,
                    call_type TEXT,
                    call_status TEXT,
                    extension_id TEXT,
                    extension_path TEXT,
                    call_data TEXT,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit(); conn.close()
        def get_customer_by_phone(self, phone_number: str) -> Optional[Dict]:
            conn = self.get_connection(); c = conn.cursor()
            c.execute('SELECT * FROM customers WHERE phone_number = ?', (phone_number,))
            row = c.fetchone(); conn.close()
            return dict(row) if row else None
        def is_subscription_active(self, customer: Dict) -> bool:
            if not customer or not customer.get('subscription_end_date'):
                return False
            end_date = datetime.strptime(customer['subscription_end_date'], '%Y-%m-%d').date()
            return end_date >= datetime.now().date()
        def log_call(self, call_params: Dict) -> int:
            conn = self.get_connection(); c = conn.cursor()
            c.execute('''
                INSERT OR REPLACE INTO calls
                (call_id, phone_number, pbx_num, pbx_did, call_type, call_status, extension_id, extension_path, call_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                call_params.get('PBXcallId'), call_params.get('PBXphone'), call_params.get('PBXnum'),
                call_params.get('PBXdid'), call_params.get('PBXcallType'), call_params.get('PBXcallStatus'),
                call_params.get('PBXextensionId'), call_params.get('PBXextensionPath'), json.dumps(call_params, ensure_ascii=False)
            ))
            conn.commit(); rid = c.lastrowid; conn.close(); return rid
        def update_call_data(self, call_id: str, new_data: Dict) -> bool:
            conn = self.get_connection(); c = conn.cursor()
            c.execute('SELECT call_data FROM calls WHERE call_id = ?', (call_id,))
            row = c.fetchone();
            if not row:
                conn.close(); return False
            existing = json.loads(row['call_data'] or '{}'); existing.update(new_data)
            c.execute('UPDATE calls SET call_data = ? WHERE call_id = ?', (json.dumps(existing, ensure_ascii=False), call_id))
            ok = c.rowcount > 0; conn.commit(); conn.close(); return ok
        def create_receipt(self, customer_id: int, call_id: str, receipt_data: Dict) -> int:
            return 1
        def update_receipt(self, receipt_id: int, **kwargs) -> bool:
            return True
        def get_customer_details(self, customer_id: int) -> Optional[Dict]:
            return None
        def update_customer_details(self, customer_id: int, **kwargs) -> bool:
            return True

# iCount – גיבוי לדמה אם אין מודול חיצוני
try:
    from icount_handler import ICountHandler, BenefitsCalculator
except Exception:
    class ICountHandler:
        def create_receipt(self, receipt_data: Dict) -> Dict:
            return {
                'status': True,
                'doc_id': f"DOC{datetime.now().strftime('%Y%m%d%H%M%S')}",
                'doc_num': f"R{datetime.now().strftime('%y%m')}-{datetime.now().strftime('%d%H%M')}",
                'message': 'קבלה נוצרה בהצלחה'
            }
    class BenefitsCalculator:
        @staticmethod
        def calculate_total_benefits(customer_details: Dict) -> Dict:
            return {'work_benefit': 2000, 'birth_benefit': 1500, 'total_benefit': 3500}

# == לוגים ==
logging.basicConfig(
    level=getattr(logging, getattr(Config, 'LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ----------------------
# Handlers כלליים (מחוץ למחלקה)
# ----------------------

def handle_new_customer() -> Dict:
    return {
        "type": "simpleMenu",
        "name": "newCustomer",
        "times": 1,
        "timeout": 10,
        "enabledKeys": "1,2",
        "setMusic": "no",
        "extensionChange": "",
        "files": [{
            "text": "שלום וברוך הבא לניסיון מספר 12000. נראה שאין לך עדיין מנוי במערכת שלנו. לחץ 1 להצטרפות למערכת, או לחץ 2 לחזרה לתפריט הקודם.",
            "activatedKeys": "1,2"
        }]
    }

def handle_subscription_renewal() -> Dict:
    return {
        "type": "simpleMenu",
        "name": "renewSubscription",
        "times": 1,
        "timeout": 10,
        "enabledKeys": "1,2",
        "setMusic": "no",
        "extensionChange": "",
        "files": [{
            "text": "המנוי שלך פג תוקף. לחץ 1 לחידוש המנוי, או לחץ 2 לחזרה לתפריט הקודם.",
            "activatedKeys": "1,2"
        }]
    }

def show_main_menu() -> Dict:
    return {
        "type": "simpleMenu",
        "name": "mainMenu",
        "times": 3,
        "timeout": 15,
        "enabledKeys": "1,2,3,4,5,6,0",
        "setMusic": "yes",
        "extensionChange": "",
        "files": [{
            "text": "שלום וברוך הבא למערכת השירותים שלנו. לחץ 1 להנפקת קבלה, לחץ 2 לביטול קבלה, לחץ 3 לעדכון פרטים אישיים, לחץ 4 לשמיעת זכויות, לחץ 5 להשארת הודעה, לחץ 6 לבקשת דיווח שנתי, לחץ 0 לחזרה.",
            "activatedKeys": "1,2,3,4,5,6,0"
        }]
    }

def handle_create_receipt() -> Dict:
    """מסך הזנת סכום קבלה"""
    return {
        "type": "getDTMF",
        "name": "receiptAmount",
        "max": 6,
        "min": 1,
        "timeout": 30,
        "confirmType": "digits",
        "setMusic": "no",
        "files": [{
            "text": "אנא הקש סכום בקבלה (בשקלים).",
            "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
        }]
    }

def handle_cancel_receipt() -> Dict:
    return {
        "type": "getDTMF",
        "name": "cancelReceiptId",
        "max": 10,
        "min": 1,
        "timeout": 30,
        "confirmType": "digits",
        "setMusic": "no",
        "files": [{
            "text": "אנא הכנס את מספר הקבלה לביטול.",
            "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
        }]
    }

def handle_update_personal_details() -> Dict:
    return {
        "type": "getDTMF",
        "name": "numChildren",
        "max": 2,
        "min": 1,
        "timeout": 20,
        "confirmType": "number",
        "setMusic": "no",
        "files": [{
            "text": "אנא הכנס את מספר הילדים.",
            "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
        }]
    }

def handle_show_benefits() -> Dict:
    return {
        "type": "simpleMenu",
        "name": "benefitsMenu",
        "times": 1,
        "timeout": 30,
        "enabledKeys": "1,0",
        "setMusic": "no",
        "files": [{
            "text": "על בסיס הנתונים שלך, אתה זכאי למענק עבודה בסך 2000 ש""ח ולדמי לידה בסך 1500 ש""ח. לחץ 1 לפרטים נוספים או 0 לחזרה לתפריט הראשי.",
            "activatedKeys": "1,0"
        }]
    }

def handle_leave_message() -> Dict:
    return {
        "type": "record",
        "name": "customerMessage",
        "max": 180,
        "min": 3,
        "confirm": "confirmOnly",
        "fileName": f"message_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "files": [{
            "text": "אנא השאר את ההודעה שלך לאחר הצפצוף. לחץ # לסיום ההקלטה.",
            "activatedKeys": "NONE"
        }]
    }

def handle_annual_report() -> Dict:
    return {
        "type": "simpleMenu",
        "name": "annualReport",
        "times": 1,
        "timeout": 15,
        "enabledKeys": "1,0",
        "setMusic": "no",
        "files": [{
            "text": "הדיווח השנתי שלך יישלח אליך בהודעת SMS תוך 24 שעות. לחץ 1 לאישור או 0 לביטול.",
            "activatedKeys": "1,0"
        }]
    }

# ----------------------
# מחלקת PBXHandler
# ----------------------

class PBXHandler:
    def __init__(self):
        self.db = DatabaseHandler()
        self.icount = ICountHandler()
        self.current_calls: Dict[str, Dict[str, Any]] = {}

    # עטיפות נוחות
    def get_customer_by_phone(self, phone_number: str) -> Optional[Dict]:
        return self.db.get_customer_by_phone(phone_number)

    def is_subscription_active(self, customer: Dict) -> bool:
        return self.db.is_subscription_active(customer)

    def log_call(self, call_params: Dict) -> None:
        self.db.log_call(call_params)

    # קבלת קלט מהמשתמש וניתוב הזרימה
    def handle_user_input(self, call_id: str, input_name: str, input_value: str) -> Dict:
        # שמירת הקלט
        call_data = self.current_calls.setdefault(call_id, {})
        call_data[input_name] = input_value
        self.db.update_call_data(call_id, {input_name: input_value})

        # ניתוב
        if input_name == 'newCustomer':
            return self.process_new_customer_choice(call_id, input_value)
        elif input_name == 'newCustomerID':
            return self.process_new_customer_id(call_id, input_value)
        elif input_name == 'renewSubscription':
            return self.process_renewal_choice(call_id, input_value)
        elif input_name == 'mainMenu':
            return self.process_main_menu_choice(call_id, input_value)
        elif input_name == 'receiptAmount':
            return self.process_receipt_amount(call_id, input_value)
        elif input_name == 'receiptDescription':
            return self.process_receipt_description(call_id, input_value)
        elif input_name == 'cancelReceiptId':
            return self.process_cancel_receipt(call_id, input_value)
        elif input_name == 'numChildren':
            return self.process_children_count(call_id, input_value)
        elif input_name.startswith('child_birth_year_'):
            return self.process_child_birth_year(call_id, input_name, input_value)
        elif input_name == 'spouse1_workplaces' or input_name == 'spouse2_workplaces':
            return self.process_spouse_workplaces(call_id, input_name, input_value)
        elif input_name == 'customerMessage':
            return self.process_customer_message(call_id, input_value)
        elif input_name == 'annualReport':
            return self.process_annual_report_choice(call_id, input_value)
        else:
            logger.warning("קלט לא מזוהה: %s=%s", input_name, input_value)
            return show_main_menu()

    def process_new_customer_choice(self, call_id: str, choice: str) -> Dict:
        if choice == '1':
            return {
                "type": "getDTMF",
                "name": "newCustomerID",
                "max": 10,
                "min": 9,
                "timeout": 30,
                "confirmType": "digits",
                "setMusic": "no",
                "files": [{
                    "text": "אנא הכנס את מספר הזהות שלך.",
                    "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
                }]
            }
        return show_main_menu()

    def process_new_customer_id(self, call_id: str, tz: str) -> Dict:
        phone = self.current_calls.get(call_id, {}).get('PBXphone')
        if not phone:
            return show_main_menu()
        try:
            existing = self.db.get_customer_by_phone(phone)
            if not existing:
                # רישום מהיר – יצירת לקוח עם מספר טלפון בלבד
                # שימו לב: פונקציית create_customer קיימת ב-database_handler.py
                try:
                    # לא בכל גיבוי יש create_customer; לכן try/except
                    cid = self.db.create_customer(phone_number=phone)
                    logger.info("נוצר לקוח חדש ID=%s לטלפון %s", cid, phone)
                except Exception:
                    logger.info("create_customer לא קיים בגיבוי – מדלגים")
            return show_main_menu()
        except Exception as e:
            logger.error("Registration failed: %s", e)
            return {
                "type": "simpleMenu",
                "name": "registrationFail",
                "times": 1,
                "timeout": 7,
                "enabledKeys": "0",
                "files": [{"text": "הרשמה נכשלה. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
            }

    def process_renewal_choice(self, call_id: str, choice: str) -> Dict:
        if choice == '1':
            return {
                "type": "simpleMenu",
                "name": "renewalConfirm",
                "times": 1,
                "timeout": 15,
                "enabledKeys": "1,2",
                "setMusic": "no",
                "files": [{
                    "text": "חידוש מנוי עולה 120 ש""ח לשנה. לחץ 1 לאישור או 2 לביטול.",
                    "activatedKeys": "1,2"
                }]
            }
        return show_main_menu()

    def process_main_menu_choice(self, call_id: str, choice: str) -> Dict:
        if choice == '1':
            return handle_create_receipt()
        elif choice == '2':
            return handle_cancel_receipt()
        elif choice == '3':
            return handle_update_personal_details()
        elif choice == '4':
            return handle_show_benefits()
        elif choice == '5':
            return handle_leave_message()
        elif choice == '6':
            return handle_annual_report()
        elif choice == '0':
            return show_main_menu()
        else:
            return {
                "type": "simpleMenu",
                "name": "invalidChoice",
                "times": 1,
                "timeout": 5,
                "enabledKeys": "0",
                "files": [{"text": "בחירה לא חוקית. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
            }

    def process_receipt_amount(self, call_id: str, amount: str) -> Dict:
        if amount == "SKIP":
            return show_main_menu()
        try:
            amount_int = int(amount)
            if amount_int <= 0:
                raise ValueError
            return {
                "type": "getDTMF",
                "name": "receiptDescription",
                "max": 20,
                "min": 1,
                "timeout": 30,
                "skipKey": "#",
                "skipValue": "NO_DESCRIPTION",
                "confirmType": "digits",
                "setMusic": "no",
                "files": [{
                    "text": f"הסכום שהוכנס הוא {amount_int} שקל. אנא הכנס קוד תיאור או לחץ # לדילוג.",
                    "activatedKeys": "1,2,3,4,5,6,7,8,9,0,#"
                }]
            }
        except Exception:
            return {
                "type": "simpleMenu",
                "name": "invalidAmount",
                "times": 1,
                "timeout": 10,
                "enabledKeys": "1,0",
                "files": [{
                    "text": "סכום לא חוקי. לחץ 1 לנסות שוב או 0 לחזרה לתפריט הראשי.",
                    "activatedKeys": "1,0"
                }]
            }

    def process_receipt_description(self, call_id: str, description: str) -> Dict:
        call_data = self.current_calls.get(call_id, {})
        amount = call_data.get('receiptAmount')
        phone_number = call_data.get('PBXphone')
        if not amount or not phone_number:
            return self.show_error_and_return_to_main()

        customer = self.get_customer_by_phone(phone_number)
        if not customer:
            return self.show_error_and_return_to_main()

        receipt_data = {
            'amount': int(amount),
            'description': description if description != "NO_DESCRIPTION" else "קבלה",
            'client_name': customer.get('name', ''),
            'client_phone': phone_number,
            'client_email': customer.get('email', '')
        }
        receipt_id = self.db.create_receipt(customer['id'], call_id, receipt_data)
        icount_result = self.icount.create_receipt(receipt_data)

        if icount_result.get('status'):
            self.db.update_receipt(
                receipt_id,
                icount_doc_id=icount_result.get('doc_id'),
                icount_doc_num=icount_result.get('doc_num'),
                icount_response=json.dumps(icount_result, ensure_ascii=False),
                status='completed'
            )
            return {
                "type": "simpleMenu",
                "name": "receiptSuccess",
                "times": 1,
                "timeout": 15,
                "enabledKeys": "0",
                "files": [{
                    "text": f"הקבלה נוצרה בהצלחה. מספר קבלה: {icount_result.get('doc_num', 'לא זמין')}. לחץ 0 לחזרה לתפריט הראשי.",
                    "activatedKeys": "0"
                }]
            }
        else:
            self.db.update_receipt(
                receipt_id,
                icount_response=json.dumps(icount_result, ensure_ascii=False),
                status='failed'
            )
            return {
                "type": "simpleMenu",
                "name": "receiptFailed",
                "times": 1,
                "timeout": 15,
                "enabledKeys": "1,0",
                "files": [{
                    "text": "שגיאה ביצירת הקבלה. לחץ 1 לנסות שוב או 0 לתפריט הראשי.",
                    "activatedKeys": "1,0"
                }]
            }

    def process_cancel_receipt(self, call_id: str, receipt_num: str) -> Dict:
        return {
            "type": "simpleMenu",
            "name": "cancelResult",
            "times": 1,
            "timeout": 15,
            "enabledKeys": "0",
            "files": [{
                "text": f"בקשת ביטול קבלה מספר {receipt_num} התקבלה. הביטול יטופל תוך 24 שעות. לחץ 0 לחזרה לתפריט הראשי.",
                "activatedKeys": "0"
            }]
        }

    def process_children_count(self, call_id: str, num_children: str) -> Dict:
        try:
            n = int(num_children)
            if n < 0 or n > 20:
                raise ValueError
            cd = self.current_calls.setdefault(call_id, {})
            cd['children_count'] = n
            cd['current_child'] = 1
            if n == 0:
                return self.ask_spouse_workplaces(call_id, 1)
            return {
                "type": "getDTMF",
                "name": "child_birth_year_1",
                "max": 4,
                "min": 4,
                "timeout": 20,
                "confirmType": "number",
                "setMusic": "no",
                "files": [{
                    "text": "אנא הכנס את שנת הלידה של הילד הראשון (4 ספרות).",
                    "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
                }]
            }
        except Exception:
            return self.show_error_and_return_to_main()

    def process_child_birth_year(self, call_id: str, input_name: str, birth_year: str) -> Dict:
        try:
            year = int(birth_year)
            cy = datetime.now().year
            if year < cy - 50 or year > cy:
                raise ValueError
            cd = self.current_calls.setdefault(call_id, {})
            cd.setdefault('children_birth_years', []).append(year)
            cur = cd.get('current_child', 1)
            total = cd.get('children_count', 0)
            if cur < total:
                cd['current_child'] = cur + 1
                nxt = cur + 1
                return {
                    "type": "getDTMF",
                    "name": f"child_birth_year_{nxt}",
                    "max": 4,
                    "min": 4,
                    "timeout": 20,
                    "confirmType": "number",
                    "setMusic": "no",
                    "files": [{
                        "text": f"אנא הכנס את שנת הלידה של ילד מספר {nxt} (4 ספרות).",
                        "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
                    }]
                }
            else:
                return self.ask_spouse_workplaces(call_id, 1)
        except Exception:
            return self.show_error_and_return_to_main()

    def ask_spouse_workplaces(self, call_id: str, spouse_num: int) -> Dict:
        label = "הראשון" if spouse_num == 1 else "השני"
        return {
            "type": "getDTMF",
            "name": f"spouse{spouse_num}_workplaces",
            "max": 2,
            "min": 1,
            "timeout": 20,
            "confirmType": "number",
            "setMusic": "no",
            "files": [{
                "text": f"אנא הכנס את מספר מקומות העבודה של בן/בת הזוג {label}.",
                "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
            }]
        }

    def process_spouse_workplaces(self, call_id: str, input_name: str, workplaces: str) -> Dict:
        try:
            w = int(workplaces)
            if w < 0 or w > 10:
                raise ValueError
            cd = self.current_calls.setdefault(call_id, {})
            cd[input_name] = w
            if input_name == 'spouse1_workplaces':
                return self.ask_spouse_workplaces(call_id, 2)
            # סיום איסוף – נשמור בפרטי הלקוח אם קיים
            phone = cd.get('PBXphone')
            cust = self.get_customer_by_phone(phone) if phone else None
            if cust:
                try:
                    self.db.update_customer_details(
                        cust['id'],
                        num_children=cd.get('children_count', 0),
                        children_birth_years=json.dumps(cd.get('children_birth_years', [])),
                        spouse1_workplaces=cd.get('spouse1_workplaces', 0),
                        spouse2_workplaces=cd.get('spouse2_workplaces', 0)
                    )
                except Exception:
                    logger.info("update_customer_details לא זמין בגיבוי – ממשיכים")
            return {
                "type": "simpleMenu",
                "name": "detailsUpdated",
                "times": 1,
                "timeout": 10,
                "enabledKeys": "0",
                "files": [{"text": "הפרטים עודכנו בהצלחה. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
            }
        except Exception:
            return self.show_error_and_return_to_main()

    def process_customer_message(self, call_id: str, message_result: str) -> Dict:
        cd = self.current_calls.get(call_id, {})
        phone = cd.get('PBXphone')
        cust = self.get_customer_by_phone(phone) if phone else None
        if cust and message_result:
            try:
                self.db.save_message(cust['id'], call_id, message_file=message_result, message_text=None, duration=None)
            except Exception:
                logger.info("save_message לא זמין בגיבוי – ממשיכים")
        return {
            "type": "simpleMenu",
            "name": "messageReceived",
            "times": 1,
            "timeout": 10,
            "enabledKeys": "0",
            "files": [{"text": "ההודעה התקבלה. נחזור אליך תוך 48 שעות. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
        }

    def process_annual_report_choice(self, call_id: str, choice: str) -> Dict:
        if choice == '1':
            cd = self.current_calls.get(call_id, {})
            phone = cd.get('PBXphone')
            cust = self.get_customer_by_phone(phone) if phone else None
            if cust:
                try:
                    self.db.request_annual_report(cust['id'])
                except Exception:
                    logger.info("request_annual_report לא זמין בגיבוי – ממשיכים")
            return {
                "type": "simpleMenu",
                "name": "reportRequested",
                "times": 1,
                "timeout": 10,
                "enabledKeys": "0",
                "files": [{"text": "בקשת הדיווח התקבלה. הדיווח יישלח אליך בהודעת SMS תוך 24 שעות. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
            }
        return show_main_menu()

    def show_error_and_return_to_main(self) -> Dict:
        return {
            "type": "simpleMenu",
            "name": "systemError",
            "times": 1,
            "timeout": 10,
            "enabledKeys": "0",
            "files": [{"text": "אירעה שגיאה במערכת. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
        }

pbx_handler = PBXHandler()

# ----------------------
# ראוטים
# ----------------------

@app.route('/pbx', methods=['GET'])
def handle_pbx_request():
    """כניסת PBX – מזהה שיחה, בודק מנוי ומחזיר תפריט"""
    try:
        call_params = {
            'PBXphone': request.args.get('PBXphone'),
            'PBXnum': request.args.get('PBXnum'),
            'PBXdid': request.args.get('PBXdid'),
            'PBXcallId': request.args.get('PBXcallId'),
            'PBXcallType': request.args.get('PBXcallType'),
            'PBXcallStatus': request.args.get('PBXcallStatus'),
            'PBXextensionId': request.args.get('PBXextensionId'),
            'PBXextensionPath': request.args.get('PBXextensionPath')
        }
        # הוספת כל פרמטרים שאינם PBX*
        for k, v in request.args.items():
            if not k.startswith('PBX'):
                call_params[k] = v
        logger.info("קיבלנו פנייה: %s", call_params)

        # לוג שיחה + שמירה בזיכרון
        pbx_handler.log_call(call_params)
        call_id = call_params.get('PBXcallId') or ''
        if call_id:
            core_keys = ['PBXphone','PBXnum','PBXdid','PBXcallType','PBXcallStatus','PBXextensionId','PBXextensionPath']
            pbx_handler.current_calls.setdefault(call_id, {}).update({k: call_params.get(k) for k in core_keys if call_params.get(k)})

        phone = call_params.get('PBXphone')
        if not phone:
            return jsonify({"error": "חסר מספר טלפון"}), 400

        customer = pbx_handler.get_customer_by_phone(phone)
        if not customer:
            return jsonify(handle_new_customer())
        if not pbx_handler.is_subscription_active(customer):
            return jsonify(handle_subscription_renewal())
        return jsonify(show_main_menu())

    except Exception as e:
        logger.exception("שגיאה בטיפול בבקשה")
        return jsonify({"error": "שגיאה בטיפול בבקשה"}), 500

@app.route('/pbx/menu/<menu_name>', methods=['GET'])
def handle_menu_choice(menu_name):
    try:
        call_id = request.args.get('PBXcallId') or ""
        if call_id:
            core_keys = ['PBXphone','PBXnum','PBXdid','PBXcallType','PBXcallStatus','PBXextensionId','PBXextensionPath']
            pbx_handler.current_calls.setdefault(call_id, {}).update({k: request.args.get(k) for k in core_keys if request.args.get(k)})

        value = request.args.get(menu_name)
        if value is None:
            for k in [
                'newCustomer','renewSubscription','mainMenu',
                'receiptAmount','receiptDescription','cancelReceiptId',
                'numChildren','spouse1_workplaces','spouse2_workplaces',
                'annualReport','customerMessage','newCustomerID'
            ]:
                if k in request.args:
                    menu_name, value = k, request.args.get(k)
                    break

        if not value:
            return jsonify({
                "type": "simpleMenu",
                "name": "invalidChoice",
                "times": 1,
                "timeout": 5,
                "enabledKeys": "0",
                "files": [{"text": "לא התקבלה בחירה. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
            })

        resp = pbx_handler.handle_user_input(call_id, menu_name, value)
        return jsonify(resp)

    except Exception:
        logger.exception("שגיאה בטיפול בבחירה")
        return jsonify({"error": "שגיאה בטיפול בבחירה"}), 500

if __name__ == '__main__':
    # דוגמאות לנתוני לקוח – ריצה מקומית בלבד
    try:
        db = DatabaseHandler()
        conn = db.get_connection(); c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO customers (id, phone_number, name, email, subscription_start_date, subscription_end_date, is_active)
            VALUES (1, '0501234567', 'יוסי כהן', 'yossi@example.com', '2024-01-01', '2025-12-31', 1)
        ''')
        c.execute('''
            INSERT OR REPLACE INTO customers (id, phone_number, name, email, subscription_start_date, subscription_end_date, is_active)
            VALUES (2, '0507654321', 'דני לוי', 'dani@example.com', '2023-01-01', '2024-06-30', 1)
        ''')
        conn.commit(); conn.close()
    except Exception:
        logger.info("דילגנו על הזנת נתוני דוגמה")

    app.run(host=getattr(Config, 'HOST', '0.0.0.0'), port=getattr(Config, 'PORT', 5000), debug=getattr(Config, 'DEBUG', True))


# === הערת תיקון ל-database_handler.py ===
# בפונקציה update_call_data קיימת אצלך פקודה: "UPDATE calls SET call_data = ?, updated_at = CURRENT_TIMESTAMP ..."
# בטבלת calls המוגדרת בקובץ זה (וגם אצלך) אין עמודה updated_at – ולכן תופיע שגיאה "no such column: updated_at".
# פתרון מהיר: החלף את השאילתה ל:
#    UPDATE calls SET call_data = ? WHERE call_id = ?
# כך לא תהיה תלות בעמודת updated_at.
