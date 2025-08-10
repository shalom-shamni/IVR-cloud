#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from dotenv import load_dotenv

# טעינת משתני סביבה
load_dotenv()

class Config:
    """הגדרות כלליות של המערכת"""
    
    # הגדרות שרת
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    
    # הגדרות מאגר נתונים
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'pbx_system.db')
    
    # הגדרות iCount API
    ICOUNT_API_URL = os.getenv('ICOUNT_API_URL', 'https://api.icount.co.il')
    ICOUNT_CID = os.getenv('ICOUNT_CID', '')
    ICOUNT_USER = os.getenv('ICOUNT_USER', '')
    ICOUNT_PASS = os.getenv('ICOUNT_PASS', '')
    
    # הגדרות SMS (אם נדרש)
    SMS_API_KEY = os.getenv('SMS_API_KEY', '')
    SMS_SENDER = os.getenv('SMS_SENDER', 'MySystem')
    
    # הגדרות זכויות (לחישובים)
    WORK_BENEFIT_BASE = 2000  # מענק עבודה בסיסי
    BIRTH_BENEFIT_PER_CHILD = 1500  # דמי לידה לילד
    
    # הגדרות הקלטות
    RECORDINGS_PATH = os.getenv('RECORDINGS_PATH', './recordings')
    MAX_RECORDING_MINUTES = 3
    
    # הגדרות תוקף מנוי  
    DEFAULT_SUBSCRIPTION_MONTHS = 12
    
    # הגדרות לוגים
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'pbx_system.log')

class DevelopmentConfig(Config):
    """הגדרות לסביבת פיתוח"""
    DEBUG = True
    DATABASE_PATH = 'dev_pbx_system.db'

class ProductionConfig(Config):
    """הגדרות לסביבת ייצור"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'

# בחירת הגדרה לפי סביבה
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
