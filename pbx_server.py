#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify
import json
import logging
import sqlite3
import os
from datetime import datetime
from typing import Dict, Any, Optional

# ייבוא המודולים שלנו
try:
    from database_handler import DatabaseHandler
    from icount_handler import ICountHandler, BenefitsCalculator
    from config import Config
except ImportError:
    # אם המודולים לא קיימים, ניצור תחליפים בסיסיים
    class Config:
        LOG_LEVEL = 'INFO'
        LOG_FILE = 'pbx_system.log'
        DATABASE_PATH = 'pbx_system.db'
    
    class DatabaseHandler:
        def __init__(self):
            self.db_path = Config.DATABASE_PATH
            self.init_database()
        
        def init_database(self):
            """יצירת מבנה מאגר הנתונים"""
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # טבלת לקוחות
            cursor.execute('''
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
            ''')
            
            # טבלת פרטים אישיים לזכויות
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS customer_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER,
                    num_children INTEGER DEFAULT 0,
                    children_birth_years TEXT, -- JSON array של שנות לידה
                    spouse1_workplaces INTEGER DEFAULT 0,
                    spouse2_workplaces INTEGER DEFAULT 0,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers (id)
                )
            ''')
            
            # טבלת שיחות
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_id TEXT UNIQUE,
                    phone_number TEXT,
                    pbx_num TEXT,
                    pbx_did TEXT,
                    call_type TEXT,
                    call_status TEXT,
                    extension_id TEXT,
                    extension_path TEXT,
                    call_data TEXT, -- JSON של כל הנתונים שנאספו
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ended_at DATETIME
                )
            ''')
            
            # טבלת קבלות
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER,
                    call_id TEXT,
                    receipt_data TEXT, -- JSON של פרטי הקבלה
                    icount_doc_id TEXT,
                    icount_doc_num TEXT,
                    icount_response TEXT, -- תגובה מ-iCount
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers (id)
                )
            ''')
            
            # טבלת הודעות
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER,
                    call_id TEXT,
                    message_file TEXT,
                    duration INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers (id)
                )
            ''')
            
            # טבלת בקשות דיווחים
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS annual_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER,
                    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (customer_id) REFERENCES customers (id)
                )
            ''')
            
            conn.commit()
            conn.close()
        
        def get_customer_by_phone(self, phone_number: str) -> Optional[Dict]:
            """קבלת פרטי לקוח לפי מספר טלפון"""
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM customers WHERE phone_number = ?', (phone_number,))
            customer = cursor.fetchone()
            conn.close()
            
            return dict(customer) if customer else None
        
        def is_subscription_active(self, customer: Dict) -> bool:
            """בדיקת תוקף מנוי"""
            if not customer or not customer.get('subscription_end_date'):
                return False
            
            end_date = datetime.strptime(customer['subscription_end_date'], '%Y-%m-%d')
            return end_date >= datetime.now()
        
        def log_call(self, call_params: Dict):
            """רישום שיחה במאגר נתונים"""
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO calls 
                (call_id, phone_number, pbx_num, pbx_did, call_type, call_status, 
                 extension_id, extension_path, call_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                call_params.get('PBXcallId'),
                call_params.get('PBXphone'),
                call_params.get('PBXnum'),
                call_params.get('PBXdid'),
                call_params.get('PBXcallType'),
                call_params.get('PBXcallStatus'),
                call_params.get('PBXextensionId'),
                call_params.get('PBXextensionPath'),
                json.dumps(call_params, ensure_ascii=False)
            ))
            
            conn.commit()
            conn.close()
        
        def update_call_data(self, call_id: str, data: Dict):
            """עדכון נתוני שיחה"""
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT call_data FROM calls WHERE call_id = ?', (call_id,))
            result = cursor.fetchone()
            
            if result:
                existing_data = json.loads(result[0] or '{}')
                existing_data.update(data)
                
                cursor.execute(
                    'UPDATE calls SET call_data = ? WHERE call_id = ?',
                    (json.dumps(existing_data, ensure_ascii=False), call_id)
                )
            
            conn.commit()
            conn.close()
        
        def create_receipt(self, customer_id: int, call_id: str, receipt_data: Dict) -> int:
            """יצירת קבלה במאגר נתונים"""
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO receipts (customer_id, call_id, receipt_data)
                VALUES (?, ?, ?)
            ''', (customer_id, call_id, json.dumps(receipt_data, ensure_ascii=False)))
            
            receipt_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return receipt_id
        
        def update_receipt(self, receipt_id: int, **kwargs):
            """עדכון קבלה"""
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            fields = []
            values = []
            
            for key, value in kwargs.items():
                fields.append(f"{key} = ?")
                values.append(value)
            
            if fields:
                values.append(receipt_id)
                cursor.execute(f"UPDATE receipts SET {', '.join(fields)} WHERE id = ?", values)
            
            conn.commit()
            conn.close()
        
        def get_customer_details(self, customer_id: int) -> Optional[Dict]:
            """קבלת פרטי לקוח מפורטים"""
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM customer_details WHERE customer_id = ?', (customer_id,))
            details = cursor.fetchone()
            conn.close()
            
            return dict(details) if details else None
        
        def update_customer_details(self, customer_id: int, **kwargs):
            """עדכון פרטי לקוח"""
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # בדיקה אם יש כבר רשומה
            cursor.execute('SELECT id FROM customer_details WHERE customer_id = ?', (customer_id,))
            existing = cursor.fetchone()
            
            if existing:
                fields = []
                values = []
                for key, value in kwargs.items():
                    fields.append(f"{key} = ?")
                    values.append(value)
                
                if fields:
                    values.append(customer_id)
                    cursor.execute(
                        f"UPDATE customer_details SET {', '.join(fields)} WHERE customer_id = ?",
                        values
                    )
            else:
                # יצירת רשומה חדשה
                fields = ['customer_id'] + list(kwargs.keys())
                values = [customer_id] + list(kwargs.values())
                placeholders = ','.join(['?'] * len(values))
                
                cursor.execute(
                    f"INSERT INTO customer_details ({','.join(fields)}) VALUES ({placeholders})",
                    values
                )
            
            conn.commit()
            conn.close()
        
        def save_message(self, customer_id: int, call_id: str, message_file: str, duration: int):
            """שמירת הודעה"""
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO messages (customer_id, call_id, message_file, duration)
                VALUES (?, ?, ?, ?)
            ''', (customer_id, call_id, message_file, duration))
            
            conn.commit()
            conn.close()
        
        def request_annual_report(self, customer_id: int):
            """רישום בקשת דיווח שנתי"""
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO annual_reports (customer_id)
                VALUES (?)
            ''', (customer_id,))
            
            conn.commit()
            conn.close()
    
    class ICountHandler:
        def create_receipt(self, receipt_data: Dict) -> Dict:
            """יצירת קבלה ב-iCount (דמה)"""
            return {
                'status': True,
                'doc_id': f"DOC{datetime.now().strftime('%Y%m%d%H%M%S')}",
                'doc_num': f"R{datetime.now().strftime('%y%m')}-{datetime.now().strftime('%d%H%M')}",
                'message': 'קבלה נוצרה בהצלחה'
            }
    
    class BenefitsCalculator:
        @staticmethod
        def calculate_total_benefits(customer_details: Dict) -> Dict:
            """חישוב זכויות (דמה)"""
            work_benefit = 2000
            birth_benefit = customer_details.get('num_children', 0) * 500
            
            return {
                'work_benefit': work_benefit,
                'birth_benefit': birth_benefit,
                'total_benefit': work_benefit + birth_benefit
            }

