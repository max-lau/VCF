#!/bin/bash
set -a
source /root/nlp-portfolio/.env.voice_bot
set +a
exec /root/nlp-portfolio/.venv/bin/python /root/nlp-portfolio/paraiq_voice_bot.py
