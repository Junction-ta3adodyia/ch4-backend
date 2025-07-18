"""
Enhanced Alert Service with Email Notifications
"""

from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio
from jinja2 import Template

from app.models.alert import Alert, AlertStatus, AlertSeverity
from app.models.pond import Pond, User
from app.config import settings


class EmailService:
    """Email notification service for alerts"""
    
    def __init__(self):
        self.smtp_server = settings.SMTP_SERVER
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.FROM_EMAIL
        self.enabled = settings.ENABLE_EMAIL_ALERTS
        
        # Check credentials but don't fail initialization
        if not self.smtp_username or not self.smtp_password:
            print("⚠️  Warning: SMTP credentials not configured. Email alerts will be disabled.")
            self.enabled = False
        
    async def send_anomaly_alert_email(self, alert: Alert, pond: Pond, user: User) -> bool:
        """Send anomaly alert email to pond owner"""
        if not self.enabled:
            print("📧 Email alerts are disabled in configuration")
            return False
            
        if not self.smtp_username or not self.smtp_password:
            print("❌ Email credentials not configured")
            return False
            
        try:
            # Determine user's preferred language
            user_language = getattr(user, 'language', 'fr')
            
            # Get alert message in user's language
            if user_language == 'ar':
                alert_message = getattr(alert, 'message_ar', alert.message_fr)
                subject = f"تنبيه شذوذ - حوض {pond.name}"
            else:  # Default to French
                alert_message = alert.message_fr
                subject = f"Alerte Anomalie - Bassin {pond.name}"
            
            # Create email content
            email_content = self._create_email_content(alert, pond, user, user_language)
            
            # Send email
            return await self._send_email(
                to_email=user.email,
                subject=subject,
                content=email_content
            )
            
        except Exception as e:
            print(f"❌ Error sending anomaly alert email: {e}")
            return False
    
    def _create_email_content(self, alert: Alert, pond: Pond, user: User, language: str) -> str:
        """Create HTML email content"""
        
        # Simple email template
        template_content = """
        <html>
        <head>
            <style>
                .container { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; }
                .header { background-color: #ff6b6b; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; }
                .alert-box { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; margin: 10px 0; border-radius: 5px; }
                .critical { background-color: #f8d7da; border-color: #f5c6cb; }
                .parameter { margin: 5px 0; padding: 8px; background-color: #f8f9fa; border-radius: 3px; }
                .footer { background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🚨 Alerte Anomalie Détectée</h2>
                </div>
                <div class="content">
                    <p>Bonjour {{ user_name }},</p>
                    <p>Une anomalie a été détectée dans votre bassin <strong>{{ pond_name }}</strong>.</p>
                    
                    <div class="alert-box {{ severity_class }}">
                        <h3>Détails de l'Anomalie</h3>
                        <p><strong>Message:</strong> {{ alert_message }}</p>
                        <p><strong>Sévérité:</strong> {{ severity }}</p>
                        <p><strong>Heure:</strong> {{ timestamp }}</p>
                        <p><strong>Score:</strong> {{ anomaly_score }}/1.0</p>
                    </div>
                    
                    <p><strong>Action recommandée:</strong> Vérifiez immédiatement les conditions de votre bassin.</p>
                    
                    <p>Cordialement,<br>Système de Surveillance Aquaculture</p>
                </div>
                <div class="footer">
                    <p>Email automatique - Ne pas répondre</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Template variables
        template_vars = {
            'user_name': f"{user.first_name} {user.last_name}",
            'pond_name': pond.name,
            'alert_message': alert.message_fr,
            'severity': self._get_severity_text(alert.severity, language),
            'severity_class': alert.severity.value.lower(),
            'timestamp': alert.triggered_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'anomaly_score': alert.context_data.get('anomaly_score', 0) if alert.current_value else 0
        }
        
        # Render template
        template = Template(template_content)
        return template.render(**template_vars)
    
    def _get_severity_text(self, severity: AlertSeverity, language: str) -> str:
        """Get severity text in specified language"""
        severity_texts = {
            AlertSeverity.INFO: 'Information',
            AlertSeverity.WARNING: 'Avertissement',
            AlertSeverity.CRITICAL: 'Critique'
        }
        return severity_texts.get(severity, str(severity.value))
    
    async def _send_email(self, to_email: str, subject: str, content: str) -> bool:
        """Send email using SMTP"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # Add HTML content
            html_part = MIMEText(content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            print(f"✅ Anomaly alert email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send email to {to_email}: {e}")
            return False


# Global email service instance
email_service = EmailService()


async def send_anomaly_alert_notification(alert: Alert, db: Session) -> bool:
    """Send anomaly alert notification via email"""
    try:
        # Get pond and user information
        pond = db.query(Pond).filter(Pond.id == alert.pond_id).first()
        if not pond:
            print(f"Pond not found for alert {alert.id}")
            return False
        
        user = db.query(User).filter(User.id == pond.owner_id).first()
        if not user:
            print(f"User not found for pond {pond.id}")
            return False
        
        # Check if user wants email notifications
        if not getattr(user, 'email_notifications', True):
            print(f"Email notifications disabled for user {user.id}")
            return False
        
        # Send email
        return await email_service.send_anomaly_alert_email(alert, pond, user)
        
    except Exception as e:
        print(f"Error sending anomaly alert notification: {e}")
        return False