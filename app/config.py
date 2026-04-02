from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str
    access_token_expire_minutes: int = 10080  # 7 days

    resend_api_key: str = ""
    alert_from_email: str = "alerts@deadmancheck.io"

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_developer: str = ""
    stripe_price_team: str = ""
    stripe_price_business: str = ""

    app_url: str = "http://localhost:8000"
    environment: str = "development"

    plan_free_monitors: int = 5
    plan_developer_monitors: int = 100
    plan_team_monitors: int = 200
    plan_business_monitors: int = 1000

    class Config:
        env_file = ".env"


settings = Settings()
