#!/bin/bash

echo "=== POSTDEPLOY STARTING BOT ===" >> /var/log/bot.log

cd /var/app/current

echo "PWD=$(pwd)" >> /var/log/bot.log

ls -la >> /var/log/bot.log

which python3 >> /var/log/bot.log

python3 --version >> /var/log/bot.log

nohup python3 bot.py >> /var/log/bot.log 2>&1 &
