module.exports = {
  apps: [{
    name: "paraiq-voice-bot",
    script: "/root/nlp-portfolio/start_voice_bot.sh",
    cwd: "/root/nlp-portfolio",
    restart_delay: 5000,
    max_restarts: 10,
    log_file: "/root/nlp-portfolio/logs/voice_bot_pm2.log",
    error_file: "/root/nlp-portfolio/logs/voice_bot_error.log",
    time: true,
  }]
};
