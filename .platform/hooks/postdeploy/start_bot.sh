#!/bin/bash

echo "=== POSTDEPLOY STARTING BOT ===" >> /var/log/bot.log

cd /var/app/current

pkill -f "python.*bot.py" || true

nohup python3 bot.py >> /var/log/bot.log 2>&1 &