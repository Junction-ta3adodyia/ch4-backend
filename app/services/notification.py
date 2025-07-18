"""
Notification Service
Handles sending notifications via email, SMS, and push notifications
"""

import asyncio
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional, Dict, Any
from datetime import datetime
import json

from twilio.rest import Client as TwilioClient
from pyfcm import FCMNotification

from app.config import settings
from app.models.alert import Alert, NotificationLog
from app.models.pond import User
from app.database import SessionLocal


class NotificationService:
    """
    Service for sending notifications through various channels
    """
    
    def __init__(self):
        self.twilio_client = None
        self.fcm_service = None
        
        # Initialize Twilio if configured
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            self.twilio_client = TwilioClient(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN
            )
        
        # Initialize Firebase if configured
        if settings.FIREBASE_SERVER_KEY:
            self.fcm_service = FCMNotification(api_key=settings.FIREBASE_SERVER_KEY)
    
    async def send_email_alert_to_observers(self, alert: Alert, observers: List[User], admins: List[User]) -> bool:
        """
        Send email alert notification to a list of observers and CC admins.
        """
        if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
            return False

        observer_emails = [u.email for u in observers if u.email and u.email_notifications]
        if not observer_emails:
            return False

        admin_emails_cc = [a.email for a in admins if a.email]

        # Use the language of the first observer for the message
        message_text = self._get_localized_message(alert, observers[0].language)

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🚨 Aquaculture Alert - {alert.title}"
            msg['From'] = settings.SMTP_USERNAME
            msg['To'] = ", ".join(observer_emails)
            if admin_emails_cc:
                msg['Cc'] = ", ".join(admin_emails_cc)

            html_content = self._create_email_html(alert, observers[0], message_text)
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)

            async with aiosmtplib.SMTP(
                hostname=settings.SMTP_SERVER, port=settings.SMTP_PORT, start_tls=True
            ) as smtp:
                await smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                await smtp.send_message(msg)

            # Log notification for each recipient
            all_recipients = observers + admins
            for user in all_recipients:
                if user.email:
                    await self._log_notification(alert.id, user.id, 'email', user.email, message_text, 'sent')
            
            return True
        except Exception as e:
            print(f"Failed to send observer email alert: {e}")
            # Log failure for each recipient
            all_recipients = observers + admins
            for user in all_recipients:
                if user.email:
                    await self._log_notification(alert.id, user.id, 'email', user.email, message_text, 'failed', str(e))
            return False
    
    async def send_sms_alert(self, alert: Alert, user: User) -> bool:
        """
        Send SMS alert notification
        """
        if not self.twilio_client or not user.phone_number:
            return False
        
        try:
            # Get localized message
            message_text = self._get_localized_message(alert, user.language)
            
            # Keep SMS short
            sms_message = f"{alert.title}\n{message_text[:100]}..."
            
            # Send SMS
            message = self.twilio_client.messages.create(
                body=sms_message,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=user.phone_number
            )
            
            # Log notification
            await self._log_notification(
                alert.id, user.id, 'sms', user.phone_number, 
                sms_message, 'sent', provider_response={'sid': message.sid}
            )
            
            return True
            
        except Exception as e:
            await self._log_notification(
                alert.id, user.id, 'sms', user.phone_number, 
                message_text, 'failed', str(e)
            )
            print(f"Failed to send SMS: {e}")
            return False
    
    async def send_push_alert(self, alert: Alert, user: User) -> bool:
        """
        Send push notification alert
        """
        if not self.fcm_service:
            return False
        
        try:
            # Get localized message
            message_text = self._get_localized_message(alert, user.language)
            
            # Get user's device tokens (would be stored in user profile)
            device_tokens = self._get_user_device_tokens(user.id)
            
            if not device_tokens:
                return False
            
            # Create notification data
            notification_data = {
                'title': alert.title,
                'body': message_text[:100],
                'icon': 'alert_icon',
                'click_action': f'/pond/{alert.pond_id}/alerts',
                'sound': 'default' if alert.severity.value == 'critical' else 'notification'
            }
            
            # Additional data payload
            data_payload = {
                'alert_id': str(alert.id),
                'pond_id': str(alert.pond_id),
                'severity': alert.severity.value,
                'parameter': alert.parameter,
                'value': str(alert.current_value)
            }
            
            # Send to all user devices
            results = []
            for token in device_tokens:
                try:
                    result = self.fcm_service.notify_single_device(
                        registration_id=token,
                        message_title=notification_data['title'],
                        message_body=notification_data['body'],
                        data_message=data_payload,
                        sound=notification_data['sound']
                    )
                    results.append(result)
                except Exception as e:
                    print(f"Failed to send to device {token}: {e}")
            
            # Log notification
            await self._log_notification(
                alert.id, user.id, 'push', f"{len(device_tokens)} devices", 
                message_text, 'sent', provider_response={'results': results}
            )
            
            return True
            
        except Exception as e:
            await self._log_notification(
                alert.id, user.id, 'push', 'unknown', 
                message_text, 'failed', str(e)
            )
            print(f"Failed to send push notification: {e}")
            return False
    
    async def send_daily_summary(self, user: User, summary_data: Dict[str, Any]) -> bool:
        """
        Send daily summary email
        """
        try:
            # Create summary email content
            html_content = self._create_daily_summary_html(user, summary_data)
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"📊 Daily Aquaculture Summary - {datetime.now().strftime('%Y-%m-%d')}"
            msg['From'] = settings.SMTP_USERNAME
            msg['To'] = user.email
            
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Send email
            async with aiosmtplib.SMTP(
                hostname=settings.SMTP_SERVER,
                port=settings.SMTP_PORT,
                start_tls=True
            ) as smtp:
                await smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                await smtp.send_message(msg)
            
            return True
            
        except Exception as e:
            print(f"Failed to send daily summary: {e}")
            return False
    
    def _get_localized_message(self, alert: Alert, language: str) -> str:
        """
        Get localized alert message based on user language
        """
        if language == 'fr' and alert.message_fr:
            return alert.message_fr
        elif language == 'ar' and alert.message_ar:
            return alert.message_ar
        else:
            return alert.message
    
    def _create_email_html(self, alert: Alert, user: User, message: str) -> str:
        """
        Create HTML email content for alerts
        """
        severity_colors = {
            'critical': '#dc3545',
            'warning': '#ffc107',
            'info': '#17a2b8'
        }
        
        color = severity_colors.get(alert.severity.value, '#6c757d')
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Aquaculture Alert</title>
        </head>
        <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f8f9fa;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                
                <!-- Header -->
                <div style="background-color: {color}; color: white; padding: 20px; text-align: center;">
                    <h1 style="margin: 0; font-size: 24px;">🚨 Alert Aquaculture</h1>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">Système de surveillance des bassins</p>
                </div>
                
                <!-- Content -->
                <div style="padding: 30px;">
                    <h2 style="color: {color}; margin-top: 0; font-size: 20px;">{alert.title}</h2>
                    
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 6px; margin: 20px 0;">
                        <p style="margin: 0; font-size: 16px; line-height: 1.5;">{message}</p>
                    </div>
                    
                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6; font-weight: bold; width: 40%;">Paramètre:</td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">{alert.parameter}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6; font-weight: bold;">Valeur actuelle:</td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6; color: {color}; font-weight: bold;">{alert.current_value}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6; font-weight: bold;">Seuil:</td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">{alert.threshold_value}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6; font-weight: bold;">Gravité:</td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">{alert.severity.value.title()}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; font-weight: bold;">Date/Heure:</td>
                            <td style="padding: 10px;">{alert.triggered_at.strftime('%d/%m/%Y %H:%M')}</td>
                        </tr>
                    </table>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="#" style="background-color: {color}; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">Voir le tableau de bord</a>
                    </div>
                </div>
                
                <!-- Footer -->
                <div style="background-color: #f8f9fa; padding: 20px; text-align: center; border-top: 1px solid #dee2e6;">
                    <p style="margin: 0; color: #6c757d; font-size: 14px;">
                        Système de gestion aquacole - Algérie<br>
                        Cette alerte a été générée automatiquement
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _create_daily_summary_html(self, user: User, summary_data: Dict[str, Any]) -> str:
        """
        Create HTML email content for daily summary
        """
        # This would create a comprehensive daily summary email
        # Including pond health scores, recent alerts, trends, etc.
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Daily Aquaculture Summary</title>
        </head>
        <body style="font-family: Arial, sans-serif;">
            <h1>Daily Summary for {user.first_name or user.username}</h1>
            <!-- Summary content would go here -->
        </body>
        </html>
        """
        return html
    
    def _get_user_device_tokens(self, user_id: int) -> list:
        """
        Get user's device tokens for push notifications
        This would query a user_devices table
        """
        # Placeholder - in real implementation, this would query device tokens
        return []
    
    async def _log_notification(
        self,
        alert_id: Optional[int],
        user_id: int,
        notification_type: str,
        recipient: str,
        message: str,
        status: str,
        error_message: Optional[str] = None,
        provider_response: Optional[Dict[str, Any]] = None
    ):
        """
        Log notification attempt to database
        """
        db = SessionLocal()
        try:
            log_entry = NotificationLog(
                alert_id=alert_id,
                user_id=user_id,
                notification_type=notification_type,
                recipient=recipient,
                message=message,
                status=status,
                error_message=error_message,
                provider_response=provider_response,
                sent_at=datetime.utcnow() if status == 'sent' else None
            )
            
            db.add(log_entry)
            db.commit()
            
        except Exception as e:
            print(f"Failed to log notification: {e}")
            db.rollback()
        finally:
            db.close()