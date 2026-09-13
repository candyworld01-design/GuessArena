import os
import random
import sqlite3
import html
import hashlib
import re
import difflib
import threading
from datetime import date

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================================================
# GUESSARENA
# Stable Render + Telegram version
# =========================================================

TOKEN = os.environ.get("BOT_TOKEN")
DB = "guessarena.db"

# =========================================================
# RENDER HEALTH SERVER
# =========================================================

web_app = Flask(__name__)


@web_app.route("/")
def health_check():
    return "GuessArena Bot is Alive! 🎮", 200


def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )


# Start ONLY ONE web server.
# The old dummy TCP server is intentionally not started because
# it would try to bind the same PORT and can crash the deployment.
server_thread = threading.Thread(
    target=run_web_server,
    daemon=True,
)
server_thread.start()


# =========================================================
# QUESTION BANK
# =========================================================

QUESTIONS = [

    # =====================================================
    # WORD
    # =====================================================

    {
        "mode": "Word",
        "difficulty": "Easy",
        "q": "_ A _ A _",
        "hint": "🐼 Black & white animal",
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
        "mode": "Word",
        "difficulty": "Easy",
        "q": "C _ T",
        "hint": "🐱 Common pet",
        "answers": ["cat"],
        "xp": 10,
    },
    {
        "mode": "Word",
        "difficulty": "Easy",
        "q": "D _ G",
        "hint": "🐶 Loyal pet",
        "answers": ["dog"],
        "xp": 10,
    },
    {
        "mode": "Word",
        "difficulty": "Easy",
        "q": "S _ N",
        "hint": "☀️ Gives us light",
        "answers": ["sun"],
        "xp": 10,
    },
    {
        "mode": "Word",
        "difficulty": "Medium",
        "q": "B _ A _ T",
        "hint": "🚤 Moves on water",
        "answers": ["boat"],
        "xp": 20,
    },
    {
        "mode": "Word",
        "difficulty": "Medium",
        "q": "P _ O N E",
        "hint": "📱 You are probably holding one",
        "answers": ["phone", "mobile", "mobile phone"],
        "xp": 20,
    },
    {
        "mode": "Word",
        "difficulty": "Medium",
        "q": "S C _ O O L",
        "hint": "🎒 Students go here",
        "answers": ["school"],
        "xp": 20,
    },
    {
        "mode": "Word",
        "difficulty": "Hard",
        "q": "Unscramble: R A E H T",
        "hint": "❤️ Important organ",
        "answers": ["heart"],
        "xp": 30,
    },
    {
        "mode": "Word",
        "difficulty": "Hard",
        "q": "Unscramble: T R A E W",
        "hint": "💧 You drink it",
        "answers": ["water"],
        "xp": 30,
    },

    # =====================================================
    # ANIMAL
    # =====================================================

    {
        "mode": "Animal",
        "difficulty": "Easy",
        "q": "🐾 King of the jungle?",
        "hint": "🦁 Big cat",
        "answers": ["lion"],
        "xp": 10,
    },
    {
        "mode": "Animal",
        "difficulty": "Easy",
        "q": "🐘 Sabse bada land animal?",
        "hint": "🦣 Huge ears",
        "answers": ["elephant"],
        "xp": 10,
    },
    {
        "mode": "Animal",
        "difficulty": "Easy",
        "q": "🐄 Doodh dene wala common farm animal?",
        "hint": "🥛 Moo",
        "answers": ["cow", "cattle"],
        "xp": 10,
    },
    {
        "mode": "Animal",
        "difficulty": "Medium",
        "q": "🦒 Sabse lambi neck kis animal ki famous hai?",
        "hint": "🌳 Leaves khaata hai",
        "answers": ["giraffe"],
        "xp": 20,
    },
    {
        "mode": "Animal",
        "difficulty": "Medium",
        "q": "🐧 Ud nahi sakta, lekin bird hai?",
        "hint": "❄️ Cold regions",
        "answers": ["penguin"],
        "xp": 20,
    },
    {
        "mode": "Animal",
        "difficulty": "Hard",
        "q": "🐙 Teen hearts wala sea animal?",
        "hint": "🌊 Eight arms",
        "answers": ["octopus"],
        "xp": 30,
    },
    {
        "mode": "Animal",
        "difficulty": "Hard",
        "q": "🦇 Echolocation ke liye famous flying mammal?",
        "hint": "🌙 Raat mein active",
        "answers": ["bat"],
        "xp": 30,
    },
    {
        "mode": "Animal",
        "difficulty": "Extreme",
        "q": "🦈 Fish jaisa dikhta hai, lekin mammal hai. Kaun?",
        "hint": "🌊 Famous intelligent ocean mammal",
        "answers": ["dolphin", "whale"],
        "xp": 50,
    },

    # =====================================================
    # EMOJI
    # =====================================================

    {
        "mode": "Emoji",
        "difficulty": "Easy",
        "q": "🌧️ + ☂️ = ?",
        "hint": "🌂 Rain mein use hota hai",
        "answers": ["umbrella"],
        "xp": 10,
    },
    {
        "mode": "Emoji",
        "difficulty": "Easy",
        "q": "🍎 + 👨‍⚕️ = ?",
        "hint": "💡 Famous saying",
        "answers": ["doctor", "doctor away", "an apple a day"],
        "xp": 10,
    },
    {
        "mode": "Emoji",
        "difficulty": "Medium",
        "q": "🦁 + 👑 = ?",
        "hint": "🎬 Famous animated story",
        "answers": ["lion king", "the lion king"],
        "xp": 20,
    },
    {
        "mode": "Emoji",
        "difficulty": "Medium",
        "q": "🔥 + 🐦 = ?",
        "hint": "🐦 Mythical creature",
        "answers": ["phoenix", "firebird", "fire bird"],
        "xp": 20,
    },
    {
        "mode": "Emoji",
        "difficulty": "Hard",
        "q": "🕷️ + 👨 = ?",
        "hint": "🦸 Marvel character",
        "answers": ["spiderman", "spider man", "spider-man"],
        "xp": 30,
    },
    {
        "mode": "Emoji",
        "difficulty": "Hard",
        "q": "🧊 + 👑 = ?",
        "hint": "❄️ Disney character",
        "answers": ["elsa", "frozen"],
        "xp": 30,
    },

    # =====================================================
    # RIDDLE
    # =====================================================

    {
        "mode": "Riddle",
        "difficulty": "Easy",
        "q": "I have hands but cannot clap. What am I?",
        "hint": "⏰ Time",
        "answers": ["clock", "a clock"],
        "xp": 10,
    },
    {
        "mode": "Riddle",
        "difficulty": "Easy",
        "q": "What has a face and two hands but no arms or legs?",
        "hint": "⏰ Time",
        "answers": ["clock", "watch", "a clock", "a watch"],
        "xp": 10,
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
        "answers": ["piano", "a piano", "keyboard", "computer keyboard"],
        "xp": 20,
    },
    {
        "mode": "Riddle",
        "difficulty": "Medium",
        "q": "Jitna zyada dry karta hoon, utna hi wet hota hoon. Main kya hoon?",
        "hint": "🛁 Bathroom",
        "answers": ["towel", "a towel"],
        "xp": 20,
    },
    {
        "mode": "Riddle",
        "difficulty": "Hard",
        "q": "Main bolta nahi, phir bhi tumhari awaaz wapas deta hoon.",
        "hint": "⛰️ Mountains ke paas sunai de sakta hai",
        "answers": ["echo", "an echo"],
        "xp": 30,
    },
    {
        "mode": "Riddle",
        "difficulty": "Hard",
        "q": "What gets wetter as it dries?",
        "hint": "🛁 You probably use it after a shower",
        "answers": ["towel"],
        "xp": 30,
    },
    {
        "mode": "Riddle",
        "difficulty": "Extreme",
        "q": "What can travel around the world while staying in one corner?",
        "hint": "✉️ Think about a letter",
        "answers": ["stamp", "a stamp"],
        "xp": 50,
    },

    # =====================================================
    # LOGIC
    # =====================================================

    {
        "mode": "Logic",
        "difficulty": "Easy",
        "q": "2 + 2 × 2 = ?",
        "hint": "🧠 BODMAS yaad hai?",
        "answers": ["6"],
        "xp": 10,
    },
    {
        "mode": "Logic",
        "difficulty": "Medium",
        "q": "2 fathers aur 2 sons fishing par gaye. Total 3 log the. Kaise?",
        "hint": "👴👨👦 Ek person dono roles ho sakta hai",
        "answers": [
            "grandfather father son",
            "grandfather father and son",
            "grandfather father son trio",
        ],
        "xp": 20,
    },
    {
        "mode": "Logic",
        "difficulty": "Medium",
        "q": "A room has 4 corners. Har corner mein ek cat hai. Total cats kitni?",
        "hint": "🐱 Har corner mein ek",
        "answers": ["4", "four"],
        "xp": 20,
    },
    {
        "mode": "Logic",
        "difficulty": "Hard",
        "q": "Ek aadmi ke paas 17 sheep thi. All but 9 ran away. Kitni bachi?",
        "hint": "🔎 'All but 9' carefully padho",
        "answers": ["9", "nine"],
        "xp": 30,
    },
    {
        "mode": "Logic",
        "difficulty": "Hard",
        "q": "Aapke paas 3 switches hain aur doosre room mein 3 bulbs. Ek hi baar bulb room mein ja sakte ho. Kaise identify karoge?",
        "hint": "💡 Light ke saath heat bhi clue hai",
        "answers": [
            "one on wait off second on",
            "heat",
            "use heat",
            "switch on wait switch off",
        ],
        "xp": 30,
    },
    {
        "mode": "Logic",
        "difficulty": "Extreme",
        "q": "Ek farmer ke paas 3 apples hain. Tum 2 le lete ho. Tumhare paas kitne apples?",
        "hint": "🍎 Jo tumne liye...",
        "answers": ["2", "two"],
        "xp": 50,
    },

    # =====================================================
    # PATTERN
    # =====================================================

    {
        "mode": "Pattern",
        "difficulty": "Easy",
        "q": "2, 4, 6, 8, ?",
        "hint": "➕ Same jump",
        "answers": ["10", "ten"],
        "xp": 10,
    },
    {
        "mode": "Pattern",
        "difficulty": "Easy",
        "q": "5, 10, 15, 20, ?",
        "hint": "🔢 +5",
        "answers": ["25"],
        "xp": 10,
    },
    {
        "mode": "Pattern",
        "difficulty": "Medium",
        "q": "3, 6, 12, 24, ?",
        "hint": "✖️ Same multiplier",
        "answers": ["48"],
        "xp": 20,
    },
    {
        "mode": "Pattern",
        "difficulty": "Medium",
        "q": "1, 4, 9, 16, ?",
        "hint": "🔢 Square numbers",
        "answers": ["25"],
        "xp": 20,
    },
    {
        "mode": "Pattern",
        "difficulty": "Hard",
        "q": "2, 6, 12, 20, 30, ?",
        "hint": "🔢 Differences dekho",
        "answers": ["42"],
        "xp": 30,
    },
    {
        "mode": "Pattern",
        "difficulty": "Hard",
        "q": "1, 1, 2, 3, 5, 8, ?",
        "hint": "🧠 Previous two numbers",
        "answers": ["13"],
        "xp": 30,
    },
    {
        "mode": "Pattern",
        "difficulty": "Extreme",
        "q": "2, 3, 5, 9, 17, ?",
        "hint": "🔢 Differences/multiplier mix",
        "answers": ["33"],
        "xp": 50,
    },

    # =====================================================
    # TRICK
    # =====================================================

    {
        "mode": "Trick",
        "difficulty": "Easy",
        "q": "What has many teeth but cannot bite?",
        "hint": "💇 Hair ke saath use hota hai",
        "answers": ["comb", "a comb"],
        "xp": 10,
    },
    {
        "mode": "Trick",
        "difficulty": "Medium",
        "q": "Ek room mein 10 candles hain. 3 bujh gayi. Kitni candles room mein hain?",
        "hint": "🕯️ Question carefully padho",
        "answers": ["10", "ten"],
        "xp": 20,
    },
    {
        "mode": "Trick",
        "difficulty": "Medium",
        "q": "What month has 28 days?",
        "hint": "📅 Sirf February mat sochna",
        "answers": [
            "all",
            "all months",
            "every month",
            "every month has 28 days",
        ],
        "xp": 20,
    },
    {
        "mode": "Trick",
        "difficulty": "Hard",
        "q": "Aisa kya hai jo jitna nikalte jao, utna bada hota jata hai?",
        "hint": "🕳️ Zameen se related",
        "answers": ["hole", "a hole", "gaddha", "pit"],
        "xp": 30,
    },
    {
        "mode": "Trick",
        "difficulty": "Hard",
        "q": "Before Mount Everest was discovered, what was the highest mountain?",
        "hint": "⛰️ Everest tab bhi exist karta tha",
        "answers": [
            "mount everest",
            "everest",
        ],
        "xp": 30,
    },
    {
        "mode": "Trick",
        "difficulty": "Extreme",
        "q": "If you overtake the person in second place, what place are you in?",
        "hint": "🏃 Position carefully",
        "answers": ["second", "second place", "2nd"],
        "xp": 50,
    },

    # =====================================================
    # CITY
    # =====================================================

    {
        "mode": "City",
        "difficulty": "Easy",
        "q": "🕌 Taj Mahal kis city mein hai?",
        "hint": "🇮🇳 Uttar Pradesh",
        "answers": ["agra"],
        "xp": 10,
    },
    {
        "mode": "City",
        "difficulty": "Easy",
        "q": "🌆 Gateway of India kis city mein hai?",
        "hint": "🇮🇳 West coast",
        "answers": ["mumbai", "bombay"],
        "xp": 10,
    },
    {
        "mode": "City",
        "difficulty": "Medium",
        "q": "🗼 Eiffel Tower kis city mein hai?",
        "hint": "🇫🇷 France",
        "answers": ["paris"],
        "xp": 20,
    },
    {
        "mode": "City",
        "difficulty": "Medium",
        "q": "🗽 Statue of Liberty kis city mein hai?",
        "hint": "🇺🇸 New York",
        "answers": ["new york", "new york city", "nyc"],
        "xp": 20,
    },
    {
        "mode": "City",
        "difficulty": "Medium",
        "q": "🏰 India Gate kis city mein hai?",
        "hint": "🇮🇳 Capital city",
        "answers": ["delhi", "new delhi"],
        "xp": 20,
    },
    {
        "mode": "City",
        "difficulty": "Hard",
        "q": "🏛️ Charminar kis Indian city mein hai?",
        "hint": "💎 Telangana",
        "answers": ["hyderabad"],
        "xp": 30,
    },
    {
        "mode": "City",
        "difficulty": "Hard",
        "q": "🌊 Marine Drive kis city mein famous hai?",
        "hint": "🌆 Maharashtra",
        "answers": ["mumbai", "bombay"],
        "xp": 30,
    },
    {
        "mode": "City",
        "difficulty": "Extreme",
        "q": "🏯 Red Fort kis city mein hai?",
        "hint": "🇮🇳 Historic capital",
        "answers": ["delhi", "new delhi"],
        "xp": 50,
    },

    # =====================================================
    # BONUS MIXED QUESTIONS
    # =====================================================

    {
        "mode": "Riddle",
        "difficulty": "Extreme",
        "q": "I am always in front of you but can never be seen. What am I?",
        "hint": "🔮 Time se related",
        "answers": ["future", "the future"],
        "xp": 50,
    },
    {
        "mode": "Logic",
        "difficulty": "Extreme",
        "q": "You have one match and enter a dark room with a candle, lamp and fireplace. What do you light first?",
        "hint": "🔥 First step obvious hai",
        "answers": ["match", "the match", "matchstick"],
        "xp": 50,
    },
    {
        "mode": "Trick",
        "difficulty": "Extreme",
        "q": "What comes once in a minute, twice in a moment, but never in a thousand years?",
        "hint": "🔤 Letters",
        "answers": ["m", "letter m"],
        "xp": 50,
    },
]


