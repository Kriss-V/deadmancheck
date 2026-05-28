from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str
    access_token_expire_minutes: int = 10080  # 7 days

    resend_api_key: str = ""
    alert_from_email: str = "alerts@deadmancheck.io"
    admin_email: str = ""

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro: str = ""

    app_url: str = "http://localhost:8000"
    environment: str = "development"

    plan_free_monitors: int = 5

    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
