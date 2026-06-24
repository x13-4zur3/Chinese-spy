#!/bin/bash

cd /var/app/current

echo "=== SCRIPT EXECUTED ===" >> startup_test.log
date >> startup_test.log

pwd >> startup_test.log

ls -la >> startup_test.log

nohup python3 bot.py >> startup_test.log 2>&1 &