# הגדרת לוגים
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class PBXHandler:
    def __init__(self):
        self.db = DatabaseHandler()
        self.icount = ICountHandler()
        self.current_calls = {}  # אחסון זמני של נתוני שיחות
    
    def get_customer_by_phone(self, phone_number: str) -> Optional[Dict]:
        """קבלת פרטי לקוח לפי מספר טלפון"""
        return self.db.get_customer_by_phone(phone_number)
    
    def is_subscription_active(self, customer: Dict) -> bool:
        """בדיקת תוקף מנוי"""
        return self.db.is_subscription_active(customer)
    
    def handle_user_input(self, call_id: str, input_name: str, input_value: str) -> Dict:
        """טיפול בקלט מהמשתמש"""
        # שמירת הקלט בנתוני השיחה
        call_data = self.current_calls.get(call_id, {})
        call_data[input_name] = input_value
        self.current_calls[call_id] = call_data
        
        # עדכון במאגר הנתונים
        self.db.update_call_data(call_id, {input_name: input_value})
        
        # טיפול לפי סוג הקלט
        if input_name == 'newCustomer':
            return self.process_new_customer_choice(call_id, input_value)
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
        elif input_name == 'spouse1_workplaces':
            return self.process_spouse_workplaces(call_id, input_name, input_value)
        elif input_name == 'spouse2_workplaces':
            return self.process_spouse_workplaces(call_id, input_name, input_value)
        elif input_name == 'customerMessage':
            return self.process_customer_message(call_id, input_value)
        elif input_name == 'annualReport':
            return self.process_annual_report_choice(call_id, input_value)
        else:
            logger.warning(f"קלט לא מזוהה: {input_name}={input_value}")
            return show_main_menu()
    
    def process_new_customer_choice(self, call_id: str, choice: str) -> Dict:
        """טיפול בבחירת לקוח חדש"""
        if choice == '1':
            return {
                "type": "getDTMF",
                "name": "newCustomerID",
                "max": 10,
                "min": 9,
                "timeout": 30,
                "confirmType": "digits",
                "setMusic": "no",
                "files": [
                    {
                        "text": "אנא הכנס את מספר הזהות שלך.",
                        "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
                    }
                ]
            }
        else:
            return show_main_menu()
    
    def process_renewal_choice(self, call_id: str, choice: str) -> Dict:
        """טיפול בבחירת חידוש מנוי"""
        if choice == '1':
            return {
                "type": "simpleMenu",
                "name": "renewalConfirm",
                "times": 1,
                "timeout": 15,
                "enabledKeys": "1,2",
                "setMusic": "no",
                "files": [
                    {
                        "text": "חידוש מנוי עולה 120 שקל לשנה. לחץ 1 לאישור או 2 לביטול.",
                        "activatedKeys": "1,2"
                    }
                ]
            }
        else:
            return show_main_menu()
    
    def process_main_menu_choice(self, call_id: str, choice: str) -> Dict:
        """טיפול בבחירות מהתפריט הראשי"""
        if choice == '1':
            return handle_create_receipt()
        elif choice == '2':
            return handle_cancel_receipt()
        elif choice == '3':
            return handle_update_personal_details()
        elif choice == '4':
            return self.handle_show_benefits(call_id)
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
                "setMusic": "no",
                "files": [
                    {
                        "text": "בחירה לא חוקית. לחץ 0 לחזרה לתפריט הראשי.",
                        "activatedKeys": "0"
                    }
                ]
            }
    
    def process_receipt_amount(self, call_id: str, amount: str) -> Dict:
        """טיפול בסכום הקבלה"""
        if amount == "SKIP":
            return show_main_menu()
        
        try:
            amount_int = int(amount)
            if amount_int <= 0:
                raise ValueError("סכום חייב להיות חיובי")
            
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
                "files": [
                    {
                        "text": f"הסכום שהוכנס הוא {amount_int} שקל. אנא הכנס קוד תיאור או לחץ # לדילוג.",
                        "activatedKeys": "1,2,3,4,5,6,7,8,9,0,#"
                    }
                ]
            }
        except ValueError:
            return {
                "type": "simpleMenu",
                "name": "invalidAmount",
                "times": 1,
                "timeout": 10,
                "enabledKeys": "1,0",
                "setMusic": "no",
                "files": [
                    {
                        "text": "סכום לא חוקי. לחץ 1 לנסות שוב או 0 לחזרה לתפריט הראשי.",
                        "activatedKeys": "1,0"
                    }
                ]
            }
    
    def process_receipt_description(self, call_id: str, description: str) -> Dict:
        """טיפול בתיאור הקבלה ויצירתה"""
        call_data = self.current_calls.get(call_id, {})
        amount = call_data.get('receiptAmount')
        phone_number = call_data.get('PBXphone')
        
        if not amount or not phone_number:
            logger.error(f"חסרים נתונים ליצירת קבלה: {call_data}")
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
        
        if icount_result['status']:
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
                "setMusic": "no",
                "files": [
                    {
                        "text": f"הקבלה נוצרה בהצלחה. מספר קבלה: {icount_result.get('doc_num', 'לא זמין')}. לחץ 0 לחזרה לתפריט הראשי.",
                        "activatedKeys": "0"
                    }
                ]
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
                "setMusic": "no",
                "files": [
                    {
                        "text": f"שגיאה ביצירת הקבלה. לחץ 1 לנסות שוב או 0 לתפריט הראשי.",
                        "activatedKeys": "1,0"
                    }
                ]
            }
    
    def process_cancel_receipt(self, call_id: str, receipt_num: str) -> Dict:
        """טיפול בביטול קבלה"""
        return {
            "type": "simpleMenu",
            "name": "cancelResult",
            "times": 1,
            "timeout": 15,
            "enabledKeys": "0",
            "setMusic": "no",
            "files": [
                {
                    "text": f"בקשת ביטול קבלה מספר {receipt_num} התקבלה. הביטול יטופל תוך 24 שעות. לחץ 0 לחזרה לתפריט הראשי.",
                    "activatedKeys": "0"
                }
            ]
        }
    
    def process_children_count(self, call_id: str, num_children: str) -> Dict:
        """טיפול במספר הילדים"""
        try:
            children_count = int(num_children)
            if children_count < 0 or children_count > 20:
                raise ValueError("מספר ילדים לא סביר")
            
            call_data = self.current_calls.get(call_id, {})
            call_data['children_count'] = children_count
            call_data['current_child'] = 1
            self.current_calls[call_id] = call_data
            
            if children_count == 0:
                return self.ask_spouse_workplaces(call_id, 1)
            else:
                return {
                    "type": "getDTMF",
                    "name": "child_birth_year_1",
                    "max": 4,
                    "min": 4,
                    "timeout": 20,
                    "confirmType": "number",
                    "setMusic": "no",
                    "files": [
                        {
                            "text": "אנא הכנס את שנת הלידה של הילד הראשון (4 ספרות).",
                            "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
                        }
                    ]
                }
        except ValueError:
            return self.show_error_and_return_to_main()
    
    def process_child_birth_year(self, call_id: str, input_name: str, birth_year: str) -> Dict:
        """טיפול בשנת לידה של ילד"""
        try:
            year = int(birth_year)
            current_year = datetime.now().year
            
            if year < current_year - 50 or year > current_year:
                raise ValueError("שנת לידה לא סבירה")
            
            call_data = self.current_calls.get(call_id, {})
            if 'children_birth_years' not in call_data:
                call_data['children_birth_years'] = []
            call_data['children_birth_years'].append(year)
            
            current_child = call_data.get('current_child', 1)
            total_children = call_data.get('children_count', 0)
            
            if current_child < total_children:
                call_data['current_child'] = current_child + 1
                self.current_calls[call_id] = call_data
                
                return {
                    "type": "getDTMF",
                    "name": f"child_birth_year_{current_child + 1}",
                    "max": 4,
                    "min": 4,
                    "timeout": 20,
                    "confirmType": "number",
                    "setMusic": "no",
                    "files": [
                        {
                            "text": f"אנא הכנס את שנת הלידה של ילד מספר {current_child + 1} (4 ספרות).",
                            "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
                        }
                    ]
                }
            else:
                self.current_calls[call_id] = call_data
                return self.ask_spouse_workplaces(call_id, 1)
                
        except ValueError:
            return self.show_error_and_return_to_main()
    
    def ask_spouse_workplaces(self, call_id: str, spouse_num: int) -> Dict:
        """שאלה על מקומות עבודה של בן/בת זוג"""
        spouse_text = "הראשון" if spouse_num == 1 else "השני"
        
        return {
            "type": "getDTMF",
            "name": f"spouse{spouse_num}_workplaces",
            "max": 2,
            "min": 1,
            "timeout": 20,
            "confirmType": "number",
            "setMusic": "no",
            "files": [
                {
                    "text": f"אנא הכנס את מספר מקומות העבודה של בן/בת הזוג {spouse_text}.",
                    "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
                }
            ]
        }
    
    def process_spouse_workplaces(self, call_id: str, input_name: str, workplaces: str) -> Dict:
        """טיפול במספר מקומות עבודה"""
        try:
            workplaces_count = int(workplaces)
            if workplaces_count < 0 or workplaces_count > 10:
                raise ValueError("מספר מקומות עבודה לא סביר")
            
            call_data = self.current_calls.get(call_id, {})
            call_data[input_name] = workplaces_count
            self.current_calls[call_id] = call_data
            
            if input_name == 'spouse1_workplaces':
                return self.ask_spouse_workplaces(call_id, 2)
            else:
                phone_number = call_data.get('PBXphone')
                customer = self.get_customer_by_phone(phone_number)
                
                if customer:
                    self.db.update_customer_details(
                        customer['id'],
                        num_children=call_data.get('children_count', 0),
                        children_birth_years=json.dumps(call_data.get('children_birth_years', [])),
                        spouse1_workplaces=call_data.get('spouse1_workplaces', 0),
                        spouse2_workplaces=call_data.get('spouse2_workplaces', 0)
                    )
                
                return {
                    "type": "simpleMenu",
                    "name": "detailsUpdated",
                    "times": 1,
                    "timeout": 10,
                    "enabledKeys": "0",
                    "setMusic": "no",
                    "files": [
                        {
                            "text": "הפרטים עודכנו בהצלחה. לחץ 0 לחזרה לתפריט הראשי.",
                            "activatedKeys": "0"
                        }
                    ]
                }
        except ValueError:
            return self.show_error_and_return_to_main()
    
    def process_customer_message(self, call_id: str, message_result: str) -> Dict:
        """טיפול בהודעה שהושארה"""
        call_data = self.current_calls.get(call_id, {})
        phone_number = call_data.get('PBXphone')
        customer = self.get_customer_by_phone(phone_number)
        
        if customer and message_result:
            self.db.save_message(
                customer['id'],
                call_id,
                message_file=message_result,
                duration=None
            )
        
        return {
            "type": "simpleMenu",
            "name": "messageReceived",
            "times": 1,
            "timeout": 10,
            "enabledKeys": "0",
            "setMusic": "no",
            "files": [
                {
                    "text": "ההודעה התקבלה. נחזור אליך תוך 48 שעות. לחץ 0 לחזרה לתפריט הראשי.",
                    "activatedKeys": "0"
                }
            ]
        }
    
    def process_annual_report_choice(self, call_id: str, choice: str) -> Dict:
        """טיפול בבחירת דיווח שנתי"""
        if choice == '1':
            call_data = self.current_calls.get(call_id, {})
            phone_number = call_data.get('PBXphone')
            customer = self.get_customer_by_phone(phone_number)
            
            if customer:
                self.db.request_annual_report(customer['id'])
            
            return {
                "type": "simpleMenu",
                "name": "reportRequested",
                "times": 1,
                "timeout": 10,
                "enabledKeys": "0",
                "setMusic": "no",
                "files": [
                    {
                        "text": "בקשת הדיווח התקבלה. הדיווח יישלח אליך בהודעת SMS תוך 24 שעות. לחץ 0 לחזרה לתפריט הראשי.",
                        "activatedKeys": "0"
                    }
                ]
            }
        else:
            return show_main_menu()
    
    def handle_show_benefits(self, call_id: str) -> Dict:
        """הצגת זכויות"""
        call_data = self.current_calls.get(call_id, {})
        phone_number = call_data.get('PBXphone')
        
        if phone_number:
            customer = self.get_customer_by_phone(phone_number)
            if customer:
                details = self.db.get_customer_details(customer['id'])
                if details:
                    benefits = BenefitsCalculator.calculate_total_benefits(details)
                    
                    return {
                        "type": "simpleMenu",
                        "name": "benefitsDisplay",
                        "times": 1,
                        "timeout": 30,
                        "enabledKeys": "1,0",
                        "setMusic": "no",
                        "files": [
                            {
                                "text": f"על בסיس הנתונים שלך, אתה זכאי למענק עבודה בסך {benefits['work_benefit']:.0f} שקל ולדמי לידה בסך {benefits['birth_benefit']:.0f} שקל. סה\"כ {benefits['total_benefit']:.0f} שקל. לחץ 1 לפרטים נוספים או 0 לחזרה לתפריט הראשי.",
                                "activatedKeys": "1,0"
                            }
                        ]
                    }
        
        return {
            "type": "simpleMenu",
            "name": "benefitsMenu",
            "times": 1,
            "timeout": 30,
            "enabledKeys": "1,0",
            "setMusic": "no",
            "files": [
                {
                    "text": "לחישוב זכויות מדויק, אנא עדכן קודם את הפרטים האישיים שלך. לחץ 1 לעדכון פרטים או 0 לחזרה לתפריט הראשי.",
                    "activatedKeys": "1,0"
                }
            ]
        }
    
    def show_error_and_return_to_main(self) -> Dict:
        """הצגת שגיאה וחזרה לתפריט הראשי"""
        return {
            "type": "simpleMenu",
            "name": "systemError",
            "times": 1,
            "timeout": 10,
            "enabledKeys": "0",
            "setMusic": "no",
            "files": [
                {
                    "text": "אירעה שגיאה במערכת. לחץ 0 לחזרה לתפריט הראשי.",
                    "activatedKeys": "0"
                }
            ]
        }


