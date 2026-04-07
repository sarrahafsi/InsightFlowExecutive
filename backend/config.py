from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gmail_credentials_path: str = "credentials.json"
    gmail_token_path: str = "token.json"
    gmail_redirect_uri: str = "http://localhost:8000/auth/gmail/callback"

    database_url: str = "postgresql://postgres:postgres@localhost:5432/insightflow"

    class Config:
        env_file = ".env"


settings = Settings()
