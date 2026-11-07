from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    model_name: str = Field(
        default="claude-opus-5-5",
        validation_alias=AliasChoices("LACAZE_MODEL", "ANTHROPIC_MODEL"),
    )
    # None means the official Anthropic API; set it only for a proxy.
    base_url: str | None = Field(default=None, validation_alias="ANTHROPIC_BASE_URL")
    auth_token: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_AUTH_TOKEN")
    api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    data_dir: Path = Field(
        default=Path(__file__).resolve().parents[3] / "data",
        validation_alias="LACAZE_DATA_DIR",
    )
    request_timeout_seconds: float = Field(
        default=180, gt=0, validation_alias="LACAZE_REQUEST_TIMEOUT_SECONDS"
    )