# =========================================================
# DATABASE
# =========================================================

db_lock = threading.Lock()

conn = sqlite3.connect(
    DB,
    check_same_thread=False,
)

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


# =========================================================
# ACTIVE GAME STATE
# =========================================================

# One active race per Telegram chat.
active = {}

# Recently used question IDs per chat.
history = {}


# =========================================================
# HELPERS
# =========================================================

def normalize(text):
    if not text:
        return ""

    text = html.unescape(str(text))
    text = text.lower()

    # Common punctuation removal
    text = re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE)

    text = text.replace("-", " ")
    text = " ".join(text.split())

    return text.strip()


def answer_matches(guess, answers):
    """
    Human-friendly matching.

    Exact aliases always work.
    Small spelling mistakes can work for longer answers,
    but very short answers are kept strict to avoid accidental wins.
    """

    guess = normalize(guess)

    if not guess:
        return False

    normalized_answers = [
        normalize(a)
        for a in answers
        if normalize(a)
    ]

    # Exact match
    if guess in normalized_answers:
        return True

    # Don't fuzzy-match tiny answers.
    if len(guess) < 4:
        return False

    # Very small spelling mistakes.
    for answer in normalized_answers:
        if len(answer) < 4:
            continue

        ratio = difflib.SequenceMatcher(
            None,
            guess,
            answer,
        ).ratio()

        if ratio >= 0.92:
            return True

    return False


