 import os
from threading import Thread
from flask import Flask

app = Flask(__name__)


@app.route("/")
def health_check():
    return "Bot is Alive!", 200


def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# Render port scan timing ke liye thread ko daemon mode me start karein
server_thread = Thread(target=run_web_server, daemon=True)
server_thread.start()

import os
import random
import sqlite3
import html
import hashlib
from datetime import date

from telegram import Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.environ.get("BOT_TOKEN")
DB = "guessarena.db"

# =========================================================
# QUESTION BANK
# =========================================================

QUESTIONS = [
    # EASY
    {
        "mode": "Word",
        "difficulty": "Easy",
        "q": "_ A _ A _",
        "hint": "🐾 Animal",
        "answers": ["panda"],
        "xp": 10,
    },
    {
        "mode": "Word",
        "difficulty": "Easy",
        "q": "_ P P L _",
        "hint": "🍎 A fruit",
        "answers": ["apple"],
        "xp": 10,
    },
    {
        "mode": "Animal",
        "difficulty": "Easy",
        "q": "🐾 King of the jungle?",
        "hint": "🦁 Big cat",
        "answers": ["lion"],
        "xp": 10,
    },
    {
        "mode": "Emoji",
        "difficulty": "Easy",
        "q": "🌧️ + ☂️ = ?",
        "hint": "🌂 Used when it rains",
        "answers": ["umbrella"],
        "xp": 10,
    },

    # MEDIUM
    {
        "mode": "City",
        "difficulty": "Medium",
        "q": "🌆 Gateway of India kis city mein hai?",
        "hint": "🇮🇳 Major city on India's west coast",
        "answers": ["mumbai"],
        "xp": 20,
    },
    {
        "mode": "City",
        "difficulty": "Medium",
        "q": "🕌 Taj Mahal kis city mein hai?",
        "hint": "🇮🇳 Uttar Pradesh",
        "answers": ["agra"],
        "xp": 20,
    },
    {
        "mode": "Riddle",
        "difficulty": "Medium",
        "q": "Cities hain, houses nahi. Rivers hain, water nahi. Main kya hoon?",
        "hint": "🗺️ Fold karke rakha ja sakta hai",
        "answers": ["map", "a map"],
        "xp": 20,
    },
    {
        "mode": "Riddle",
        "difficulty": "Medium",
        "q": "Keys hain, lekin locks nahi khol sakta. Kya hai?",
        "hint": "🎹 Music",
        "answers": ["piano", "a piano"],
        "xp": 20,
    },
    {
        "mode": "Emoji",
        "difficulty": "Medium",
        "q": "🦁 + 👑 = ?",
        "hint": "🎬 Famous animated story",
        "answers": ["lion king", "the lion king"],
        "xp": 20,
    },

    # HARD
    {
        "mode": "Logic",
        "difficulty": "Hard",
        "q": "2 fathers aur 2 sons fishing par gaye. Total 3 log the. Kaise?",
        "hint": "👨‍👦 Ek person dono roles ho sakta hai",
        "answers": ["grandfather father son", "grandfather, father, son"],
        "xp": 30,
    },
    {
        "mode": "Trick",
        "difficulty": "Hard",
        "q": "Ek room mein 10 candles hain. 3 bujh gayi. Kitni candles room mein hain?",
        "hint": "🕯️ Question carefully padho",
        "answers": ["10", "ten"],
        "xp": 30,
    },
    {
        "mode": "Pattern",
        "difficulty": "Hard",
        "q": "2, 6, 12, 20, 30, ?",
        "hint": "🔢 Har number ka pattern dekho",
        "answers": ["42"],
        "xp": 30,
    },
    {
        "mode": "Word",
        "difficulty": "Hard",
        "q": "Unscramble: R A E H T",
        "hint": "❤️ Body ke andar important organ",
        "answers": ["heart"],
        "xp": 30,
    },

    # EXTREME
    {
        "mode": "Logic",
        "difficulty": "Extreme",
        "q": "Aapke paas 3 switches hain aur doosre room mein 3 bulbs. Ek hi baar bulb room mein ja sakte ho. Kaise identify karoge?",
        "hint": "💡 Sirf light nahi, heat bhi clue hai",
        "answers": [
            "switch on wait switch off second on",
            "heat"
        ],
        "xp": 50,
    },
    {
        "mode": "Trick",
        "difficulty": "Extreme",
        "q": "Aisa kya hai jo jitna nikalte jao, utna bada hota jata hai?",
        "hint": "🕳️ Zameen se related",
        "answers": ["hole", "a hole", "gaddha", "pit"],
        "xp": 50,
    },
    {
        "mode": "Riddle",
        "difficulty": "Extreme",
        "q": "Main bolta nahi, phir bhi tumhari awaaz wapas deta hoon. Main kya hoon?",
        "hint": "⛰️ Mountains ke paas sunai de sakta hai",
        "answers": ["echo", "an echo"],
        "xp": 50,
    },
]

