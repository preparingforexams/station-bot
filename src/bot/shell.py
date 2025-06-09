from bs_config import Env
from bs_state import StateStorage

from bot.config import Config
from bot.main import _create_state_storage_factory
from bot.state import StationState

env = Env.load(include_default_dotenv=True)
config = Config.from_env(env)
state_storage_factory = _create_state_storage_factory(config)


async def get_state_storage() -> StateStorage[StationState]:
    return await state_storage_factory(StationState.empty())
