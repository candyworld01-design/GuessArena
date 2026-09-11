GUESSARENA — Telegram Group Game Bot

PHONE/TERMUX QUICK START

1) Install Termux from the official F-Droid/GitHub source.
2) In Termux:
   pkg update
   pkg install python
   pip install -r requirements.txt

3) Set your BotFather token WITHOUT posting it anywhere:
   export BOT_TOKEN="PASTE_YOUR_TOKEN_HERE"

4) Run:
   python bot.py

5) Add the bot to a Telegram group. For the first version, give it permission to read messages.
   Members can use:
   /game
   /leaderboard
   /profile
   /help

IMPORTANT
- Never share your bot token.
- This first version uses SQLite and keeps group-specific scores.
- It is intentionally simple so it can be tested on a phone before adding advanced features.
- For a 24/7 public bot, later move the same project to a proper always-on host.
