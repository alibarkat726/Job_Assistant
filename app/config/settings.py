from typing import List, Union
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App Basics
    APP_NAME: str = "Job Assistant AI Platform"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = Field(..., min_length=32, description="App secret key for cryptographic operations")
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000", "http://127.0.0.1:3000","http://localhost:41391"]

    # Database
    DATABASE_URL: str = Field(..., description="PostgreSQL async connection string")
    TEST_DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres@localhost:5432/job_assistant_test_db",
        description="Test database async connection string"
    )

    # Security & JWT Tokens
    JWT_SECRET_KEY: str = Field(..., min_length=32, description="JWT signing secret key")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Rate Limiting & Account Lockout
    MAX_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15

    # File Storage & CV Intake
    MAX_UPLOAD_SIZE_MB: int = 10
    STORAGE_DIR: str = "./storage/cvs"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gemini-2.5-flash"

    # OpenAI & LLM Settings
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    RAG_TEST_MODE: bool = False
    RAG_EMBEDDING_BATCH_SIZE: int = Field(default=64, ge=1, le=256)
    RAG_PROVIDER_TIMEOUT_SECONDS: float = Field(default=30, gt=0, le=120)
    RAG_PROVIDER_MAX_RETRIES: int = Field(default=2, ge=0, le=3)
    RAG_CHUNK_TOKENS: int = Field(default=400, ge=100, le=1000)
    RAG_CHUNK_OVERLAP_TOKENS: int = Field(default=60, ge=0, le=99)
    RAG_CONTEXT_TOKENS: int = Field(default=4000, ge=500, le=16000)
    RAG_HISTORY_TOKENS: int = Field(default=2000, ge=0, le=8000)
    RAG_OUTPUT_TOKENS: int = Field(default=1000, ge=100, le=4000)
    RAG_MIN_SIMILARITY: float = Field(default=0.25, ge=-1, le=1)
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    RAG_CHAT_RATE_LIMIT: str = "20/minute"
    RAG_SYNC_RATE_LIMIT: str = "2/minute"
    RAG_DAILY_TOKEN_BUDGET: int = Field(default=100_000, ge=1000)
    MAX_EXTRACTED_TEXT_CHARS: int = Field(default=200_000, ge=1000)
    MAX_PDF_PAGES: int = Field(default=100, ge=1)
    MAX_DOCX_EXPANDED_BYTES: int = Field(default=20 * 1024 * 1024, ge=1000)

    @model_validator(mode="after")
    def production_configuration(self):
        if self.RAG_TEST_MODE and self.ENVIRONMENT != "testing":
            raise ValueError("RAG_TEST_MODE is restricted to testing")
        if self.ENVIRONMENT == "production":
            if not self.RATE_LIMIT_STORAGE_URI.startswith(("redis://", "rediss://")):
                raise ValueError("Production requires shared Redis rate-limit and token-budget storage")
            if "*" in self.CORS_ORIGINS:
                raise ValueError("Production requires explicit CORS origins")
            if not self.OPENAI_API_KEY:
                raise ValueError("Production RAG requires OPENAI_API_KEY")
        return self

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                return json.loads(v)
            return [i.strip() for i in v.split(",") if i.strip()]
        return v


settings = Settings()
