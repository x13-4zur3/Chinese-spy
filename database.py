from __future__ import annotations

from dataclasses import dataclass
import os
import sqlite3
import boto3
from botocore.exceptions import ClientError
import aiosqlite

from config import DATABASE_PATH, DEFAULT_PREFIX, STARTING_BALANCE

# --- AWS S3 SYNC CONFIGURATION ---
BUCKET_NAME = "my-casino-bot-storage-123" 
DB_FILE_NAME = "casino.db"

s3_client = boto3.client('s3')

def download_db_from_s3():
    """Downloads casino.db from S3 to the server folder on bot boot."""
    try:
        print("Checking AWS S3 for existing casino.db data...")
        s3_client.download_file(BUCKET_NAME, DB_FILE_NAME, DB_FILE_NAME)
        print("Database sync from AWS complete!")
    except ClientError as e:
        if e.response['Error']['Code'] == "404":
            print("No existing database found in S3. Creating a fresh tracking database.")
            open(DB_FILE_NAME, 'a').close()
        else:
            print(f"AWS S3 Download Warning: {e}")

def upload_db_to_s3():
    """Uploads the local casino.db file back up to AWS S3 securely."""
    try:
        s3_client.upload_file(DB_FILE_NAME, BUCKET_NAME, DB_FILE_NAME)
        print("Changes saved and backed up to AWS S3 successfully.")
    except Exception as e:
        print(f"AWS S3 Backup Error: {e}")

# Trigger structural synchronization immediately when database.py is imported on boot
download_db_from_s3()
# ----------------------------------

BALANCE_TOPUP_MIGRATION_KEY = "bonus_topup_20260615_100000"
BALANCE_TOPUP_AMOUNT = 100_000

@dataclass
class GuildSettings:
    guild_id: int
    prefix: str = DEFAULT_PREFIX
    log_channel_id: int | None = None
    coinflip_house_edge: int = 0
    log_member_events: bool = True
    log_message_events: bool = True
    log_mod_events: bool = True
    log_game_events: bool = True
    casino_enabled: bool = True