# יצירת מופע של PBXHandler
pbx_handler = PBXHandler()


@app.route('/pbx', methods=['GET'])
def handle_pbx_request():
    """נקודת הכניסה הראשית לפניות מהמרכזיה"""
    try:
        # קבלת פרמטרים מהמרכזיה
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
        
        # הוספת כל הפרמטרים הנוספים שנאספו
        for key, value in request.args.items():
            if not key.startswith('PBX'):
                call_params[key] = value
        
        logger.info(f"קיבלנו פנייה: {call_params}")
        
        call_id = call_params.get('PBXcallId')
        phone_number = call_params.get('PBXphone')
        
        if not call_id or not phone_number:
            return jsonify({"error": "חסרים פרמטרים נדרשים"}), 400
        
        # שמירת נתוני השיחה
        pbx_handler.current_calls[call_id] = call_params
        pbx_handler.db.log_call(call_params)
        
        # בדיקה אם יש קלט מהמשתמש
        user_inputs = {}
        for key, value in call_params.items():
            if not key.startswith('PBX') and value:
                user_inputs[key] = value
        
        if user_inputs:
            # יש קלט מהמשתמש - צריך לטפל בו
            input_name = list(user_inputs.keys())[0]
            input_value = user_inputs[input_name]
            return jsonify(pbx_handler.handle_user_input(call_id, input_name, input_value))
        
        # אין קלט - זו פנייה ראשונית
        customer = pbx_handler.get_customer_by_phone(phone_number)
        
        if not customer:
            # לקוח לא קיים - העברה לשלוחת הרשמה
            return handle_new_customer()
        
        # בדיקת תוקף מנוי
        if not pbx_handler.is_subscription_active(customer):
            # מנוי לא בתוקף - העברה לשלוחת הצטרפות
            return handle_subscription_renewal()
        
        # לקוח עם מנוי בתוקף - הצגת תפריט ראשי
        return show_main_menu()
        
    except Exception as e:
        logger.error(f"שגיאה בטיפול בפנייה: {str(e)}")
        return jsonify({"error": "שגיאה בטיפול בבקשה"}), 500


