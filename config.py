import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
STARTING_BALANCE = int(os.getenv("STARTING_BALANCE", "1000"))
DAILY_REWARD = int(os.getenv("DAILY_REWARD", "500"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "casino.db")
DEFAULT_PREFIX = os.getenv("DEFAULT_PREFIX", "!")