class Database:
    def __init__(self, path: str = DATABASE_PATH):
        self.path = path

    # One-time startup migrations that should run exactly once per database.
    async def _apply_startup_migrations(self, db: aiosqlite.Connection) -> None:
        async with db.execute(
            "SELECT value FROM app_meta WHERE key = ?",
            (BALANCE_TOPUP_MIGRATION_KEY,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is not None:
                return
            await db.execute("UPDATE users SET balance = balance + ?", (BALANCE_TOPUP_AMOUNT,))
            await db.execute(
                "INSERT INTO app_meta (key, value) VALUES (?, ?)",
                (BALANCE_TOPUP_MIGRATION_KEY, "applied"),
            )

    async def connect(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL,
                    last_daily REAL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    prefix TEXT NOT NULL DEFAULT '!',
                    log_channel_id INTEGER,
                    coinflip_house_edge INTEGER NOT NULL DEFAULT 0,
                    log_member_events INTEGER NOT NULL DEFAULT 1,
                    log_message_events INTEGER NOT NULL DEFAULT 1,
                    log_mod_events INTEGER NOT NULL DEFAULT 1,
                    log_game_events INTEGER NOT NULL DEFAULT 1,
                    casino_enabled INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            await self._apply_startup_migrations(db)
            await db.commit()
        
        # Backup the schema creation structure to S3
        upload_db_to_s3()

    async def get_balance(self, user_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0]
                await db.execute(
                    "INSERT INTO users (user_id, balance, last_daily) VALUES (?, ?, NULL)",
                    (user_id, STARTING_BALANCE),
                )
                await db.commit()
        
        # New row was initialized, backup to S3
        upload_db_to_s3()
        return STARTING_BALANCE

    async def set_balance(self, user_id: int, balance: int) -> None:
        await self.get_balance(user_id)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (max(0, balance), user_id),
            )
            await db.commit()
        
        # Balance was updated, backup to S3
        upload_db_to_s3()

    async def adjust_balance(self, user_id: int, delta: int) -> int:
        balance = await self.get_balance(user_id)
        new_balance = max(0, balance + delta)
        await self.set_balance(user_id, new_balance)
        return new_balance

    async def can_claim_daily(self, user_id: int) -> tuple[bool, int]:
        import time
        await self.get_balance(user_id)
        now = time.time()
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT last_daily FROM users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                last_daily = row[0] if row and row[0] else 0
                elapsed = now - last_daily
                cooldown = 86400
                if elapsed >= cooldown:
                    return True, 0
                return False, int(cooldown - elapsed)

    async def claim_daily(self, user_id: int, amount: int) -> int:
        import time
        can_claim, _ = await self.can_claim_daily(user_id)
        if not can_claim:
            raise ValueError("Daily already claimed")
        now = time.time()
        new_balance = await self.adjust_balance(user_id, amount)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET last_daily = ? WHERE user_id = ?",
                (now, user_id),
            )
            await db.commit()
        
        # Daily timestamp updated, backup to S3
        upload_db_to_s3()
        return new_balance

        async def leaderboard(self, limit: int = 10) -> list[tuple[int, int]]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """
                SELECT user_id, balance
                FROM users
                ORDER BY balance DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                return await cursor.fetchall()

    def _row_to_settings(self, guild_id: int, row: tuple | None) -> GuildSettings:
        if row is None:
            return GuildSettings(guild_id=guild_id)

        return GuildSettings(
            guild_id=guild_id,
            prefix=row[0] or DEFAULT_PREFIX,
            log_channel_id=row[1],
            coinflip_house_edge=max(0, min(10, row[2] or 0)),
            log_member_events=bool(row[3]),
            log_message_events=bool(row[4]),
            log_mod_events=bool(row[5]),
            log_game_events=bool(row[6]),
            casino_enabled=bool(row[7]),
        )

    async def get_guild_settings(self, guild_id: int) -> GuildSettings:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """
                SELECT prefix, log_channel_id, coinflip_house_edge,
                       log_member_events, log_message_events,
                       log_mod_events, log_game_events, casino_enabled
                FROM guild_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()

        return self._row_to_settings(guild_id, row)

    async def update_guild_settings(
        self,
        guild_id: int,
        **kwargs: object
    ) -> GuildSettings:
        current = await self.get_guild_settings(guild_id)

        data = {
            "prefix": kwargs.get("prefix", current.prefix),
            "log_channel_id": kwargs.get("log_channel_id", current.log_channel_id),
            "coinflip_house_edge": kwargs.get(
                "coinflip_house_edge",
                current.coinflip_house_edge,
            ),
            "log_member_events": int(
                kwargs.get("log_member_events", current.log_member_events)
            ),
            "log_message_events": int(
                kwargs.get("log_message_events", current.log_message_events)
            ),
            "log_mod_events": int(
                kwargs.get("log_mod_events", current.log_mod_events)
            ),
            "log_game_events": int(
                kwargs.get("log_game_events", current.log_game_events)
            ),
            "casino_enabled": int(
                kwargs.get("casino_enabled", current.casino_enabled)
            ),
        }

        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO guild_settings (
                    guild_id,
                    prefix,
                    log_channel_id,
                    coinflip_house_edge,
                    log_member_events,
                    log_message_events,
                    log_mod_events,
                    log_game_events,
                    casino_enabled
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    prefix = excluded.prefix,
                    log_channel_id = excluded.log_channel_id,
                    coinflip_house_edge = excluded.coinflip_house_edge,
                    log_member_events = excluded.log_member_events,
                    log_message_events = excluded.log_message_events,
                    log_mod_events = excluded.log_mod_events,
                    log_game_events = excluded.log_game_events,
                    casino_enabled = excluded.casino_enabled
                """,
                (
                    guild_id,
                    str(data["prefix"])[:5],
                    data["log_channel_id"],
                    max(0, min(10, int(data["coinflip_house_edge"]))),
                    data["log_member_events"],
                    data["log_message_events"],
                    data["log_mod_events"],
                    data["log_game_events"],
                    data["casino_enabled"],
                ),
            )

            await db.commit()

        upload_db_to_s3()

        return await self.get_guild_settings(guild_id)