def handle_new_customer():
    """טיפול בלקוח חדש"""
    return jsonify({
        "type": "simpleMenu",
        "name": "newCustomer",
        "times": 1,
        "timeout": 10,
        "enabledKeys": "1,2",
        "setMusic": "no",
        "extensionChange": "",
        "files": [
            {
                "text": "שלום וברוך הבא. נראה שאין לך עדיין מנוי במערכת שלנו. לחץ 1 להצטרפות למערכת, או לחץ 2 לחזרה לתפריט הקודם.",
                "activatedKeys": "1,2"
            }
        ]
    })


def handle_subscription_renewal():
    """טיפול בחידוש מנוי"""
    return jsonify({
        "type": "simpleMenu", 
        "name": "renewSubscription",
        "times": 1,
        "timeout": 10,
        "enabledKeys": "1,2",
        "setMusic": "no",
        "extensionChange": "",
        "files": [
            {
                "text": "המנוי שלך פג תוקף. לחץ 1 לחידוש המנוי, או לחץ 2 לחזרה לתפריט הקודם.",
                "activatedKeys": "1,2"
            }
        ]
    })


def show_main_menu():
    """תפריט ראשי ללקוחות עם מנוי בתוקף"""
    return jsonify({
        "type": "simpleMenu",
        "name": "mainMenu", 
        "times": 3,
        "timeout": 15,
        "enabledKeys": "1,2,3,4,5,6,7,8,9,0",
        "setMusic": "yes",
        "extensionChange": "",
        "files": [
            {
                "text": "שלום וברוך הבא למערכת השירותים שלנו. לחץ 1 להנפקת קבלה, לחץ 2 לביטול קבלה, לחץ 3 לעדכון פרטים אישיים, לחץ 4 לשמיעת זכויות מגיעות, לחץ 5 להשארת הודעה, לחץ 6 לבקשת דיווח שנתי, לחץ 0 לחזרה.",
                "activatedKeys": "1,2,3,4,5,6,0"
            }
        ]
    })


