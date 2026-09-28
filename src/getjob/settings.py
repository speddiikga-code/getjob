"""Runtime settings and secrets, read from environment variables and `.env`."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )

    profile_path: Path = Field(Path("config/search.yaml"), validation_alias="GETJOB_PROFILE")
    apply_path: Path = Field(Path("config/apply.yaml"), validation_alias="GETJOB_APPLY_PROFILE")
    experience_path: Path = Field(
        Path("config/experience.yaml"), validation_alias="GETJOB_EXPERIENCE"
    )
    db_path: Path = Field(Path("data/jobs.db"), validation_alias="GETJOB_DB_PATH")
    log_level: str = Field("INFO", validation_alias="GETJOB_LOG_LEVEL")
    request_delay: float = Field(2.0, ge=0, validation_alias="GETJOB_REQUEST_DELAY")
    timeout: float = Field(20.0, gt=0, validation_alias="GETJOB_TIMEOUT")
    user_agent: str = Field(DEFAULT_USER_AGENT, validation_alias="GETJOB_USER_AGENT")

    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    notify_email_to: str | None = None

    saramin_api_key: SecretStr | None = None
    # Drafts 자기소개서 with Claude; without it the offline template engine is used.
    anthropic_api_key: SecretStr | None = None

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def email_ready(self) -> bool:
        return bool(self.smtp_user and self.smtp_password and self.notify_email_to)

    @property
    def applications_dir(self) -> Path:
        """Draft packages live next to the database, e.g. data/applications/."""
        return self.db_path.parent / "applications"

    @property
    def anthropic_key(self) -> str | None:
        return self.anthropic_api_key.get_secret_value() if self.anthropic_api_key else None
