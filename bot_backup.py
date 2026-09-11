import os
import random
import sqlite3
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

TOKEN = os.environ.get("BOT_TOKEN")
DB = "guessarena.db"

GAMES = [
    {"type":"word","q":"_ A _ A _","hint":"🐾 Animal","answers":["panda"],"points":10},
    {"type":"city","q":"🌆 Guess the city: Famous for the Gateway of India.","hint":"🇮🇳 It is a major city on India's west coast.","answers":["mumbai"],"points":10},
    {"type":"emoji","q":"🦁 + 👑","hint":"🎬 A famous animated movie.","answers":["lion king","the lion king"],"points":10},
    {"type":"riddle","q":"I have cities but no houses, rivers but no water. What am I?","hint":"🗺️ You can unfold me.","answers":["map","a map"],"points":10},
    {"type":"word","q":"_ P P L _","hint":"🍎 A fruit","answers":["apple"],"points":10},
    {"type":"city","q":"🌆 Guess the city: The Taj Mahal is here.","hint":"🇮🇳 A famous city in Uttar Pradesh.","answers":["agra"],"points":10},
    {"type":"emoji","q":"🐠 + 🌊 + 👦","hint":"🎬 Animated ocean adventure.","answers":["finding nemo"],"points":10},
    {"type":"riddle","q":"What has keys but cannot open locks?","hint":"🎹 Think of music.","answers":["piano","a piano"],"points":10},
]

conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS players(
    chat_id INTEGER, user_id INTEGER, name TEXT, xp INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0, streak INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id,user_id)
)""")
conn.commit()

active = {}  # chat_id -> current round

def ensure_player(chat_id, user):
    cur.execute("""INSERT OR IGNORE INTO players(chat_id,user_id,name)
                   VALUES(?,?,?)""", (chat_id,user.id,user.full_name))
    cur.execute("UPDATE players SET name=? WHERE chat_id=? AND user_id=?",
                (user.full_name,chat_id,user.id))
    conn.commit()

def add_win(chat_id, user):
    ensure_player(chat_id,user)
    cur.execute("""UPDATE players SET xp=xp+10,wins=wins+1,streak=streak+1
                   WHERE chat_id=? AND user_id=?""", (chat_id,user.id))
    conn.commit()

def normalize(s):
    return " ".join(s.lower().strip().split()).replace("the ","",1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎮 <b>GuessArena</b>\\n\\n"
        "Group mein friends ke saath quick guessing games khelo!\\n\\n"
        "🎯 /game — new round\\n"
        "🏆 /leaderboard — group ranking\\n"
        "👤 /profile — your stats\\n"
        "ℹ️ /help — commands"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 <b>GuessArena Help</b>\\n\\n"
        "/game — game start\\n"
        "/leaderboard — top players\\n"
        "/profile — your stats\\n\\n"
        "Round mein answer simply message mein type karo. "
        "Pehla correct answer +10 XP! 🔥",
        parse_mode="HTML"
    )

async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active:
        await update.message.reply_text("⚡ Ek round already chal raha hai! Answer guess karo.")
        return

    g = random.choice(GAMES)
    active[chat_id] = {
        "answers": [normalize(a) for a in g["answers"]],
        "hint": g["hint"],
        "started": time.time()
    }

    keyboard = [[InlineKeyboardButton("💡 Hint", callback_data=f"hint:{chat_id}")]]
    await update.message.reply_text(
        f"🎮 <b>ROUND START!</b>\\n\\n"
        f"🧩 <b>{g['q']}</b>\\n\\n"
        f"⏱️ Jaldi answer karo!\\n"
        f"🏆 Correct answer = +{g['points']} XP",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("hint:"):
        chat_id = int(q.data.split(":")[1])
        game_data = active.get(chat_id)
        if not game_data:
            await q.answer("Round khatam ho gaya.", show_alert=True)
            return
        await q.message.reply_text(f"💡 <b>Hint:</b> {game_data['hint']}", parse_mode="HTML")

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    chat_id = update.effective_chat.id
    game_data = active.get(chat_id)
    if not game_data:
        return

    if normalize(update.message.text) in game_data["answers"]:
        user = update.effective_user
        ensure_player(chat_id,user)
        add_win(chat_id,user)
        active.pop(chat_id,None)
        cur.execute("SELECT xp,wins,streak FROM players WHERE chat_id=? AND user_id=?",
                    (chat_id,user.id))
        xp,wins,streak = cur.fetchone()
        await update.message.reply_text(
            f"🎉 <b>{user.full_name}</b> got it first!\\n\\n"
            f"🏆 +10 XP\\n⭐ Total XP: {xp}\\n"
            f"🔥 Streak: {streak}\\n\\n"
            f"Type /game for the next round!",
            parse_mode="HTML"
        )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cur.execute("""SELECT name,xp,wins FROM players
                   WHERE chat_id=? ORDER BY xp DESC,wins DESC LIMIT 10""",(chat_id,))
    rows = cur.fetchall()
    if not rows:
        await update.message.reply_text("🏆 Abhi leaderboard empty hai. /game se start karo!")
        return
    medals=["🥇","🥈","🥉"]
    lines=["🏆 <b>GROUP LEADERBOARD</b>",""]
    for i,(name,xp,wins) in enumerate(rows,1):
        medal=medals[i-1] if i<=3 else f"{i}."
        lines.append(f"{medal} {name} — ⭐ {xp} XP | 🏆 {wins} wins")
    await update.message.reply_text("\n".join(lines),parse_mode="HTML")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    ensure_player(chat_id,user)
    cur.execute("SELECT xp,wins,streak FROM players WHERE chat_id=? AND user_id=?",
                (chat_id,user.id))
    xp,wins,streak=cur.fetchone()
    level = xp//100 + 1
    await update.message.reply_text(
        f"👤 <b>{user.full_name}</b>\n\n"
        f"⭐ XP: {xp}\n🎮 Level: {level}\n"
        f"🏆 Wins: {wins}\n🔥 Streak: {streak}",
        parse_mode="HTML"
    )

def main():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN missing. Set it before running.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("game", game))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer))
    print("GuessArena is running...")
    app.run_polling(poll_interval=1, timeout=60)

if __name__ == "__main__":
    main()