def handle_create_receipt():
    """התחלת תהליך הנפקת קבלה"""
    return {
        "type": "getDTMF",
        "name": "receiptAmount",
        "max": 6,
        "min": 1,
        "timeout": 30,
        "skipKey": "#",
        "skipValue": "SKIP",
        "confirmType": "number",
        "setMusic": "no",
        "files": [
            {
                "text": "אנא הכנס את סכום הקבלה בשקלים. לחץ # לדילוג.",
                "activatedKeys": "1,2,3,4,5,6,7,8,9,0,#"
            }
        ]
    }


def handle_cancel_receipt():
    """ביטול קבלה"""
    return {
        "type": "getDTMF",
        "name": "cancelReceiptId",
        "max": 10,
        "min": 1,
        "timeout": 30,
        "confirmType": "digits",
        "setMusic": "no",
        "files": [
            {
                "text": "אנא הכנס את מספר הקבלה לביטול.",
                "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
            }
        ]
    }


def handle_update_personal_details():
    """עדכון פרטים אישיים"""
    return {
        "type": "getDTMF", 
        "name": "numChildren",
        "max": 2,
        "min": 1,
        "timeout": 20,
        "confirmType": "number",
        "setMusic": "no",
        "files": [
            {
                "text": "אנא הכנס את מספר הילדים.",
                "activatedKeys": "1,2,3,4,5,6,7,8,9,0"
            }
        ]
    }


