from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gmail_credentials_path: str = "credentials.json"
    gmail_token_path: str = "token.json"
    gmail_redirect_uri: str = "http://localhost:8000/auth/gmail/callback"

    database_url: str = "postgresql://postgres:postgres@localhost:5432/insightflow"

    slack_bot_token: str = ""

    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_keys: str = "SCRUM"

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.2"

    # LLM Provider : "ollama" (default, local, free) | "openai" (ChatGPT) | "azure" (GPT-4o, premium)
    llm_provider: str = "ollama"

    # OpenAI ChatGPT (used only when llm_provider=openai)
    openai_api_key: str = ""
    openai_model:   str = "gpt-4o"

    # Azure OpenAI (used only when llm_provider=azure)
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2024-12-01-preview"

    # OneDrive / Microsoft Graph
    onedrive_client_id:     str = ""
    onedrive_client_secret: str = ""
    onedrive_tenant:        str = "common"
    onedrive_redirect_uri:  str = "http://localhost:8000/auth/onedrive/callback"

    # Celery / Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    class Config:
        env_file = ".env"


settings = Settings()
