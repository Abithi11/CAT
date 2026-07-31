from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    jwt_refresh_token_expire_days: int

    # LM Studio (OpenAI-compatible) endpoint. Model auto-detected via /v1/models
    # when llm_model is unset.
    llm_base_url: str = "http://trinity.local:1234/v1"
    llm_model: str | None = None
    llm_timeout_seconds: float = 60.0

    # SMTP for alert email delivery. Leave smtp_host empty to disable email;
    # in-app alerts (alerts table + dashboard) work regardless.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    alert_email_from: str | None = None
    alert_email_to: str | None = None

    # APScheduler alert scan
    scheduler_enabled: bool = True
    alert_scan_interval_minutes: int = 15

    # Demo tenant created by seed_demo.py on docker-compose bring-up
    demo_tenant_slug: str = "demo"
    demo_tenant_name: str = "CAT Rentals Demo"
    demo_email: str = "demo@cat.com"
    demo_password: str = "demo1234"

    model_config = {"env_file": ".env"}

    @field_validator(
        "llm_model", "smtp_host", "smtp_user", "smtp_password",
        "alert_email_from", "alert_email_to", mode="before",
    )
    @classmethod
    def empty_string_is_none(cls, v):
        return v or None


settings = Settings()
