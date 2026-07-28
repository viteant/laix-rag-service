from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "laix-rag-service"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "laix_rag"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@postgres:5432/laix_rag"

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    # Seguridad / JWT
    JWT_SECRET_KEY: str = "super_secret_jwt_key_cambiar_en_produccion"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 24 horas

    # CORS
    CORS_ORIGINS: str = ""

    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    EMBEDDING_DIMENSIONS: int = 768

    # LLM classifier for Registro Oficial indexes
    LLM_CLASSIFIER_ENABLED: bool = False
    LLM_CLASSIFIER_PROVIDER: str = "openai_compatible"
    LLM_CLASSIFIER_MODEL: str = ""
    LLM_CLASSIFIER_API_KEY: str = ""
    LLM_CLASSIFIER_BASE_URL: str = "https://api.openai.com/v1"
    LLM_CLASSIFIER_TIMEOUT_SECONDS: int = 45
    LLM_CLASSIFIER_TEMPERATURE: float = 0
    LLM_CLASSIFIER_MAX_INDEX_PAGES: int = 3
    LLM_CLASSIFIER_MAX_INPUT_CHARS: int = 18000
    LLM_CLASSIFIER_PROMPT_VERSION: str = "registro-oficial-v1"

    # Emergency disk-space relief for the public-source batch.
    PIPELINE_STORAGE_PATH: str = "/app/data"
    PIPELINE_MIN_FREE_SPACE_PERCENT: float = 20
    PIPELINE_RESUME_FREE_SPACE_PERCENT: float = 40
    PDF_OPTIMIZATION_PROFILE: str = "ebook"
    PDF_OPTIMIZATION_TIMEOUT_SECONDS: int = 600
    PIPELINE_PROCESS_CONCURRENCY: int = 2
    PIPELINE_OCR_CONCURRENCY: int = 4

    # Cloudflare R2 (S3-compatible API)
    R2_ENDPOINT_URL: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    R2_REGION: str = "auto"
    R2_PREFIX: str = "public"
    PUBLIC_PIPELINE_SCHEDULER_ENABLED: bool = False

    # Alertas SMTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    ALERT_EMAIL_TO: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
