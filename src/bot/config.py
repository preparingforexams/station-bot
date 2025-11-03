import logging
from dataclasses import dataclass
from functools import cache
from typing import Self

from bs_config import Env
from bs_nats_updater import NatsConfig

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class StateConfig:
    redis_host: str
    redis_username: str
    redis_password: str

    @property
    def redis_key(self):
        return f"{self.redis_username}:state"

    @classmethod
    def from_env(cls, env: Env) -> Self | None:
        redis = env / "redis"
        host = redis.get_string("host")
        if host is None:
            _logger.warning("State not configured")
            return None

        return cls(
            redis_host=host,
            redis_username=redis.get_string("username", required=True),
            redis_password=redis.get_string("password", required=True),
        )


@dataclass(frozen=True, kw_only=True)
class UserAgentConfig:
    client_name: str
    contact_email: str
    project_url: str

    @cache
    def build_header_value(self) -> str:
        from importlib.metadata import version

        bot_version = version("bot")
        httpx_version = version("httpx")

        return f"{self.client_name}/{bot_version} ({self.project_url}; {self.contact_email}) httpx/{httpx_version}"

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            client_name=env.get_string("client-name", default="station-bot"),
            contact_email=env.get_string(
                "contact-email",
                default="station-bot@bjoernpetersen.net",
            ),
            project_url=env.get_string(
                "project-url",
                default="https://github.com/preparingforexams/station-bot",
            ),
        )


@dataclass(frozen=True, kw_only=True)
class Config:
    app_version: str
    nats: NatsConfig
    sentry_dsn: str | None
    state: StateConfig | None
    telegram_token: str
    user_agent: UserAgentConfig

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            app_version=env.get_string("app-version", default="dev"),
            nats=NatsConfig.from_env(env / "nats"),
            sentry_dsn=env.get_string("sentry-dsn"),
            state=StateConfig.from_env(env / "state"),
            telegram_token=env.get_string("telegram-token", required=True),
            user_agent=UserAgentConfig.from_env(env / "user-agent"),
        )
