#!/bin/bash

echo "=== POSTDEPLOY STARTING BOT ===" >> /var/log/bot.log

cd /var/app/current

# Kill any old bot process
pkill -f "python.*bot.py" || true

# Start bot in background
nohup python3 bot.py >> /var/log/bot.log 2>&1 &
