from typing import List, Union
from pydantic import Field, field_validator
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
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

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