# =========================================================
# DATABASE
# =========================================================

conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS players(
    chat_id INTEGER,
    user_id INTEGER,
    name TEXT,
    xp INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    games INTEGER DEFAULT 0,
    hints INTEGER DEFAULT 0,
    achievements TEXT DEFAULT '',
    PRIMARY KEY(chat_id,user_id)
)
""")

conn.commit()

# chat_id -> current round
active = {}


# =========================================================
# HELPERS
# =========================================================

def normalize(text):
    text = text.lower().strip()
    text = " ".join(text.split())
    return text


def ensure_player(chat_id, user):
    cur.execute(
        """INSERT OR IGNORE INTO players(chat_id,user_id,name)
           VALUES(?,?,?)""",
        (chat_id, user.id, user.full_name),
    )
    cur.execute(
        "UPDATE players SET name=? WHERE chat_id=? AND user_id=?",
        (user.full_name, chat_id, user.id),
    )
    conn.commit()


def level_from_xp(xp):
    return xp // 100 + 1


def title_from_level(level):
    if level >= 25:
        return "👑 Legend"
    if level >= 15:
        return "🔥 Master"
    if level >= 10:
        return "🧠 Expert"
    if level >= 5:
        return "⚡ Solver"
    return "🌱 Rookie"


def difficulty_icon(difficulty):
    return {
        "Easy": "🟢",
        "Medium": "🟡",
        "Hard": "🔴",
        "Extreme": "🟣",
    }.get(difficulty, "⚪")


def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎮 Play", callback_data="menu:play"),
            InlineKeyboardButton("🎯 Modes", callback_data="menu:modes"),
        ],
        [
            InlineKeyboardButton("🏆 Leaderboard", callback_data="menu:leaderboard"),
            InlineKeyboardButton("👤 Profile", callback_data="menu:profile"),
        ],
        [
            InlineKeyboardButton("🎁 Daily Challenge", callback_data="menu:daily"),
            InlineKeyboardButton("🏅 Achievements", callback_data="menu:achievements"),
        ],
    ])


def mode_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎲 Random", callback_data="mode:Random"),
            InlineKeyboardButton("🧩 Word", callback_data="mode:Word"),
        ],
        [
            InlineKeyboardButton("🧠 Riddle", callback_data="mode:Riddle"),
            InlineKeyboardButton("🕵️ Logic", callback_data="mode:Logic"),
        ],
        [
            InlineKeyboardButton("😀 Emoji", callback_data="mode:Emoji"),
            InlineKeyboardButton("🔢 Pattern", callback_data="mode:Pattern"),
        ],
        [
            InlineKeyboardButton("😈 Trick", callback_data="mode:Trick"),
            InlineKeyboardButton("🐾 Animal", callback_data="mode:Animal"),
        ],
        [
            InlineKeyboardButton("🌆 City", callback_data="mode:City"),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="menu:home"),
        ],
    ])


def difficulty_menu(mode):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Easy", callback_data=f"diff:{mode}:Easy"),
            InlineKeyboardButton("🟡 Medium", callback_data=f"diff:{mode}:Medium"),
        ],
        [
            InlineKeyboardButton("🔴 Hard", callback_data=f"diff:{mode}:Hard"),
            InlineKeyboardButton("🟣 Extreme", callback_data=f"diff:{mode}:Extreme"),
        ],
        [
            InlineKeyboardButton("🎲 Any Difficulty", callback_data=f"diff:{mode}:Any"),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="menu:modes"),
        ],
    ])


def choose_question(mode="Random", difficulty="Any"):
    pool = QUESTIONS

    if mode != "Random":
        pool = [q for q in pool if q["mode"] == mode]

    if difficulty != "Any":
        pool = [q for q in pool if q["difficulty"] == difficulty]

    if not pool:
        pool = QUESTIONS

    return random.choice(pool)


# =========================================================
# START / HELP
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎮 <b>GUESSARENA</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🧠 Think fast. Guess smart.\n"
        "🏆 Beat your friends.\n\n"
        "Welcome to your puzzle arena! 🔥\n"
        "Choose an option below to begin."
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>HOW TO PLAY</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🎮 <b>Play</b> — Start a random puzzle\n"
        "🎯 <b>Modes</b> — Choose your puzzle type\n"
        "🟢 Easy → 🟣 Extreme\n\n"
        "💡 Hints help you solve difficult rounds.\n"
        "🔥 Consecutive wins increase your streak.\n"
        "⭐ Earn XP and level up.\n"
        "🏆 Compete with your group.\n\n"
        "💬 Answer by simply typing your answer."
    )

    await update.message.reply_text(text, parse_mode="HTML")


# =========================================================
# GAME
# =========================================================

async def start_game(update, context, mode="Random", difficulty="Any"):
    chat_id = update.effective_chat.id

    if chat_id in active:
        await update.effective_message.reply_text(
            "⚡ <b>Round already running!</b>\n\n"
            "🧩 Answer the current puzzle first.",
            parse_mode="HTML",
        )
        return

    q = choose_question(mode, difficulty)

    active[chat_id] = {
        "answers": [normalize(a) for a in q["answers"]],
        "hint": q["hint"],
        "xp": q["xp"],
        "mode": q["mode"],
        "difficulty": q["difficulty"],
    }

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💡 Hint",
                callback_data=f"hint:{chat_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Menu",
                callback_data="menu:home"
            )
        ],
    ])

    text = (
        "🎮 <b>GUESSARENA</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{difficulty_icon(q['difficulty'])} <b>{q['difficulty'].upper()} • {q['mode'].upper()}</b>\n\n"
        "🧩 <b>YOUR PUZZLE</b>\n"
        f"{q['q']}\n\n"
        f"🏆 Reward: <b>+{q['xp']} XP</b>\n"
        "💡 Need help? Use the Hint button.\n\n"
        "✍️ <b>Type your answer below!</b>"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_game(update, context)


# =========================================================
# ANSWER
# =========================================================

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    game_data = active.get(chat_id)

    if not game_data:
        return

    user = update.effective_user
    ensure_player(chat_id, user)

    guess = normalize(update.message.text)

    if guess not in game_data["answers"]:
        await update.message.reply_text(
            "❌ <b>Not quite!</b>\n"
            "Keep thinking... 🧠",
            parse_mode="HTML",
        )
        return

    active.pop(chat_id, None)

    cur.execute(
        """SELECT xp,wins,streak,best_streak,games,achievements
           FROM players WHERE chat_id=? AND user_id=?""",
        (chat_id, user.id),
    )

    row = cur.fetchone()
    old_xp, wins, streak, best_streak, games, achievements = row

    new_streak = streak + 1
    best_streak = max(best_streak, new_streak)
    reward = game_data["xp"]

    # Streak bonus
    bonus = 0
    if new_streak >= 3:
        bonus = 5
    if new_streak >= 5:
        bonus = 10

    total_reward = reward + bonus
    new_xp = old_xp + total_reward
    new_wins = wins + 1
    new_games = games + 1

    achievements_list = [x for x in achievements.split("|") if x]

    if new_wins >= 1 and "FIRST_WIN" not in achievements_list:
        achievements_list.append("FIRST_WIN")

    if new_wins >= 10 and "TEN_WINS" not in achievements_list:
        achievements_list.append("TEN_WINS")

    if best_streak >= 5 and "FIVE_STREAK" not in achievements_list:
        achievements_list.append("FIVE_STREAK")

    cur.execute(
        """UPDATE players
           SET xp=?,wins=?,streak=?,best_streak=?,games=?,achievements=?
           WHERE chat_id=? AND user_id=?""",
        (
            new_xp,
            new_wins,
            new_streak,
            best_streak,
            new_games,
            "|".join(achievements_list),
            chat_id,
            user.id,
        ),
    )

    conn.commit()

    level = level_from_xp(new_xp)

    bonus_text = ""
    if bonus:
        bonus_text = f"\n🔥 Streak bonus: <b>+{bonus} XP</b>"

    text = (
        "🎉 <b>CORRECT!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🥇 <b>{html.escape(user.full_name)}</b> got it first!\n\n"
        f"🏆 Puzzle XP: <b>+{reward}</b>"
        f"{bonus_text}\n"
        f"⭐ Total XP: <b>{new_xp}</b>\n"
        f"🔥 Streak: <b>{new_streak}</b>\n"
        f"📈 Level: <b>{level}</b>\n\n"
        "🎮 Ready for another round?"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Next Round", callback_data="menu:play")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="menu:leaderboard")],
    ])

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# =========================================================
# PROFILE
# =========================================================

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    ensure_player(chat_id, user)

    cur.execute(
        """SELECT xp,wins,streak,best_streak,games
           FROM players WHERE chat_id=? AND user_id=?""",
        (chat_id, user.id),
    )

    xp, wins, streak, best_streak, games = cur.fetchone()

    level = level_from_xp(xp)
    title = title_from_level(level)

    accuracy = 0
    if games:
        accuracy = round((wins / games) * 100)

    text = (
        "👤 <b>MY PROFILE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 {html.escape(user.full_name)}\n"
        f"{title} • Level {level}\n\n"
        f"⭐ XP: <b>{xp}</b>\n"
        f"🏆 Wins: <b>{wins}</b>\n"
        f"🎮 Games: <b>{games}</b>\n"
        f"🎯 Accuracy: <b>{accuracy}%</b>\n"
        f"🔥 Current streak: <b>{streak}</b>\n"
        f"💥 Best streak: <b>{best_streak}</b>"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
    )


# =========================================================
# LEADERBOARD
# =========================================================

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    cur.execute(
        """SELECT name,xp,wins FROM players
           WHERE chat_id=?
           ORDER BY xp DESC,wins DESC LIMIT 10""",
        (chat_id,),
    )

    rows = cur.fetchall()

    if not rows:
        await update.effective_message.reply_text(
            "🏆 <b>Leaderboard empty hai!</b>\n\n"
            "🎮 /game se first round start karo.",
            parse_mode="HTML",
        )
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = [
        "🏆 <b>GROUP LEADERBOARD</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for i, (name, xp, wins) in enumerate(rows, 1):
        medal = medals[i - 1] if i <= 3 else f"<b>{i}.</b>"
        lines.append(
            f"{medal} {html.escape(name)}\n"
            f"   ⭐ {xp} XP  •  🏆 {wins} wins"
        )

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# =========================================================
# ACHIEVEMENTS
# =========================================================

async def achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    ensure_player(chat_id, user)

    cur.execute(
        "SELECT achievements FROM players WHERE chat_id=? AND user_id=?",
        (chat_id, user.id),
    )

    data = cur.fetchone()[0]
    unlocked = [x for x in data.split("|") if x]

    names = {
        "FIRST_WIN": "🥇 First Blood — Win your first round",
        "TEN_WINS": "🏆 Rising Star — Win 10 rounds",
        "FIVE_STREAK": "🔥 On Fire — Reach a 5 streak",
    }

    lines = [
        "🏅 <b>ACHIEVEMENTS</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for key, description in names.items():
        if key in unlocked:
            lines.append(f"✅ {description}")
        else:
            lines.append(f"🔒 {description}")

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# =========================================================
# DAILY CHALLENGE
# =========================================================

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id in active:
        await update.effective_message.reply_text(
            "⚡ Pehle current round complete karo."
        )
        return

    # Same question for everyone on the same day
    index = int(
        hashlib.md5(str(date.today()).encode()).hexdigest(),
        16
    ) % len(QUESTIONS)

    q = QUESTIONS[index]

    active[chat_id] = {
        "answers": [normalize(a) for a in q["answers"]],
        "hint": q["hint"],
        "xp": q["xp"] + 10,
        "mode": q["mode"],
        "difficulty": q["difficulty"],
    }

    text = (
        "🎁 <b>DAILY CHALLENGE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🌟 One special puzzle for today!\n\n"
        f"{difficulty_icon(q['difficulty'])} {q['difficulty']}\n"
        f"🧩 <b>{q['q']}</b>\n\n"
        f"🏆 Reward: <b>+{q['xp'] + 10} XP</b>\n"
        "💡 One hint available."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 Hint", callback_data=f"hint:{chat_id}")],
        [InlineKeyboardButton("🏠 Menu", callback_data="menu:home")],
    ])

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# =========================================================
# BUTTONS
# =========================================================

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "menu:home":
        await query.message.reply_text(
            "🏠 <b>GUESSARENA HOME</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Choose your next move 👇",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        return

    if data == "menu:play":
        await start_game(update, context)
        return

    if data == "menu:modes":
        await query.message.reply_text(
            "🎯 <b>CHOOSE YOUR MODE</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Har mode mein alag type ka challenge hai.",
            parse_mode="HTML",
            reply_markup=mode_menu(),
        )
        return

    if data == "menu:profile":
        await profile(update, context)
        return

    if data == "menu:leaderboard":
        await leaderboard(update, context)
        return

    if data == "menu:achievements":
        await achievements(update, context)
        return

    if data == "menu:daily":
        await daily(update, context)
        return

    if data.startswith("mode:"):
        mode = data.split(":", 1)[1]

        await query.message.reply_text(
            f"🎯 <b>{mode.upper()} MODE</b>\n\n"
            "Difficulty choose karo 👇",
            parse_mode="HTML",
            reply_markup=difficulty_menu(mode),
        )
        return

    if data.startswith("diff:"):
        _, mode, difficulty = data.split(":")

        await start_game(
            update,
            context,
            mode=mode,
            difficulty=difficulty,
        )
        return

    if data.startswith("hint:"):
        chat_id = int(data.split(":")[1])
        game_data = active.get(chat_id)

        if not game_data:
            await query.answer(
                "Round already finished.",
                show_alert=True,
            )
            return

        await query.message.reply_text(
            f"💡 <b>HINT</b>\n\n{game_data['hint']}",
            parse_mode="HTML",
        )


# =========================================================
# MAIN
# =========================================================

def main():
    if not TOKEN:
        raise SystemExit(
            "BOT_TOKEN missing. Set it before running."
        )

    request = HTTPXRequest(read_timeout=60, write_timeout=60, connect_timeout=60, pool_timeout=60)
    app = Application.builder().token(TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("game", game))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("achievements", achievements))
    app.add_handler(CommandHandler("daily", daily))

    app.add_handler(CallbackQueryHandler(button))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            answer
        )
    )

    print("GuessArena 2.0 is running...")

    app.run_polling(
        poll_interval=1,
        timeout=60
    )


if __name__ == "__main__":
    main()
import threading
import http.server
import socketserver 

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()
