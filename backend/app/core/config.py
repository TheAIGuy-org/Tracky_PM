"""
Configuration management using Pydantic Settings.
Loads environment variables from .env file.
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Application
    app_name: str = "Tracky PM"
    app_version: str = "0.1.0"
    debug: bool = False
    
    # Supabase Configuration
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: Optional[str] = None  # For admin operations
    
    # JWT Configuration (for magic links)
    jwt_secret: Optional[str] = None  # Falls back to supabase_key if not set
    jwt_expiry_hours: int = 72  # Magic link validity (3 days)
    
    # Frontend URL (for magic link generation)
    frontend_url: str = "http://localhost:5173"
    
    # Import Settings
    noise_threshold_days: int = 2  # Default threshold for ignoring minor date changes
    max_upload_size_mb: int = 10  # Maximum Excel file size in MB
    
    # CORS Settings (for Frontend)
    cors_origins: str = "http://localhost:5173"  # Vite default port
    
    # Email Configuration (SMTP)
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: str = "noreply@trackypm.com"
    smtp_from_name: str = "Tracky PM"
    smtp_use_tls: bool = True
    
    # SendGrid Configuration (alternative to SMTP)
    sendgrid_api_key: Optional[str] = None
    sendgrid_from_email: str = "noreply@trackypm.com"
    
    # Slack Configuration
    slack_webhook_url: Optional[str] = None
    slack_bot_token: Optional[str] = None
    
    # Scheduler Settings
    enable_scheduler: bool = True
    scheduler_timezone: str = "UTC"
    
    # CRITICAL FIX (A): Only ONE worker should run scheduler in multi-worker deployments
    # Set RUN_SCHEDULER=true on only ONE container/worker to prevent duplicate emails
    run_scheduler: bool = False  # Default FALSE - must be explicitly enabled
    
    # CRITICAL: Operations Team Fallback (CRIT_002)
    # This email receives alerts when no PM is configured
    ops_escalation_email: Optional[str] = None
    ops_escalation_name: str = "Operations Team"
    
    # Alert Processing Settings
    alert_batch_size: int = 50  # Process alerts in batches
    alert_batch_delay_seconds: int = 5  # Delay between batches
    max_email_retries: int = 3  # Retry failed emails
    email_retry_backoff_base: int = 60  # Base backoff in seconds
    
    # Escalation Settings
    escalation_timeout_business_hours: bool = True  # Use business hours for timeouts
    pm_approval_timeout_hours: int = 24  # Auto-escalate after this many hours
    
    # Job Monitoring
    job_failure_alert_threshold: int = 2  # Alert after this many failures
    
    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    @property
    def email_enabled(self) -> bool:
        """Check if email is configured."""
        return bool(self.smtp_host or self.sendgrid_api_key)
    
    @property
    def slack_enabled(self) -> bool:
        """Check if Slack is configured."""
        return bool(self.slack_webhook_url or self.slack_bot_token)
    
    @property
    def has_fallback_escalation(self) -> bool:
        """Check if fallback escalation is configured."""
        return bool(self.ops_escalation_email)


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance.
    Call this function to get application settings.
    """
    return Settings()


# Global settings instance
settings = get_settings()
