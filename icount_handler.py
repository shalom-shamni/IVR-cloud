#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from config import Config

logger = logging.getLogger(__name__)

class ICountHandler:
    """מחלקה לטיפול ב-API של iCount"""
    
    def __init__(self):
        self.api_url = Config.ICOUNT_API_URL
        self.cid = Config.ICOUNT_CID
        self.user = Config.ICOUNT_USER  
        self.password = Config.ICOUNT_PASS
        self.session_id = None
        
    def authenticate(self) -> bool:
        """התחברות למערכת iCount"""
        try:
            auth_url = f"{self.api_url}/api/login"
            auth_data = {
                'cid': self.cid,
                'user': self.user,
                'pass': self.password
            }
            
            response = requests.post(auth_url, data=auth_data)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status'):
                    self.session_id = result.get('session_id')
                    logger.info("התחברות ל-iCount הצליחה")
                    return True
                else:
                    logger.error(f"כישלון בהתחברות: {result.get('message')}")
                    return False
            else:
                logger.error(f"שגיאת HTTP בהתחברות: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"שגיאה בהתחברות ל-iCount: {str(e)}")
            return False
    
    def create_receipt(self, receipt_data: Dict[str, Any]) -> Dict[str, Any]:
        """יצירת קבלה חדשה במערכת iCount"""
        
        if not self.session_id and not self.authenticate():
            return {"status": False, "message": "כישלון בהתחברות למערכת"}
        
        try:
            receipt_url = f"{self.api_url}/api/doc/create"
            
            # הכנת נתוני הקבלה לפורמט iCount
            icount_data = {
                'sid': self.session_id,
                'doctype': 'receipt',  # סוג מסמך - קבלה
                'lang': 'he',
                'currency': 'ILS',
                'watax': 1,  # מע"ם
                'date': datetime.now().strftime('%d/%m/%Y'),
                'description': receipt_data.get('description', 'קבלה'),
                'sum': receipt_data.get('amount', 0),
                'client': {
                    'name': receipt_data.get('client_name', ''),
                    'phone': receipt_data.get('client_phone', ''),
                    'email': receipt_data.get('client_email', '')
                }
            }
            
            response = requests.post(receipt_url, json=icount_data)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status'):
                    logger.info(f"קבלה נוצרה בהצלחה: {result.get('doc_id')}")
                    return {
                        "status": True,
                        "doc_id": result.get('doc_id'),
                        "doc_num": result.get('doc_num'),
                        "message": "הקבלה נוצרה בהצלחה"
                    }
                else:
                    logger.error(f"כישלון ביצירת קבלה: {result.get('message')}")
                    return {
                        "status": False,
                        "message": result.get('message', 'שגיאה לא ידועה')
                    }
            else:
                logger.error(f"שגיאת HTTP ביצירת קבלה: {response.status_code}")
                return {
                    "status": False,
                    "message": f"שגיאת שרת: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"שגיאה ביצירת קבלה: {str(e)}")
            return {
                "status": False,
                "message": f"שגיאה טכנית: {str(e)}"
            }
    
    def cancel_receipt(self, doc_id: str) -> Dict[str, Any]:
        """ביטול קבלה במערכת iCount"""
        
        if not self.session_id and not self.authenticate():
            return {"status": False, "message": "כישלון בהתחברות למערכת"}
        
        try:
            cancel_url = f"{self.api_url}/api/doc/cancel"
            cancel_data = {
                'sid': self.session_id,
                'doc_id': doc_id
            }
            
            response = requests.post(cancel_url, data=cancel_data)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status'):
                    logger.info(f"קבלה בוטלה בהצלחה: {doc_id}")
                    return {
                        "status": True,
                        "message": "הקבלה בוטלה בהצלחה"
                    }
                else:
                    logger.error(f"כישלון בביטול קבלה: {result.get('message')}")
                    return {
                        "status": False,
                        "message": result.get('message', 'שגיאה לא ידועה')
                    }
            else:
                logger.error(f"שגיאת HTTP בביטול קבלה: {response.status_code}")
                return {
                    "status": False,
                    "message": f"שגיאת שרת: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"שגיאה בביטול קבלה: {str(e)}")
            return {
                "status": False,
                "message": f"שגיאה טכנית: {str(e)}"
            }
    
    def get_receipt_details(self, doc_id: str) -> Dict[str, Any]:
        """קבלת פרטי קבלה מהמערכת"""
        
        if not self.session_id and not self.authenticate():
            return {"status": False, "message": "כישלון בהתחברות למערכת"}
        
        try:
            details_url = f"{self.api_url}/api/doc/get"
            details_data = {
                'sid': self.session_id,
                'doc_id': doc_id
            }
            
            response = requests.post(details_url, data=details_data)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status'):
                    return {
                        "status": True,
                        "data": result.get('data', {})
                    }
                else:
                    return {
                        "status": False,
                        "message": result.get('message', 'קבלה לא נמצאה')
                    }
            else:
                return {
                    "status": False,
                    "message": f"שגיאת שרת: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"שגיאה בקבלת פרטי קבלה: {str(e)}")
            return {
                "status": False,
                "message": f"שגיאה טכנית: {str(e)}"
            }
    
    def logout(self):
        """התנתקות מהמערכת"""
        if self.session_id:
            try:
                logout_url = f"{self.api_url}/api/logout"
                logout_data = {'sid': self.session_id}
                requests.post(logout_url, data=logout_data)
                self.session_id = None
                logger.info("התנתקות מ-iCount הושלמה")
            except Exception as e:
                logger.error(f"שגיאה בהתנתקות: {str(e)}")

class BenefitsCalculator:
    """מחלקה לחישוב זכויות"""
    
    @staticmethod
    def calculate_work_benefit(workplaces_spouse1: int, workplaces_spouse2: int) -> float:
        """חישוב מענק עבודה לפי מקומות עבודה"""
        total_workplaces = workplaces_spouse1 + workplaces_spouse2
        base_amount = Config.WORK_BENEFIT_BASE
        
        # חישוב לפי מספר מקומות עבודה
        if total_workplaces >= 2:
            return base_amount * 1.5  # בונוס ל-2+ מקומות עבודה
        elif total_workplaces == 1:
            return base_amount
        else:
            return 0
    
    @staticmethod
    def calculate_birth_benefits(children_birth_years: list) -> float:
        """חישוב דמי לידה לפי גילאי ילדים"""
        if not children_birth_years:
            return 0
        
        current_year = datetime.now().year
        total_benefit = 0
        
        for birth_year in children_birth_years:
            try:
                child_age = current_year - int(birth_year)
                # דמי לידה מגיעים עד גיל 18
                if child_age <= 18:
                    total_benefit += Config.BIRTH_BENEFIT_PER_CHILD
            except (ValueError, TypeError):
                continue
        
        return total_benefit
    
    @staticmethod
    def calculate_total_benefits(customer_details: Dict) -> Dict[str, float]:
        """חישוב כל הזכויות"""
        work_benefit = BenefitsCalculator.calculate_work_benefit(
            customer_details.get('spouse1_workplaces', 0),
            customer_details.get('spouse2_workplaces', 0)
        )
        
        children_years = []
        if customer_details.get('children_birth_years'):
            try:
                children_years = json.loads(customer_details['children_birth_years'])
            except:
                children_years = []
        
        birth_benefit = BenefitsCalculator.calculate_birth_benefits(children_years)
        
        return {
            'work_benefit': work_benefit,
            'birth_benefit': birth_benefit,
            'total_benefit': work_benefit + birth_benefit
        }