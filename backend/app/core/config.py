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
    
    # Import Settings
    noise_threshold_days: int = 2  # Default threshold for ignoring minor date changes
    max_upload_size_mb: int = 10  # Maximum Excel file size in MB
    
    # CORS Settings (for Frontend)
    cors_origins: str = "http://localhost:5173"  # Vite default port
    
    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance.
    Call this function to get application settings.
    """
    return Settings()


# Global settings instance
settings = get_settings()