def handle_leave_message():
    """השארת הודעה"""
    return {
        "type": "record",
        "name": "customerMessage",
        "max": 180,  # 3 דקות
        "min": 3,
        "confirm": "confirmOnly",
        "fileName": f"message_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "files": [
            {
                "text": "אנא השאר את ההודעה שלך לאחר הצפצוף. לחץ # לסיום ההקלטה.",
                "activatedKeys": "NONE"
            }
        ]
    }


def handle_annual_report():
    """בקשת דיווח שנתי"""
    return {
        "type": "simpleMenu",
        "name": "annualReport",
        "times": 1,
        "timeout": 15,
        "enabledKeys": "1,0",
        "setMusic": "no",
        "files": [
            {
                "text": "הדיווח השנתי שלך יישלח אליך בהודעת SMS תוך 24 שעות. לחץ 1 לאישור או 0 לביטול.",
                "activatedKeys": "1,0"
            }
        ]
    }


def init_sample_data():
    """הוספת נתוני דוגמה למאגר"""
    conn = sqlite3.connect(pbx_handler.db.db_path)
    cursor = conn.cursor()
    
    try:
        # לקוח עם מנוי בתוקף
        cursor.execute('''
            INSERT OR REPLACE INTO customers 
            (phone_number, name, email, subscription_start_date, subscription_end_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            '0501234567',
            'יוסי כהן',
            'yossi@example.com',
            '2024-01-01',
            '2025-12-31',
            1
        ))
        
        # לקוח עם מנוי שפג
        cursor.execute('''
            INSERT OR REPLACE INTO customers
            (phone_number, name, email, subscription_start_date, subscription_end_date, is_active)  
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            '0507654321',
            'דני לוי',
            'danny@example.com',
            '2023-01-01',
            '2024-06-30',
            1
        ))
        
        conn.commit()
        logger.info("נתוני דוגמה נוספו בהצלחה")
    except Exception as e:
        logger.error(f"שגיאה בהוספת נתוני דוגמה: {str(e)}")
    finally:
        conn.close()


if __name__ == '__main__':
    # יצירת נתוני דוגמה
    init_sample_data()
    
    # הפעלת השרת
    app.run(host='0.0.0.0', port=5000, debug=True)
