import asyncio
import logging
from typing import TYPE_CHECKING

import sentry_sdk
import uvloop
from bs_config import Env

from bot.bot import StationBot
from bot.config import Config

if TYPE_CHECKING:
    from bot.state import StateStorageFactory

_logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig()
    _logger.root.level = logging.WARNING
    logging.getLogger(__package__).level = logging.DEBUG


def _setup_sentry(config: Config) -> None:
    dsn = config.sentry_dsn
    if dsn is None:
        _logger.warning("Sentry DSN not configured")
        return

    sentry_sdk.init(
        dsn=dsn,
        release=config.app_version,
    )


def _create_state_storage_factory(config: Config) -> StateStorageFactory:
    state_config = config.state
    if state_config is None:
        from bs_state.implementation import memory_storage

        return lambda initial: memory_storage.load(initial_state=initial)

    from bs_state.implementation import redis_storage

    return lambda initial: redis_storage.load(
        initial_state=initial,
        host=state_config.redis_host,
        username=state_config.redis_username,
        password=state_config.redis_password,
        key=state_config.redis_key,
    )


def main():
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    _setup_logging()

    env = Env.load(include_default_dotenv=True)
    config = Config.from_env(env)

    _setup_sentry(config)

    state_storage_factory = _create_state_storage_factory(config)
    StationBot.run(config, state_storage_factory)


if __name__ == "__main__":
    main()