def ensure_player(chat_id, user):
    with db_lock:
        cur.execute(
            """
            INSERT OR IGNORE INTO players
            (chat_id,user_id,name)
            VALUES(?,?,?)
            """,
            (
                chat_id,
                user.id,
                user.full_name,
            ),
        )

        cur.execute(
            """
            UPDATE players
            SET name=?
            WHERE chat_id=? AND user_id=?
            """,
            (
                user.full_name,
                chat_id,
                user.id,
            ),
        )

        conn.commit()


def level_from_xp(xp):
    return (xp // 100) + 1


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
            InlineKeyboardButton(
                "🎮 Play",
                callback_data="menu:play",
            ),
            InlineKeyboardButton(
                "🎯 Modes",
                callback_data="menu:modes",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏆 Leaderboard",
                callback_data="menu:leaderboard",
            ),
            InlineKeyboardButton(
                "👤 Profile",
                callback_data="menu:profile",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎁 Daily Challenge",
                callback_data="menu:daily",
            ),
            InlineKeyboardButton(
                "🏅 Achievements",
                callback_data="menu:achievements",
            ),
        ],
    ])


def mode_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎲 Random",
                callback_data="mode:Random",
            ),
            InlineKeyboardButton(
                "🧩 Word",
                callback_data="mode:Word",
            ),
        ],
        [
            InlineKeyboardButton(
                "🧠 Riddle",
                callback_data="mode:Riddle",
            ),
            InlineKeyboardButton(
                "🕵️ Logic",
                callback_data="mode:Logic",
            ),
        ],
        [
            InlineKeyboardButton(
                "😀 Emoji",
                callback_data="mode:Emoji",
            ),
            InlineKeyboardButton(
                "🔢 Pattern",
                callback_data="mode:Pattern",
            ),
        ],
        [
            InlineKeyboardButton(
                "😈 Trick",
                callback_data="mode:Trick",
            ),
            InlineKeyboardButton(
                "🐾 Animal",
                callback_data="mode:Animal",
            ),
        ],
        [
            InlineKeyboardButton(
                "🌆 City",
                callback_data="mode:City",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔙 Home",
                callback_data="menu:home",
            ),
        ],
    ])


