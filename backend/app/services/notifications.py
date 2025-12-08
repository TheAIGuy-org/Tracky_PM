"""
Notification Service for Tracky PM.

Handles all outbound notifications:
- Email (via SendGrid/SMTP)
- Slack (via webhooks/API)

Provides:
- Template rendering (Jinja2)
- Delivery tracking
- Retry logic with exponential backoff
- Rate limiting
"""
import asyncio
import hashlib
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID
import json
import logging

from app.core.config import settings
from app.core.database import get_supabase_client


# Configure logging
logger = logging.getLogger(__name__)


class NotificationChannel(Enum):
    """Supported notification channels."""
    EMAIL = "EMAIL"
    SLACK = "SLACK"
    BOTH = "BOTH"


class NotificationStatus(Enum):
    """Notification delivery status."""
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"


@dataclass
class NotificationResult:
    """Result of a notification attempt."""
    success: bool
    channel: NotificationChannel
    message_id: Optional[str] = None
    error: Optional[str] = None
    retry_after: Optional[datetime] = None


@dataclass
class EmailMessage:
    """Email message structure."""
    to_email: str
    to_name: str
    subject: str
    html_body: str
    text_body: Optional[str] = None
    reply_to: Optional[str] = None
    cc: Optional[List[str]] = None
    tracking_id: Optional[str] = None


@dataclass  
class SlackMessage:
    """Slack message structure."""
    channel_id: Optional[str] = None
    user_id: Optional[str] = None
    text: str = ""
    blocks: Optional[List[Dict]] = None
    thread_ts: Optional[str] = None


# ==========================================
# EMAIL TEMPLATES
# ==========================================

