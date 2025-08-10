#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from config import Config

logger = logging.getLogger(__name__)

class DatabaseHandler:
    """מחלקה לטיפול במאגר הנתונים"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.init_database()
    
    def get_connection(self):
        """יצירת חיבור למאגר נתונים"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """יצירת מבנה מאגר הנתונים"""
        conn = self.get_connection()
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # טבלת פרטים אישיים לזכויות
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customer_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER UNIQUE,
                num_children INTEGER DEFAULT 0,
                children_birth_years TEXT, -- JSON array של שנות לידה
                spouse1_workplaces INTEGER DEFAULT 0,
                spouse2_workplaces INTEGER DEFAULT 0,
                additional_info TEXT, -- JSON למידע נוסף
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
            )
        ''')
        
        # טבלת שיחות
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT UNIQUE NOT NULL,
                phone_number TEXT,
                customer_id INTEGER,
                pbx_num TEXT,
                pbx_did TEXT,
                call_type TEXT,
                call_status TEXT,
                extension_id TEXT,
                extension_path TEXT,
                call_data TEXT, -- JSON של כל הנתונים שנאספו
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                ended_at DATETIME,
                duration INTEGER, -- משך השיחה בשניות
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )
        ''')
        
        # טבלת קבלות
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                call_id TEXT,
                receipt_data TEXT NOT NULL, -- JSON של פרטי הקבלה
                icount_doc_id TEXT,
                icount_doc_num TEXT,
                icount_response TEXT, -- תגובה מלאה מ-iCount
                amount DECIMAL(10,2),
                description TEXT,
                status TEXT DEFAULT 'pending', -- pending, completed, cancelled, failed
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers (id),
                FOREIGN KEY (call_id) REFERENCES calls (call_id)
            )
        ''')
        
        # טבלת הודעות
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                call_id TEXT,
                message_file TEXT,
                message_text TEXT, -- תמלול אם קיים
                message_duration INTEGER, -- אורך ההקלטה בשניות
                status TEXT DEFAULT 'new', -- new, processed, archived
                priority TEXT DEFAULT 'normal', -- low, normal, high, urgent
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed_at DATETIME,
                FOREIGN KEY (customer_id) REFERENCES customers (id),
                FOREIGN KEY (call_id) REFERENCES calls (call_id)
            )
        ''')
        
        # טבלת דיווחים שנתיים
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS annual_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                report_year INTEGER NOT NULL,
                report_data TEXT, -- JSON של נתוני הדיווח
                report_file TEXT, -- נתיב לקובץ הדיווח
                status TEXT DEFAULT 'requested', -- requested, generated, sent, failed
                requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                generated_at DATETIME,
                sent_at DATETIME,
                UNIQUE(customer_id, report_year),
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )
        ''')
        
        # אינדקסים לביצועים טובים יותר
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers (phone_number)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_calls_call_id ON calls (call_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_calls_phone ON calls (phone_number)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_receipts_customer ON receipts (customer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_customer ON messages (customer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_reports_customer ON annual_reports (customer_id)')
        
        conn.commit()
        conn.close()
        logger.info("מאגר הנתונים אותחל בהצלחה")
    
    # פונקציות לקוחות
    def get_customer_by_phone(self, phone_number: str) -> Optional[Dict]:
        """קבלת פרטי לקוח לפי מספר טלפון"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM customers WHERE phone_number = ?', (phone_number,))
        customer = cursor.fetchone()
        conn.close()
        
        return dict(customer) if customer else None
    
    def get_customer_by_id(self, customer_id: int) -> Optional[Dict]:
        """קבלת פרטי לקוח לפי ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM customers WHERE id = ?', (customer_id,))
        customer = cursor.fetchone()
        conn.close()
        
        return dict(customer) if customer else None
    
    def create_customer(self, phone_number: str, name: str = None, email: str = None) -> int:
        """יצירת לקוח חדש"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # חישוב תאריכי מנוי (שנה מהיום)
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=365 * Config.DEFAULT_SUBSCRIPTION_MONTHS // 12)
        
        cursor.execute('''
            INSERT INTO customers (phone_number, name, email, subscription_start_date, subscription_end_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (phone_number, name, email, start_date, end_date))
        
        customer_id = cursor.lastrowid
        
        # יצירת רשומת פרטים אישיים ריקה
        cursor.execute('''
            INSERT INTO customer_details (customer_id) VALUES (?)
        ''', (customer_id,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"נוצר לקוח חדש: {phone_number} (ID: {customer_id})")
        return customer_id
    
    def update_customer(self, customer_id: int, **kwargs) -> bool:
        """עדכון פרטי לקוח"""
        if not kwargs:
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # בניית שאילתת עדכון דינמית
        set_clauses = []
        values = []
        
        for key, value in kwargs.items():
            if key in ['name', 'email', 'subscription_start_date', 'subscription_end_date', 'is_active']:
                set_clauses.append(f"{key} = ?")
                values.append(value)
        
        if not set_clauses:
            conn.close()
            return False
        
        set_clauses.append("updated_at = ?")
        values.append(datetime.now())
        values.append(customer_id)
        
        query = f"UPDATE customers SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(query, values)
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def is_subscription_active(self, customer: Dict) -> bool:
        """בדיקת תוקף מנוי"""
        if not customer or not customer.get('subscription_end_date'):
            return False
        
        end_date = datetime.strptime(customer['subscription_end_date'], '%Y-%m-%d').date()
        return end_date >= datetime.now().date()
    
    # פונקציות פרטים אישיים
    def get_customer_details(self, customer_id: int) -> Optional[Dict]:
        """קבלת פרטים אישיים של לקוח"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM customer_details WHERE customer_id = ?', (customer_id,))
        details = cursor.fetchone()
        conn.close()
        
        return dict(details) if details else None
    
    def update_customer_details(self, customer_id: int, **kwargs) -> bool:
        """עדכון פרטים אישיים"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # בדיקה אם קיימת רשומה
        cursor.execute('SELECT id FROM customer_details WHERE customer_id = ?', (customer_id,))
        exists = cursor.fetchone()
        
        if exists:
            # עדכון רשומה קיימת
            set_clauses = []
            values = []
            
            for key, value in kwargs.items():
                if key in ['num_children', 'children_birth_years', 'spouse1_workplaces', 
                          'spouse2_workplaces', 'additional_info']:
                    set_clauses.append(f"{key} = ?")
                    values.append(value)
            
            if set_clauses:
                set_clauses.append("updated_at = ?")
                values.append(datetime.now())
                values.append(customer_id)
                
                query = f"UPDATE customer_details SET {', '.join(set_clauses)} WHERE customer_id = ?"
                cursor.execute(query, values)
        else:
            # יצירת רשומה חדשה
            columns = ['customer_id']
            values = [customer_id]
            
            for key, value in kwargs.items():
                if key in ['num_children', 'children_birth_years', 'spouse1_workplaces', 
                          'spouse2_workplaces', 'additional_info']:
                    columns.append(key)
                    values.append(value)
            
            placeholders = ', '.join(['?'] * len(columns))
            query = f"INSERT INTO customer_details ({', '.join(columns)}) VALUES ({placeholders})"
            cursor.execute(query, values)
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    # פונקציות שיחות
    def log_call(self, call_params: Dict) -> int:
        """רישום שיחה במאגר נתונים"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # חיפוש לקוח לפי מספר טלפון
        customer_id = None
        if call_params.get('PBXphone'):
            customer = self.get_customer_by_phone(call_params['PBXphone'])
            if customer:
                customer_id = customer['id']
        
        cursor.execute('''
            INSERT OR REPLACE INTO calls 
            (call_id, phone_number, customer_id, pbx_num, pbx_did, call_type, 
             call_status, extension_id, extension_path, call_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            call_params.get('PBXcallId'),
            call_params.get('PBXphone'),
            customer_id,
            call_params.get('PBXnum'),
            call_params.get('PBXdid'),
            call_params.get('PBXcallType'),
            call_params.get('PBXcallStatus'),
            call_params.get('PBXextensionId'),
            call_params.get('PBXextensionPath'),
            json.dumps(call_params, ensure_ascii=False)
        ))
        
        call_row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return call_row_id
    
    def update_call_data(self, call_id: str, new_data: Dict) -> bool:
        """עדכון נתוני שיחה"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # קבלת הנתונים הקיימים
        cursor.execute('SELECT call_data FROM calls WHERE call_id = ?', (call_id,))
        result = cursor.fetchone()
        
        if result:
            existing_data = json.loads(result['call_data'] or '{}')
            existing_data.update(new_data)
            
            cursor.execute('''
                UPDATE calls SET call_data = ? WHERE call_id = ? 
                WHERE call_id = ?
            ''', (json.dumps(existing_data, ensure_ascii=False), call_id))
            
            success = cursor.rowcount > 0
        else:
            success = False
        
        conn.commit()
        conn.close()
        
        return success
    
    # פונקציות קבלות
    def create_receipt(self, customer_id: int, call_id: str, receipt_data: Dict) -> int:
        """יצירת רשומת קבלה"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO receipts 
            (customer_id, call_id, receipt_data, amount, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            customer_id,
            call_id,
            json.dumps(receipt_data, ensure_ascii=False),
            receipt_data.get('amount', 0),
            receipt_data.get('description', '')
        ))
        
        receipt_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return receipt_id
    
    def update_receipt(self, receipt_id: int, **kwargs) -> bool:
        """עדכון פרטי קבלה"""
        if not kwargs:
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        set_clauses = []
        values = []
        
        for key, value in kwargs.items():
            if key in ['icount_doc_id', 'icount_doc_num', 'icount_response', 
                      'amount', 'description', 'status']:
                set_clauses.append(f"{key} = ?")
                values.append(value)
        
        if set_clauses:
            set_clauses.append("updated_at = ?")
            values.append(datetime.now())
            values.append(receipt_id)
            
            query = f"UPDATE receipts SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(query, values)
            
            success = cursor.rowcount > 0
        else:
            success = False
        
        conn.commit()
        conn.close()
        
        return success
    
    # פונקציות הודעות
    def save_message(self, customer_id: int, call_id: str, message_file: str = None, 
                    message_text: str = None, duration: int = None) -> int:
        """שמירת הודעה"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO messages 
            (customer_id, call_id, message_file, message_text, message_duration)
            VALUES (?, ?, ?, ?, ?)
        ''', (customer_id, call_id, message_file, message_text, duration))
        
        message_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"נשמרה הודעה חדשה: ID {message_id}")
        return message_id
    
    # פונקציות דיווחים
    def request_annual_report(self, customer_id: int, report_year: int = None) -> int:
        """בקשת דיווח שנתי"""
        if not report_year:
            report_year = datetime.now().year - 1  # שנה קודמת כברירת מחדל
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO annual_reports 
            (customer_id, report_year, status, requested_at)
            VALUES (?, ?, 'requested', ?)
        ''', (customer_id, report_year, datetime.now()))
        
        report_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"נתבקש דיווח שנתי: לקוח {customer_id}, שנה {report_year}")
        return report_id
    
    def close(self):
        """סגירת חיבור (אם נדרש)"""
        pass