def difficulty_menu(mode):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢 Easy",
                callback_data=f"diff:{mode}:Easy",
            ),
            InlineKeyboardButton(
                "🟡 Medium",
                callback_data=f"diff:{mode}:Medium",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔴 Hard",
                callback_data=f"diff:{mode}:Hard",
            ),
            InlineKeyboardButton(
                "🟣 Extreme",
                callback_data=f"diff:{mode}:Extreme",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎲 Any Difficulty",
                callback_data=f"diff:{mode}:Any",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="menu:modes",
            ),
        ],
    ])


def choose_question(mode="Random", difficulty="Any", chat_id=None):
    pool = QUESTIONS

    if mode != "Random":
        pool = [
            q for q in pool
            if q["mode"] == mode
        ]

    if difficulty != "Any":
        pool = [
            q for q in pool
            if q["difficulty"] == difficulty
        ]

    if not pool:
        pool = QUESTIONS

    # Avoid immediate repeats where possible.
    if chat_id is not None:
        used = history.setdefault(chat_id, [])

        available = [
            q for q in pool
            if id(q) not in used
        ]

        if available:
            pool = available

        selected = random.choice(pool)

        used.append(id(selected))

        # Keep memory small.
        if len(used) > min(40, len(QUESTIONS)):
            del used[:-min(40, len(QUESTIONS))]

        return selected

    return random.choice(pool)


