from dataclasses import dataclass
from typing import Self

from bs_config import Env
from bs_nats_updater import NatsConfig


@dataclass
class StateConfig:
    redis_host: str
    redis_username: str
    redis_password: str

    @property
    def redis_key(self):
        return f"{self.redis_username}:state"

    @classmethod
    def from_env(cls, env: Env) -> Self | None:
        host = env.get_string("REDIS_HOST")
        if host is None:
            return None

        return cls(
            redis_host=host,
            redis_username=env.get_string("REDIS_USERNAME", required=True),
            redis_password=env.get_string("REDIS_PASSWORD", required=True),
        )


@dataclass
class Config:
    app_version: str
    nats: NatsConfig
    sentry_dsn: str | None
    state: StateConfig | None
    telegram_token: str

    @classmethod
    def from_env(cls, env: Env) -> Self:
        return cls(
            app_version=env.get_string("APP_VERSION", default="dev"),
            nats=NatsConfig.from_env(env.scoped("NATS_")),
            sentry_dsn=env.get_string("SENTRY_DSN"),
            state=StateConfig.from_env(env.scoped("STATE_")),
            telegram_token=env.get_string("TELEGRAM_TOKEN", required=True),
        )