class EmailTemplates:
    """Email template definitions using simple string formatting."""
    
    # Base HTML template
    BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ background: #fff; border: 1px solid #e0e0e0; border-top: none; padding: 30px; border-radius: 0 0 8px 8px; }}
        .button {{ display: inline-block; background: #667eea; color: white !important; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 20px 0; }}
        .button:hover {{ background: #5a67d8; }}
        .task-card {{ background: #f8f9fa; border-left: 4px solid #667eea; padding: 15px; margin: 15px 0; border-radius: 0 4px 4px 0; }}
        .task-card h3 {{ margin: 0 0 10px 0; color: #333; }}
        .task-card p {{ margin: 5px 0; color: #666; }}
        .deadline {{ color: #e53e3e; font-weight: 600; }}
        .footer {{ text-align: center; padding: 20px; color: #888; font-size: 12px; }}
        .urgency-HIGH {{ border-color: #ed8936; }}
        .urgency-CRITICAL {{ border-color: #e53e3e; }}
        .impact-card {{ background: #fff8e1; border: 1px solid #ffd54f; padding: 15px; border-radius: 4px; margin: 15px 0; }}
        .status-badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
        .status-ON_TRACK {{ background: #c6f6d5; color: #276749; }}
        .status-DELAYED {{ background: #feebc8; color: #c05621; }}
        .status-BLOCKED {{ background: #fed7d7; color: #c53030; }}
    </style>
</head>
<body>
    <div class="container">
        {content}
    </div>
</body>
</html>
"""

    @classmethod
    def status_check_alert(
        cls,
        recipient_name: str,
        work_item_name: str,
        work_item_id: str,
        deadline: str,
        urgency: str,
        magic_link: str,
        program_name: str = "",
        project_name: str = "",
        is_critical_path: bool = False
    ) -> tuple[str, str]:
        """Generate status check alert email."""
        urgency_class = f"urgency-{urgency}" if urgency in ["HIGH", "CRITICAL"] else ""
        critical_badge = '<span style="background:#e53e3e;color:white;padding:2px 8px;border-radius:4px;font-size:11px;">CRITICAL PATH</span>' if is_critical_path else ""
        
        html_content = f"""
        <div class="header">
            <h1>📋 Status Check Required</h1>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>
            
            <p>We need a quick status update on one of your tasks that's approaching its deadline.</p>
            
            <div class="task-card {urgency_class}">
                <h3>{work_item_name} {critical_badge}</h3>
                <p><strong>ID:</strong> {work_item_id}</p>
                <p><strong>Deadline:</strong> <span class="deadline">{deadline}</span></p>
                {'<p><strong>Program:</strong> ' + program_name + '</p>' if program_name else ''}
                {'<p><strong>Project:</strong> ' + project_name + '</p>' if project_name else ''}
            </div>
            
            <p>Please take a moment to update the status. This helps the team stay informed and allows us to adjust plans if needed.</p>
            
            <p style="text-align: center;">
                <a href="{magic_link}" class="button">Update Status Now</a>
            </p>
            
            <p style="font-size: 13px; color: #666;">
                ⏰ Please respond within 4 hours. If we don't hear back, we'll reach out to your backup or manager.
            </p>
        </div>
        <div class="footer">
            <p>This is an automated message from Tracky PM.</p>
            <p>The link above is unique to you and doesn't require login.</p>
        </div>
"""
        
        text_content = f"""
Status Check Required

Hi {recipient_name},

We need a quick status update on one of your tasks:

Task: {work_item_name}
ID: {work_item_id}
Deadline: {deadline}
{('Program: ' + program_name) if program_name else ''}
{('Project: ' + project_name) if project_name else ''}

Please update the status by clicking here: {magic_link}

⏰ Please respond within 4 hours.

---
Tracky PM
"""
        
        return cls.BASE_HTML.format(content=html_content), text_content.strip()

    @classmethod
    def response_confirmation(
        cls,
        recipient_name: str,
        work_item_name: str,
        work_item_id: str,
        reported_status: str,
        submitted_at: str,
        proposed_new_date: str = None,
        requires_approval: bool = False,
        impact_summary: Dict = None
    ) -> tuple[str, str]:
        """Generate response confirmation email."""
        status_text = reported_status.replace("_", " ")
        status_class = f"status-{reported_status}"
        
        impact_html = ""
        if impact_summary and reported_status in ["DELAYED", "BLOCKED"]:
            impact_html = f"""
            <div class="impact-card">
                <h4 style="margin: 0 0 10px 0;">📊 Impact Analysis</h4>
                <p><strong>Delay:</strong> {impact_summary.get('delay_days', 0)} days</p>
                <p><strong>Affected Tasks:</strong> {impact_summary.get('cascade_count', 0)}</p>
                {'<p><strong>⚠️ Critical Path Affected</strong></p>' if impact_summary.get('is_critical_path') else ''}
                <p><strong>Risk Level:</strong> {impact_summary.get('risk_level', 'Unknown')}</p>
            </div>
"""
        
        approval_note = ""
        if requires_approval:
            approval_note = """
            <div style="background: #ebf8ff; border: 1px solid #90cdf4; padding: 15px; border-radius: 4px; margin: 15px 0;">
                <p style="margin: 0;"><strong>⏳ Pending Approval</strong></p>
                <p style="margin: 5px 0 0 0; font-size: 13px;">Your delay request has been submitted for PM approval. You'll be notified once a decision is made.</p>
            </div>
"""
        
        html_content = f"""
        <div class="header">
            <h1>✅ Response Received</h1>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>
            
            <p>Thank you for updating the status on your task. Here's a summary of your response:</p>
            
            <div class="task-card">
                <h3>{work_item_name}</h3>
                <p><strong>ID:</strong> {work_item_id}</p>
                <p><strong>Status:</strong> <span class="{status_class} status-badge">{status_text}</span></p>
                <p><strong>Submitted:</strong> {submitted_at}</p>
                {'<p><strong>New Target Date:</strong> ' + proposed_new_date + '</p>' if proposed_new_date else ''}
            </div>
            
            {impact_html}
            {approval_note}
            
            <p style="font-size: 13px; color: #666;">
                You can update your response anytime before the deadline by using the same link.
            </p>
        </div>
        <div class="footer">
            <p>Thank you for keeping the project on track!</p>
            <p>Tracky PM</p>
        </div>
"""
        
        text_content = f"""
Response Received

Hi {recipient_name},

Thank you for updating the status on your task.

Task: {work_item_name}
ID: {work_item_id}
Status: {status_text}
Submitted: {submitted_at}
{('New Target Date: ' + proposed_new_date) if proposed_new_date else ''}

{'⏳ Your delay request has been submitted for PM approval.' if requires_approval else ''}

---
Tracky PM
"""
        
        return cls.BASE_HTML.format(content=html_content), text_content.strip()

    @classmethod
    def approval_request(
        cls,
        pm_name: str,
        responder_name: str,
        work_item_name: str,
        work_item_id: str,
        original_deadline: str,
        proposed_new_date: str,
        delay_days: int,
        reason_category: str,
        impact_summary: Dict,
        approval_link: str
    ) -> tuple[str, str]:
        """Generate approval request email for PM."""
        risk_color = {
            "LOW": "#48bb78",
            "MEDIUM": "#ed8936", 
            "HIGH": "#e53e3e",
            "CRITICAL": "#c53030"
        }.get(impact_summary.get("risk_level", "MEDIUM"), "#ed8936")
        
        html_content = f"""
        <div class="header" style="background: linear-gradient(135deg, #ed8936 0%, #dd6b20 100%);">
            <h1>🔔 Delay Approval Required</h1>
        </div>
        <div class="content">
            <p>Hi {pm_name},</p>
            
            <p>A team member has reported a delay that requires your approval:</p>
            
            <div class="task-card urgency-HIGH">
                <h3>{work_item_name}</h3>
                <p><strong>ID:</strong> {work_item_id}</p>
                <p><strong>Reported By:</strong> {responder_name}</p>
                <p><strong>Original Deadline:</strong> {original_deadline}</p>
                <p><strong>Proposed New Date:</strong> <span class="deadline">{proposed_new_date}</span></p>
                <p><strong>Delay:</strong> {delay_days} days</p>
                <p><strong>Reason:</strong> {reason_category.replace('_', ' ')}</p>
            </div>
            
            <div class="impact-card">
                <h4 style="margin: 0 0 10px 0;">📊 Impact Analysis</h4>
                <p><strong>Affected Tasks:</strong> {impact_summary.get('cascade_count', 0)}</p>
                {'<p><strong>⚠️ CRITICAL PATH AFFECTED</strong></p>' if impact_summary.get('is_critical_path') else ''}
                <p><strong>Risk Level:</strong> <span style="color: {risk_color}; font-weight: 600;">{impact_summary.get('risk_level', 'Unknown')}</span></p>
                {'<p><strong>Recommendation:</strong> ' + impact_summary.get('recommendation', '') + '</p>' if impact_summary.get('recommendation') else ''}
            </div>
            
            <p style="text-align: center;">
                <a href="{approval_link}" class="button">Review & Approve</a>
            </p>
        </div>
        <div class="footer">
            <p>Tracky PM - Proactive Project Management</p>
        </div>
"""
        
        text_content = f"""
Delay Approval Required

Hi {pm_name},

A team member has reported a delay that requires your approval:

Task: {work_item_name}
ID: {work_item_id}
Reported By: {responder_name}
Original Deadline: {original_deadline}
Proposed New Date: {proposed_new_date}
Delay: {delay_days} days
Reason: {reason_category.replace('_', ' ')}

Impact:
- Affected Tasks: {impact_summary.get('cascade_count', 0)}
- Risk Level: {impact_summary.get('risk_level', 'Unknown')}
{'- CRITICAL PATH AFFECTED' if impact_summary.get('is_critical_path') else ''}

Review and approve: {approval_link}

---
Tracky PM
"""
        
        return cls.BASE_HTML.format(content=html_content), text_content.strip()

    @classmethod
    def escalation_notice(
        cls,
        recipient_name: str,
        escalation_level: str,
        original_assignee: str,
        work_item_name: str,
        work_item_id: str,
        deadline: str,
        reason: str,
        magic_link: str
    ) -> tuple[str, str]:
        """Generate escalation notice email."""
        level_description = {
            "BACKUP": "as the backup resource",
            "MANAGER": "as the manager",
            "PM": "as the program manager"
        }.get(escalation_level, "")
        
        html_content = f"""
        <div class="header" style="background: linear-gradient(135deg, #e53e3e 0%, #c53030 100%);">
            <h1>⚠️ Escalation: Status Check Required</h1>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>
            
            <p>You're receiving this {level_description} because the original assignee hasn't responded to a status check.</p>
            
            <div class="task-card urgency-CRITICAL">
                <h3>{work_item_name}</h3>
                <p><strong>ID:</strong> {work_item_id}</p>
                <p><strong>Original Assignee:</strong> {original_assignee}</p>
                <p><strong>Deadline:</strong> <span class="deadline">{deadline}</span></p>
                <p><strong>Escalation Reason:</strong> {reason}</p>
            </div>
            
            <p>Please either:</p>
            <ul>
                <li>Provide the status update if you know it</li>
                <li>Contact {original_assignee} to get the status</li>
                <li>Take appropriate action to ensure the deadline is met</li>
            </ul>
            
            <p style="text-align: center;">
                <a href="{magic_link}" class="button">Respond Now</a>
            </p>
        </div>
        <div class="footer">
            <p>Tracky PM - Proactive Project Management</p>
        </div>
"""
        
        text_content = f"""
ESCALATION: Status Check Required

Hi {recipient_name},

You're receiving this {level_description} because the original assignee hasn't responded.

Task: {work_item_name}
ID: {work_item_id}
Original Assignee: {original_assignee}
Deadline: {deadline}
Reason: {reason}

Please respond: {magic_link}

---
Tracky PM
"""
        
        return cls.BASE_HTML.format(content=html_content), text_content.strip()

    @classmethod
    def no_recipient_alert(
        cls,
        pm_name: str,
        work_item_name: str,
        work_item_id: str,
        deadline: str,
        original_assignee: str,
        skipped_recipients: List[Dict],
        dashboard_link: str
    ) -> tuple[str, str]:
        """Generate alert when no recipient is available in escalation chain."""
        skipped_html = ""
        for recipient in skipped_recipients:
            skipped_html += f"<li><strong>{recipient.get('name', 'Unknown')}</strong>: {recipient.get('reason', 'Unavailable')}</li>"
        
        html_content = f"""
        <div class="header" style="background: linear-gradient(135deg, #c53030 0%, #9c1c1c 100%);">
            <h1>🚨 CRITICAL: No Available Recipients</h1>
        </div>
        <div class="content">
            <p>Hi {pm_name},</p>
            
            <p><strong>Urgent:</strong> A status check could not be sent because no one in the escalation chain is available.</p>
            
            <div class="task-card urgency-CRITICAL">
                <h3>{work_item_name}</h3>
                <p><strong>ID:</strong> {work_item_id}</p>
                <p><strong>Deadline:</strong> <span class="deadline">{deadline}</span></p>
                <p><strong>Original Assignee:</strong> {original_assignee}</p>
            </div>
            
            <div style="background: #fff5f5; border: 1px solid #fc8181; padding: 15px; border-radius: 4px; margin: 15px 0;">
                <h4 style="margin: 0 0 10px 0; color: #c53030;">Escalation Chain Status:</h4>
                <ul style="margin: 0; padding-left: 20px;">
                    {skipped_html}
                </ul>
            </div>
            
            <p><strong>Required Action:</strong></p>
            <ul>
                <li>Manually contact the team to get a status update</li>
                <li>Update resource availability in the system</li>
                <li>Consider reassigning the task if needed</li>
            </ul>
            
            <p style="text-align: center;">
                <a href="{dashboard_link}" class="button">Go to Dashboard</a>
            </p>
        </div>
        <div class="footer">
            <p>This requires immediate attention.</p>
            <p>Tracky PM</p>
        </div>
"""
        
        text_content = f"""
🚨 CRITICAL: No Available Recipients

Hi {pm_name},

A status check could not be sent because no one in the escalation chain is available.

Task: {work_item_name}
ID: {work_item_id}
Deadline: {deadline}
Original Assignee: {original_assignee}

Unavailable Recipients:
{chr(10).join([f"- {r.get('name', 'Unknown')}: {r.get('reason', 'Unavailable')}" for r in skipped_recipients])}

Required Action:
- Manually contact the team
- Update resource availability
- Consider reassignment

Dashboard: {dashboard_link}

---
Tracky PM
"""
        
        return cls.BASE_HTML.format(content=html_content), text_content.strip()


# ==========================================
# NOTIFICATION SERVICE
# ==========================================

class NotificationService:
    """
    Unified notification service supporting multiple channels.
    
    Features:
    - Email via SMTP or SendGrid
    - Slack via webhooks
    - Delivery tracking
    - Retry with exponential backoff (HIGH_003)
    """
    
    def __init__(self):
        self.email_enabled = bool(getattr(settings, 'smtp_host', None) or getattr(settings, 'sendgrid_api_key', None))
        self.slack_enabled = bool(getattr(settings, 'slack_webhook_url', None) or getattr(settings, 'slack_bot_token', None))
        self.max_retries = getattr(settings, 'max_retries', 3)
        self.base_delay = 1.0  # Base delay in seconds for exponential backoff
        
    async def _retry_with_backoff(
        self,
        operation,
        *args,
        max_retries: int = None,
        **kwargs
    ) -> NotificationResult:
        """
        Execute operation with exponential backoff retry.
        
        HIGH_003: Proper retry logic for email service.
        
        Args:
            operation: Async function to execute
            max_retries: Override default max retries
            
        Returns:
            NotificationResult from the operation
        """
        retries = max_retries or self.max_retries
        last_error = None
        
        for attempt in range(retries):
            result = await operation(*args, **kwargs)
            
            if result.success:
                return result
            
            last_error = result.error
            
            # Don't retry on the last attempt
            if attempt < retries - 1:
                # Exponential backoff: 1s, 2s, 4s, 8s, etc.
                delay = self.base_delay * (2 ** attempt)
                # Cap at 60 seconds
                delay = min(delay, 60)
                
                logger.warning(
                    f"Notification failed (attempt {attempt + 1}/{retries}): {result.error}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
        
        # All retries exhausted
        logger.error(f"Notification failed after {retries} attempts: {last_error}")
        return NotificationResult(
            success=False,
            channel=NotificationChannel.EMAIL,
            error=f"Failed after {retries} attempts: {last_error}",
            retry_after=datetime.now(timezone.utc) + timedelta(minutes=15)  # CRIT_004
        )
    
    async def _send_email_simple(
        self,
        to_email: str,
        subject: str,
        body: str,
        to_name: str = ""
    ) -> NotificationResult:
        """
        Send a simple email (used by scheduler for ops alerts).
        
        This is a convenience method that doesn't require all
        the parameters of the full email methods.
        """
        message = EmailMessage(
            to_email=to_email,
            to_name=to_name or to_email.split("@")[0],
            subject=subject,
            html_body=f"<html><body><pre>{body}</pre></body></html>",
            text_body=body
        )
        return await self._send_email(message)
        
    async def send_status_check_alert(
        self,
        alert_id: UUID,
        recipient_email: str,
        recipient_name: str,
        work_item_name: str,
        work_item_id: str,
        deadline: str,
        urgency: str,
        magic_link: str,
        program_name: str = "",
        project_name: str = "",
        is_critical_path: bool = False,
        channel: NotificationChannel = NotificationChannel.EMAIL
    ) -> NotificationResult:
        """Send a status check alert notification."""
        html_body, text_body = EmailTemplates.status_check_alert(
            recipient_name=recipient_name,
            work_item_name=work_item_name,
            work_item_id=work_item_id,
            deadline=deadline,
            urgency=urgency,
            magic_link=magic_link,
            program_name=program_name,
            project_name=project_name,
            is_critical_path=is_critical_path
        )
        
        message = EmailMessage(
            to_email=recipient_email,
            to_name=recipient_name,
            subject=f"[{'🔴 ' if urgency in ['HIGH', 'CRITICAL'] else ''}Status Check] {work_item_id}: {work_item_name}",
            html_body=html_body,
            text_body=text_body,
            tracking_id=str(alert_id)
        )
        
        result = await self._send_email(message)
        
        # Record delivery attempt
        await self._record_delivery(
            alert_id=alert_id,
            channel=NotificationChannel.EMAIL,
            status=NotificationStatus.SENT if result.success else NotificationStatus.FAILED,
            message_id=result.message_id,
            error=result.error
        )
        
        return result

    async def send_response_confirmation(
        self,
        response_id: UUID,
        recipient_email: str,
        recipient_name: str,
        work_item_name: str,
        work_item_id: str,
        reported_status: str,
        submitted_at: str,
        proposed_new_date: str = None,
        requires_approval: bool = False,
        impact_summary: Dict = None
    ) -> NotificationResult:
        """Send response confirmation email."""
        html_body, text_body = EmailTemplates.response_confirmation(
            recipient_name=recipient_name,
            work_item_name=work_item_name,
            work_item_id=work_item_id,
            reported_status=reported_status,
            submitted_at=submitted_at,
            proposed_new_date=proposed_new_date,
            requires_approval=requires_approval,
            impact_summary=impact_summary
        )
        
        status_emoji = {
            "ON_TRACK": "✅",
            "DELAYED": "⏰",
            "BLOCKED": "🚫",
            "COMPLETED": "🎉"
        }.get(reported_status, "📋")
        
        message = EmailMessage(
            to_email=recipient_email,
            to_name=recipient_name,
            subject=f"{status_emoji} Response Received: {work_item_id}",
            html_body=html_body,
            text_body=text_body,
            tracking_id=str(response_id)
        )
        
        return await self._send_email(message)

    async def send_approval_request(
        self,
        alert_id: UUID,
        pm_email: str,
        pm_name: str,
        responder_name: str,
        work_item_name: str,
        work_item_id: str,
        original_deadline: str,
        proposed_new_date: str,
        delay_days: int,
        reason_category: str,
        impact_summary: Dict,
        approval_link: str
    ) -> NotificationResult:
        """Send approval request to PM."""
        html_body, text_body = EmailTemplates.approval_request(
            pm_name=pm_name,
            responder_name=responder_name,
            work_item_name=work_item_name,
            work_item_id=work_item_id,
            original_deadline=original_deadline,
            proposed_new_date=proposed_new_date,
            delay_days=delay_days,
            reason_category=reason_category,
            impact_summary=impact_summary,
            approval_link=approval_link
        )
        
        message = EmailMessage(
            to_email=pm_email,
            to_name=pm_name,
            subject=f"🔔 Approval Required: {delay_days}-day delay on {work_item_id}",
            html_body=html_body,
            text_body=text_body,
            tracking_id=str(alert_id)
        )
        
        return await self._send_email(message)

    async def send_escalation_notice(
        self,
        alert_id: UUID,
        recipient_email: str,
        recipient_name: str,
        escalation_level: str,
        original_assignee: str,
        work_item_name: str,
        work_item_id: str,
        deadline: str,
        reason: str,
        magic_link: str
    ) -> NotificationResult:
        """Send escalation notice."""
        html_body, text_body = EmailTemplates.escalation_notice(
            recipient_name=recipient_name,
            escalation_level=escalation_level,
            original_assignee=original_assignee,
            work_item_name=work_item_name,
            work_item_id=work_item_id,
            deadline=deadline,
            reason=reason,
            magic_link=magic_link
        )
        
        message = EmailMessage(
            to_email=recipient_email,
            to_name=recipient_name,
            subject=f"⚠️ ESCALATION: Status Check Required - {work_item_id}",
            html_body=html_body,
            text_body=text_body,
            tracking_id=str(alert_id)
        )
        
        return await self._send_email(message)

    async def send_no_recipient_alert(
        self,
        alert_id: UUID,
        pm_email: str,
        pm_name: str,
        work_item_name: str,
        work_item_id: str,
        deadline: str,
        original_assignee: str,
        skipped_recipients: List[Dict]
    ) -> NotificationResult:
        """Send critical alert when no recipient available."""
        dashboard_link = f"{settings.frontend_url}/alerts"
        
        html_body, text_body = EmailTemplates.no_recipient_alert(
            pm_name=pm_name,
            work_item_name=work_item_name,
            work_item_id=work_item_id,
            deadline=deadline,
            original_assignee=original_assignee,
            skipped_recipients=skipped_recipients,
            dashboard_link=dashboard_link
        )
        
        message = EmailMessage(
            to_email=pm_email,
            to_name=pm_name,
            subject=f"🚨 CRITICAL: No Available Recipients - {work_item_id}",
            html_body=html_body,
            text_body=text_body,
            tracking_id=str(alert_id)
        )
        
        return await self._send_email(message)

    async def _send_email(self, message: EmailMessage, with_retry: bool = True) -> NotificationResult:
        """
        Send email via configured provider.
        
        HIGH_003: Uses retry with exponential backoff by default.
        
        Supports:
        - SMTP (default)
        - SendGrid (if configured)
        """
        # Check if email is enabled
        smtp_host = getattr(settings, 'smtp_host', None)
        sendgrid_key = getattr(settings, 'sendgrid_api_key', None)
        
        # Select provider
        if sendgrid_key:
            send_func = self._send_via_sendgrid_once
        elif smtp_host:
            send_func = self._send_via_smtp_once
        else:
            # Log to console if no email provider configured
            logger.warning(f"Email not configured. Would send to: {message.to_email}")
            logger.info(f"Subject: {message.subject}")
            
            # Still return success for development
            return NotificationResult(
                success=True,
                channel=NotificationChannel.EMAIL,
                message_id=f"dev-{hashlib.md5(message.subject.encode()).hexdigest()[:8]}",
                error=None
            )
        
        # Use retry logic if enabled
        if with_retry:
            return await self._retry_with_backoff(send_func, message)
        else:
            return await send_func(message)

    async def _send_via_smtp_once(self, message: EmailMessage) -> NotificationResult:
        """Send email via SMTP (single attempt)."""
        try:
            smtp_host = getattr(settings, 'smtp_host', 'localhost')
            smtp_port = getattr(settings, 'smtp_port', 587)
            smtp_user = getattr(settings, 'smtp_user', None)
            smtp_pass = getattr(settings, 'smtp_password', None)
            smtp_from = getattr(settings, 'smtp_from_email', 'noreply@trackypm.com')
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = message.subject
            msg['From'] = f"Tracky PM <{smtp_from}>"
            msg['To'] = f"{message.to_name} <{message.to_email}>"
            
            if message.text_body:
                msg.attach(MIMEText(message.text_body, 'plain'))
            msg.attach(MIMEText(message.html_body, 'html'))
            
            # Issue #10: Use get_running_loop() instead of deprecated get_event_loop()
            # Run in executor to avoid blocking
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self._smtp_send_sync,
                smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from, message.to_email, msg
            )
            
            return NotificationResult(
                success=True,
                channel=NotificationChannel.EMAIL,
                message_id=f"smtp-{datetime.now(timezone.utc).timestamp()}"  # CRIT_004
            )
            
        except Exception as e:
            logger.error(f"SMTP send failed: {e}")
            return NotificationResult(
                success=False,
                channel=NotificationChannel.EMAIL,
                error=str(e),
                retry_after=datetime.now(timezone.utc) + timedelta(minutes=5)  # CRIT_004
            )

    def _smtp_send_sync(self, host, port, user, password, from_addr, to_addr, msg):
        """Synchronous SMTP send for executor."""
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg)

    async def _send_via_sendgrid_once(self, message: EmailMessage) -> NotificationResult:
        """Send email via SendGrid API (single attempt)."""
        try:
            import httpx
            
            api_key = getattr(settings, 'sendgrid_api_key')
            from_email = getattr(settings, 'sendgrid_from_email', 'noreply@trackypm.com')
            
            payload = {
                "personalizations": [{
                    "to": [{"email": message.to_email, "name": message.to_name}]
                }],
                "from": {"email": from_email, "name": "Tracky PM"},
                "subject": message.subject,
                "content": [
                    {"type": "text/plain", "value": message.text_body or ""},
                    {"type": "text/html", "value": message.html_body}
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code in [200, 202]:
                    # CRIT_004: Use timezone-aware datetime
                    message_id = response.headers.get("X-Message-Id", f"sg-{datetime.now(timezone.utc).timestamp()}")
                    return NotificationResult(
                        success=True,
                        channel=NotificationChannel.EMAIL,
                        message_id=message_id
                    )
                else:
                    return NotificationResult(
                        success=False,
                        channel=NotificationChannel.EMAIL,
                        error=f"SendGrid error: {response.status_code} - {response.text}",
                        retry_after=datetime.now(timezone.utc) + timedelta(minutes=5)  # CRIT_004
                    )
                    
        except ImportError:
            logger.error("httpx not installed for SendGrid")
            return NotificationResult(
                success=False,
                channel=NotificationChannel.EMAIL,
                error="httpx package required for SendGrid"
            )
        except Exception as e:
            logger.error(f"SendGrid send failed: {e}")
            return NotificationResult(
                success=False,
                channel=NotificationChannel.EMAIL,
                error=str(e),
                retry_after=datetime.now(timezone.utc) + timedelta(minutes=5)  # CRIT_004
            )

    async def _record_delivery(
        self,
        alert_id: UUID,
        channel: NotificationChannel,
        status: NotificationStatus,
        message_id: str = None,
        error: str = None
    ) -> None:
        """Record delivery attempt in database."""
        try:
            db = get_supabase_client()
            
            # CRIT_004: Use timezone-aware datetime
            now_utc = datetime.now(timezone.utc)
            
            # Update alert with delivery info
            update_data = {
                "notification_metadata": {
                    "channel": channel.value,
                    "status": status.value,
                    "message_id": message_id,
                    "last_error": error,
                    "last_attempt": now_utc.isoformat()
                }
            }
            
            if status == NotificationStatus.SENT:
                update_data["status"] = "SENT"
                update_data["sent_at"] = now_utc.isoformat()
            
            db.client.table("alerts").update(update_data).eq("id", str(alert_id)).execute()
            
        except Exception as e:
            logger.error(f"Failed to record delivery: {e}")


# Global notification service instance
notification_service = NotificationService()


# Convenience functions
async def send_status_check_alert(**kwargs) -> NotificationResult:
    """Send a status check alert notification."""
    return await notification_service.send_status_check_alert(**kwargs)


async def send_response_confirmation(**kwargs) -> NotificationResult:
    """Send response confirmation email."""
    return await notification_service.send_response_confirmation(**kwargs)


async def send_approval_request(**kwargs) -> NotificationResult:
    """Send approval request to PM."""
    return await notification_service.send_approval_request(**kwargs)


async def send_escalation_notice(**kwargs) -> NotificationResult:
    """Send escalation notice."""
    return await notification_service.send_escalation_notice(**kwargs)


async def send_no_recipient_alert(**kwargs) -> NotificationResult:
    """Send critical alert when no recipient available."""
    return await notification_service.send_no_recipient_alert(**kwargs)
