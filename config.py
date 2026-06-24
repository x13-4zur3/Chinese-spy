import os
from dotenv import load_dotenv

# Load .env only for local development
# On AWS this will do nothing (which is correct)
load_dotenv()

# -----------------------------
# DISCORD SETTINGS
# -----------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is missing. Check your environment variables.")

# -----------------------------
# BOT SETTINGS
# -----------------------------
DEFAULT_PREFIX = os.getenv("DEFAULT_PREFIX", "!")

VOICE_CHANNEL_ID = int(
    os.getenv("VOICE_CHANNEL_ID", "1511769421830422631")
)

# -----------------------------
# ECONOMY SETTINGS
# -----------------------------
STARTING_BALANCE = int(os.getenv("STARTING_BALANCE", "1000"))
DAILY_REWARD = int(os.getenv("DAILY_REWARD", "500"))

# -----------------------------
# DATABASE SETTINGS
# -----------------------------
DATABASE_PATH = os.getenv("DATABASE_PATH", "casino.db")