from pathlib import Path

import pytest
from bs_config import Env

from bot.config import Config


@pytest.fixture(scope="session")
def config() -> Config:
    env = Env.load(
        toml_configs=[Path("config-test.toml")],
    )
    return Config.from_env(env)