def clear_game(chat_id):
    active.pop(chat_id, None)


# =========================================================
# START / HELP
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    ensure_player(chat_id, user)

    text = (
        "🎮 <b>GUESSARENA</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🧠 Think fast. Guess smart.\n"
        "😂 Galat hua toh dimaag ko blame mat karna.\n"
        "🏆 Sahi hua toh credit lena allowed hai.\n\n"
        "🔥 Welcome to the Arena!\n"
        "Choose your battlefield 👇"
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
        "🎮 <b>Play</b> — Random challenge\n"
        "🎯 <b>Modes</b> — Choose your category\n"
        "🟢 Easy → 🟣 Extreme\n\n"
        "✍️ Answer simply by typing.\n"
        "💡 Hint button clue dega.\n"
        "🔥 Consecutive wins = streak bonus.\n"
        "⭐ XP se level up.\n"
        "🏆 Group mein fastest solver wins.\n\n"
        "⚡ Commands:\n"
        "/game — Start game\n"
        "/profile — Your stats\n"
        "/leaderboard — Group ranking\n"
        "/daily — Daily challenge\n"
        "/achievements — Badges\n"
        "/stop — Current round stop"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


# =========================================================
# GAME START
# =========================================================

async def start_game(
    update,
    context,
    mode="Random",
    difficulty="Any",
):
    chat_id = update.effective_chat.id

    if chat_id in active:
        await update.effective_message.reply_text(
            "⚡ <b>ROUND ALREADY RUNNING!</b>\n\n"
            "🧩 Pehle current puzzle solve karo.\n"
            "😈 Bhaag ke next question par nahi ja sakte.",
            parse_mode="HTML",
        )
        return

    q = choose_question(
        mode,
        difficulty,
        chat_id,
    )

    active[chat_id] = {
        "answers": q["answers"],
        "hint": q["hint"],
        "xp": q["xp"],
        "mode": q["mode"],
        "difficulty": q["difficulty"],
        "question": q["q"],
        "started_by": None,
    }

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💡 Hint",
                callback_data=f"hint:{chat_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "🛑 Stop Round",
                callback_data=f"stop:{chat_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 Menu",
                callback_data="menu:home",
            ),
        ],
    ])

    text = (
        "🎮 <b>GUESSARENA</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{difficulty_icon(q['difficulty'])} "
        f"<b>{q['difficulty'].upper()} • {q['mode'].upper()}</b>\n\n"
        "🧩 <b>YOUR PUZZLE</b>\n"
        f"{q['q']}\n\n"
        f"🏆 Reward: <b>+{q['xp']} XP</b>\n"
        "💡 Need help? Hint available.\n\n"
        "✍️ <b>TYPE YOUR ANSWER!</b>\n"
        "⚡ First correct answer wins."
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_game(update, context)


# =========================================================
# STOP
# =========================================================

async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in active:
        await update.effective_message.reply_text(
            "😴 Koi active round nahi hai."
        )
        return

    clear_game(chat_id)

    await update.effective_message.reply_text(
        "🛑 <b>ROUND STOPPED</b>\n\n"
        "😈 Puzzle bach gaya.\n"
        "🎮 Jab ready ho /game dabao.",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# =========================================================
# ANSWER
# =========================================================

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not update.message.text:
        return

    chat_id = update.effective_chat.id
    game_data = active.get(chat_id)

    if not game_data:
        return

    user = update.effective_user

    ensure_player(chat_id, user)

    guess = update.message.text

    if not answer_matches(
        guess,
        game_data["answers"],
    ):
        await update.message.reply_text(
            "❌ <b>Nope!</b>\n"
            "🧠 Dimaag ko thoda aur load do 😂",
            parse_mode="HTML",
        )
        return

    # Remove immediately so two simultaneous correct
    # messages cannot both win.
    active.pop(chat_id, None)

    with db_lock:
        cur.execute(
            """
            SELECT xp,wins,streak,best_streak,
                   games,achievements
            FROM players
            WHERE chat_id=? AND user_id=?
            """,
            (
                chat_id,
                user.id,
            ),
        )

        row = cur.fetchone()

        if not row:
            ensure_player(chat_id, user)

            cur.execute(
                """
                SELECT xp,wins,streak,best_streak,
                       games,achievements
                FROM players
                WHERE chat_id=? AND user_id=?
                """,
                (
                    chat_id,
                    user.id,
                ),
            )

            row = cur.fetchone()

        (
            old_xp,
            wins,
            streak,
            best_streak,
            games,
            achievements,
        ) = row

        new_streak = streak + 1
        new_best = max(
            best_streak,
            new_streak,
        )

        reward = game_data["xp"]

        bonus = 0

        if new_streak >= 3:
            bonus += 5

        if new_streak >= 5:
            bonus += 5

        if new_streak >= 10:
            bonus += 10

        total_reward = reward + bonus

        new_xp = old_xp + total_reward
        new_wins = wins + 1
        new_games = games + 1

        achievements_list = [
            x
            for x in achievements.split("|")
            if x
        ]

        if (
            new_wins >= 1
            and "FIRST_WIN" not in achievements_list
        ):
            achievements_list.append(
                "FIRST_WIN"
            )

        if (
            new_wins >= 10
            and "TEN_WINS" not in achievements_list
        ):
            achievements_list.append(
                "TEN_WINS"
            )

        if (
            new_best >= 5
            and "FIVE_STREAK" not in achievements_list
        ):
            achievements_list.append(
                "FIVE_STREAK"
            )

        if (
            new_best >= 10
            and "TEN_STREAK" not in achievements_list
        ):
            achievements_list.append(
                "TEN_STREAK"
            )

        cur.execute(
            """
            UPDATE players
            SET xp=?,
                wins=?,
                streak=?,
                best_streak=?,
                games=?,
                achievements=?
            WHERE chat_id=? AND user_id=?
            """,
            (
                new_xp,
                new_wins,
                new_streak,
                new_best,
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
        bonus_text = (
            f"\n🔥 Streak bonus: "
            f"<b>+{bonus} XP</b>"
        )

    escaped_name = html.escape(
        user.full_name
    )

    text = (
        "🎉 <b>CORRECT!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🥇 <b>{escaped_name}</b> "
        "got it first!\n\n"
        f"🏆 Puzzle XP: <b>+{reward}</b>"
        f"{bonus_text}\n"
        f"⭐ Total XP: <b>{new_xp}</b>\n"
        f"🔥 Streak: <b>{new_streak}</b>\n"
        f"📈 Level: <b>{level}</b>\n\n"
        "😂 Baaki sab: better luck next time.\n"
        "🎮 Next round?"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔥 NEXT ROUND",
                callback_data="menu:play",
            )
        ],
        [
            InlineKeyboardButton(
                "🎯 Change Mode",
                callback_data="menu:modes",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏆 Leaderboard",
                callback_data="menu:leaderboard",
            ),
        ],
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

    with db_lock:
        cur.execute(
            """
            SELECT xp,wins,streak,best_streak,games
            FROM players
            WHERE chat_id=? AND user_id=?
            """,
            (
                chat_id,
                user.id,
            ),
        )

        row = cur.fetchone()

    if not row:
        return

    (
        xp,
        wins,
        streak,
        best_streak,
        games,
    ) = row

    level = level_from_xp(xp)
    title = title_from_level(level)

    accuracy = 0

    if games:
        accuracy = round(
            (wins / games) * 100
        )

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
        f"💥 Best streak: <b>{best_streak}</b>\n\n"
        f"📊 XP to next level: "
        f"<b>{100 - (xp % 100)}</b>"
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

    with db_lock:
        cur.execute(
            """
            SELECT name,xp,wins
            FROM players
            WHERE chat_id=?
            ORDER BY xp DESC,wins DESC
            LIMIT 10
            """,
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

    medals = [
        "🥇",
        "🥈",
        "🥉",
    ]

    lines = [
        "🏆 <b>GROUP LEADERBOARD</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for i, (
        name,
        xp,
        wins,
    ) in enumerate(rows, 1):

        medal = (
            medals[i - 1]
            if i <= 3
            else f"<b>{i}.</b>"
        )

        lines.append(
            f"{medal} "
            f"{html.escape(name)}\n"
            f"   ⭐ {xp} XP"
            f"  •  🏆 {wins} wins"
        )

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# =========================================================
# ACHIEVEMENTS
# =========================================================

async def achievements(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    chat_id = update.effective_chat.id
    user = update.effective_user

    ensure_player(chat_id, user)

    with db_lock:
        cur.execute(
            """
            SELECT achievements
            FROM players
            WHERE chat_id=? AND user_id=?
            """,
            (
                chat_id,
                user.id,
            ),
        )

        row = cur.fetchone()

    data = row[0] if row else ""

    unlocked = [
        x
        for x in data.split("|")
        if x
    ]

    names = {
        "FIRST_WIN":
            "🥇 First Blood — First win",

        "TEN_WINS":
            "🏆 Rising Star — 10 wins",

        "FIVE_STREAK":
            "🔥 On Fire — 5 streak",

        "TEN_STREAK":
            "💀 Unstoppable — 10 streak",
    }

    lines = [
        "🏅 <b>ACHIEVEMENTS</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for key, description in names.items():

        if key in unlocked:
            lines.append(
                f"✅ {description}"
            )
        else:
            lines.append(
                f"🔒 {description}"
            )

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# =========================================================
# DAILY CHALLENGE
# =========================================================

async def daily(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    chat_id = update.effective_chat.id

    if chat_id in active:
        await update.effective_message.reply_text(
            "⚡ Pehle current round complete karo."
        )
        return

    # Same puzzle for everyone on the same day.
    index = int(
        hashlib.md5(
            str(date.today()).encode()
        ).hexdigest(),
        16,
    ) % len(QUESTIONS)

    q = QUESTIONS[index]

    active[chat_id] = {
        "answers": q["answers"],
        "hint": q["hint"],
        "xp": q["xp"] + 10,
        "mode": q["mode"],
        "difficulty": q["difficulty"],
        "question": q["q"],
        "started_by": None,
    }

    text = (
        "🎁 <b>DAILY CHALLENGE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🌟 One special puzzle for today!\n\n"
        f"{difficulty_icon(q['difficulty'])} "
        f"<b>{q['difficulty']}</b>\n\n"
        f"🧩 {q['q']}\n\n"
        f"🏆 Reward: <b>+{q['xp'] + 10} XP</b>\n"
        "💡 One hint available.\n\n"
        "⚡ First correct answer wins."
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💡 Hint",
                callback_data=f"hint:{chat_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "🛑 Stop",
                callback_data=f"stop:{chat_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Menu",
                callback_data="menu:home",
            )
        ],
    ])

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# =========================================================
# BUTTON HANDLER
# =========================================================

async def button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    try:
        await query.answer()
    except Exception:
        pass

    data = query.data or ""

    # -----------------------------------------------------
    # HOME
    # -----------------------------------------------------

    if data == "menu:home":

        await query.message.reply_text(
            "🏠 <b>GUESSARENA HOME</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔥 Choose your next move 👇",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        return

    # -----------------------------------------------------
    # PLAY
    # -----------------------------------------------------

    if data == "menu:play":

        await start_game(
            update,
            context,
        )
        return

    # -----------------------------------------------------
    # MODES
    # -----------------------------------------------------

    if data == "menu:modes":

        await query.message.reply_text(
            "🎯 <b>CHOOSE YOUR MODE</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "😂 Har mode mein alag dimaag ki vaat hai.",
            parse_mode="HTML",
            reply_markup=mode_menu(),
        )
        return

    # -----------------------------------------------------
    # PROFILE
    # -----------------------------------------------------

    if data == "menu:profile":

        await profile(
            update,
            context,
        )
        return

    # -----------------------------------------------------
    # LEADERBOARD
    # -----------------------------------------------------

    if data == "menu:leaderboard":

        await leaderboard(
            update,
            context,
        )
        return

    # -----------------------------------------------------
    # ACHIEVEMENTS
    # -----------------------------------------------------

    if data == "menu:achievements":

        await achievements(
            update,
            context,
        )
        return

    # -----------------------------------------------------
    # DAILY
    # -----------------------------------------------------

    if data == "menu:daily":

        await daily(
            update,
            context,
        )
        return

    # -----------------------------------------------------
    # MODE
    # -----------------------------------------------------

    if data.startswith("mode:"):

        mode = data.split(
            ":",
            1,
        )[1]

        await query.message.reply_text(
            f"🎯 <b>{mode.upper()} MODE</b>\n\n"
            "Difficulty choose karo 👇",
            parse_mode="HTML",
            reply_markup=difficulty_menu(mode),
        )
        return

    # -----------------------------------------------------
    # DIFFICULTY
    # -----------------------------------------------------

    if data.startswith("diff:"):

        parts = data.split(":")

        if len(parts) != 3:
            return

        _, mode, difficulty = parts

        await start_game(
            update,
            context,
            mode=mode,
            difficulty=difficulty,
        )
        return

    # -----------------------------------------------------
    # HINT
    # -----------------------------------------------------

    if data.startswith("hint:"):

        try:
            chat_id = int(
                data.split(":")[1]
            )
        except Exception:
            return

        game_data = active.get(chat_id)

        if not game_data:

            try:
                await query.answer(
                    "Round already finished.",
                    show_alert=True,
                )
            except Exception:
                pass

            return

        await query.message.reply_text(
            "💡 <b>HINT</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{game_data['hint']}",
            parse_mode="HTML",
        )
        return

    # -----------------------------------------------------
    # STOP BUTTON
    # -----------------------------------------------------

    if data.startswith("stop:"):

        try:
            chat_id = int(
                data.split(":")[1]
            )
        except Exception:
            return

        if chat_id in active:

            clear_game(chat_id)

            await query.message.reply_text(
                "🛑 <b>ROUND STOPPED</b>\n\n"
                "🎮 New round ke liye Play dabao.",
                parse_mode="HTML",
                reply_markup=main_menu(),
            )
        else:

            try:
                await query.answer(
                    "No active round.",
                    show_alert=True,
                )
            except Exception:
                pass

        return


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update,
    context,
):
    print(
        "GuessArena error:",
        repr(context.error),
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not TOKEN:
        raise SystemExit(
            "BOT_TOKEN missing. "
            "Set BOT_TOKEN in Render Environment Variables."
        )

    request = HTTPXRequest(
        read_timeout=60,
        write_timeout=60,
        connect_timeout=60,
        pool_timeout=60,
    )

    application = (
        Application
        .builder()
        .token(TOKEN)
        .request(request)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_cmd,
        )
    )

    application.add_handler(
        CommandHandler(
            "game",
            game,
        )
    )

    application.add_handler(
        CommandHandler(
            "profile",
            profile,
        )
    )

    application.add_handler(
        CommandHandler(
            "leaderboard",
            leaderboard,
        )
    )

    application.add_handler(
        CommandHandler(
            "achievements",
            achievements,
        )
    )

    application.add_handler(
        CommandHandler(
            "daily",
            daily,
        )
    )

    application.add_handler(
        CommandHandler(
            "stop",
            stop_game,
        )
    )

    # Buttons
    application.add_handler(
        CallbackQueryHandler(
            button,
        )
    )

    # Normal answers
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            answer,
        )
    )

    application.add_error_handler(
        error_handler
    )

    print(
        "================================="
    )
    print(
        "GuessArena is running..."
    )
    print(
        f"Questions: {len(QUESTIONS)}"
    )
    print(
        "Render health server: ON"
    )
    print(
        "Telegram polling: ON"
    )
    print(
        "================================="
    )

    application.run_polling(
        poll_interval=1,
        timeout=60,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
