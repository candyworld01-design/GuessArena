# ============================================================
# GUESSARENA 2.0
# Complete fresh bot_v2.py
# ============================================================

import os
import random
import sqlite3
import html
import asyncio
from threading import Thread
from datetime import date

from flask import Flask

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.request import HTTPXRequest

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# ============================================================
# RENDER HEALTH SERVER
# DO NOT CHANGE
# ============================================================

app = Flask(__name__)


@app.route("/")
def health_check():
    return "Bot is Alive!", 200


def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )


server_thread = Thread(
    target=run_web_server,
    daemon=True,
)

server_thread.start()


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.environ.get("BOT_TOKEN")

DB_FILE = "guessarena.db"

PANIC_TIME = 5


# ============================================================
# DATABASE
# ============================================================

conn = sqlite3.connect(
    DB_FILE,
    check_same_thread=False,
)

cur = conn.cursor()

cur.execute(
    """
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
    """
)

conn.commit()


# ============================================================
# ACTIVE GAMES
# ============================================================

active = {}


# ============================================================
# QUESTION BANK
# ============================================================

QUESTIONS = [

    # ========================================================
    # WORD
    # ========================================================

    {
        "mode": "Word",
        "difficulty": "Easy",
        "q": "Opposite of HOT?",
        "hint": "Winter wala feeling ❄️",
        "answers": ["cold"],
        "xp": 10,
    },
    {
        "mode": "Word",
        "difficulty": "Easy",
        "q": "Opposite of BIG?",
        "hint": "Small",
        "answers": ["small", "little"],
        "xp": 10,
    },
    {
        "mode": "Word",
        "difficulty": "Medium",
        "q": "A person who writes books is called?",
        "hint": "Book banane wala ✍️",
        "answers": ["author", "writer"],
        "xp": 20,
    },
    {
        "mode": "Word",
        "difficulty": "Medium",
        "q": "What do we call a word with the opposite meaning?",
        "hint": "Example: hot/cold",
        "answers": ["antonym"],
        "xp": 20,
    },
    {
        "mode": "Word",
        "difficulty": "Hard",
        "q": "What is the fear of heights called?",
        "hint": "Starts with Acro...",
        "answers": ["acrophobia"],
        "xp": 30,
    },
    {
        "mode": "Word",
        "difficulty": "Hard",
        "q": "What is a word that reads the same backward called?",
        "hint": "madam",
        "answers": ["palindrome"],
        "xp": 30,
    },
    {
        "mode": "Word",
        "difficulty": "Extreme",
        "q": "What is the study of word origins called?",
        "hint": "Language history",
        "answers": ["etymology"],
        "xp": 50,
    },


    # ========================================================
    # ANIMAL
    # ========================================================

    {
        "mode": "Animal",
        "difficulty": "Easy",
        "q": "Which animal is known as the King of the Jungle?",
        "hint": "Big cat 🦁",
        "answers": ["lion"],
        "xp": 10,
    },
    {
        "mode": "Animal",
        "difficulty": "Easy",
        "q": "Which animal says MEOW?",
        "hint": "🐱",
        "answers": ["cat"],
        "xp": 10,
    },
    {
        "mode": "Animal",
        "difficulty": "Medium",
        "q": "Which is the largest land animal?",
        "hint": "Has a trunk",
        "answers": ["elephant"],
        "xp": 20,
    },
    {
        "mode": "Animal",
        "difficulty": "Medium",
        "q": "Which animal is famous for changing its skin color?",
        "hint": "🦎",
        "answers": ["chameleon"],
        "xp": 20,
    },
    {
        "mode": "Animal",
        "difficulty": "Hard",
        "q": "Which mammal can truly fly?",
        "hint": "Not a bird 🦇",
        "answers": ["bat"],
        "xp": 30,
    },
    {
        "mode": "Animal",
        "difficulty": "Hard",
        "q": "What is the fastest land animal?",
        "hint": "Spotted big cat",
        "answers": ["cheetah"],
        "xp": 30,
    },
    {
        "mode": "Animal",
        "difficulty": "Extreme",
        "q": "Which animal has three hearts?",
        "hint": "Ocean creature 🐙",
        "answers": ["octopus"],
        "xp": 50,
    },


    # ========================================================
    # EMOJI
    # ========================================================

    {
        "mode": "Emoji",
        "difficulty": "Easy",
        "q": "🐶 = Which animal?",
        "hint": "Woof!",
        "answers": ["dog"],
        "xp": 10,
    },
    {
        "mode": "Emoji",
        "difficulty": "Easy",
        "q": "🍎 = What fruit?",
        "hint": "Red fruit",
        "answers": ["apple"],
        "xp": 10,
    },
    {
        "mode": "Emoji",
        "difficulty": "Medium",
        "q": "🌧️ + ☂️ = What do you need?",
        "hint": "Rain protection",
        "answers": ["umbrella"],
        "xp": 20,
    },
    {
        "mode": "Emoji",
        "difficulty": "Medium",
        "q": "🔥 + 🧯 = What are you fighting?",
        "hint": "Dangerous flames",
        "answers": ["fire"],
        "xp": 20,
    },
    {
        "mode": "Emoji",
        "difficulty": "Hard",
        "q": "👑 + 🦁 = Guess the phrase!",
        "hint": "King of the...",
        "answers": ["king of the jungle", "lion king", "lion"],
        "xp": 30,
    },
    {
        "mode": "Emoji",
        "difficulty": "Hard",
        "q": "🌙 + 🚶 = Night-time activity?",
        "hint": "Walking...",
        "answers": ["night walk", "walking at night"],
        "xp": 30,
    },


    # ========================================================
    # CITY
    # ========================================================

    {
        "mode": "City",
        "difficulty": "Easy",
        "q": "Which city is famous for the Eiffel Tower?",
        "hint": "🇫🇷",
        "answers": ["paris"],
        "xp": 10,
    },
    {
        "mode": "City",
        "difficulty": "Easy",
        "q": "Which city is famous for the Statue of Liberty?",
        "hint": "🇺🇸",
        "answers": ["new york", "new york city", "nyc"],
        "xp": 10,
    },
    {
        "mode": "City",
        "difficulty": "Medium",
        "q": "Which city is known as the Big Apple?",
        "hint": "Same city as Statue of Liberty",
        "answers": ["new york", "new york city", "nyc"],
        "xp": 20,
    },
    {
        "mode": "City",
        "difficulty": "Medium",
        "q": "Which city is famous for Bollywood?",
        "hint": "India 🇮🇳",
        "answers": ["mumbai", "bombay"],
        "xp": 20,
    },
    {
        "mode": "City",
        "difficulty": "Hard",
        "q": "Which city is called the Eternal City?",
        "hint": "Italy 🇮🇹",
        "answers": ["rome"],
        "xp": 30,
    },
    {
        "mode": "City",
        "difficulty": "Hard",
        "q": "Which city is famous for the Burj Khalifa?",
        "hint": "UAE 🇦🇪",
        "answers": ["dubai"],
        "xp": 30,
    },


    # ========================================================
    # RIDDLE
    # ========================================================

    {
        "mode": "Riddle",
        "difficulty": "Easy",
        "q": "I have hands but cannot clap. What am I?",
        "hint": "Time ⏰",
        "answers": ["clock"],
        "xp": 10,
    },
    {
        "mode": "Riddle",
        "difficulty": "Easy",
        "q": "I have teeth but cannot bite. What am I?",
        "hint": "Hair ke saath use hota hai",
        "answers": ["comb"],
        "xp": 10,
    },
    {
        "mode": "Riddle",
        "difficulty": "Medium",
        "q": "The more you take, the more you leave behind. What are they?",
        "hint": "Walking 👣",
        "answers": ["steps", "footsteps"],
        "xp": 20,
    },
    {
        "mode": "Riddle",
        "difficulty": "Medium",
        "q": "I speak without a mouth and hear without ears. What am I?",
        "hint": "Mountain mein sunai deta hai",
        "answers": ["echo"],
        "xp": 20,
    },
    {
        "mode": "Riddle",
        "difficulty": "Hard",
        "q": "What gets wetter the more it dries?",
        "hint": "Bathroom",
        "answers": ["towel"],
        "xp": 30,
    },
    {
        "mode": "Riddle",
        "difficulty": "Hard",
        "q": "What has cities but no houses, forests but no trees?",
        "hint": "Navigation 🗺️",
        "answers": ["map"],
        "xp": 30,
    },


    # ========================================================
    # LOGIC
    # ========================================================

    {
        "mode": "Logic",
        "difficulty": "Easy",
        "q": "What comes next: 2, 4, 6, 8, ?",
        "hint": "+2",
        "answers": ["10"],
        "xp": 10,
    },
    {
        "mode": "Logic",
        "difficulty": "Easy",
        "q": "If 5 + 5 = 10, what is 10 + 10?",
        "hint": "Double 10",
        "answers": ["20"],
        "xp": 10,
    },
    {
        "mode": "Logic",
        "difficulty": "Medium",
        "q": "What comes next: 3, 6, 12, 24, ?",
        "hint": "×2",
        "answers": ["48"],
        "xp": 20,
    },
    {
        "mode": "Logic",
        "difficulty": "Medium",
        "q": "A dozen eggs contains how many eggs?",
        "hint": Common counting term",
        "answers": ["12"],
        "xp": 20,
    },
    {
        "mode": "Logic",
        "difficulty": "Hard",
        "q": "If all roses are flowers and some flowers fade, can we conclude all roses fade?",
        "hint": Think carefully",
        "answers": ["no"],
        "xp": 30,
    },
    {
        "mode": "Logic",
        "difficulty": "Hard",
        "q": "What comes next: 1, 1, 2, 3, 5, 8, ?",
        "hint": Fibonacci",
        "answers": ["13"],
        "xp": 30,
    },
    {
        "mode": "Logic",
        "difficulty": "Extreme",
        "q": "If 2 machines make 2 items in 2 minutes, how many items do 6 machines make in 6 minutes?",
        "hint": Same production rate",
        "answers": ["18"],
        "xp": 50,
    },


    # ========================================================
    # TRICK
    # ========================================================

    {
        "mode": "Trick",
        "difficulty": "Easy",
        "q": "How many months have 28 days?",
        "hint": Read carefully 😈",
        "answers": ["12", "all", "all 12"],
        "xp": 10,
    },
    {
        "mode": "Trick",
        "difficulty": "Easy",
        "q": "What gets bigger when you take more away?",
        "hint": Digging",
        "answers": ["hole"],
        "xp": 10,
    },
    {
        "mode": "Trick",
        "difficulty": "Medium",
        "q": "A plane crashes on the border. Where do they bury survivors?",
        "hint": Survivors...",
        "answers": ["nowhere", "they don't"],
        "xp": 20,
    },
    {
        "mode": "Trick",
        "difficulty": "Medium",
        "q": "If you have one match and enter a dark room with a candle, lamp and stove, what do you light first?",
        "hint": 🔥,
        "answers": ["match", "the match"],
        "xp": 20,
    },
    {
        "mode": "Trick",
        "difficulty": "Hard",
        "q": "What word becomes shorter when you add two letters to it?",
        "hint": Think English word",
        "answers": ["short"],
        "xp": 30,
    },
    {
        "mode": "Trick",
        "difficulty": "Hard",
        "q": "Before Mount Everest was discovered, what was the highest mountain?",
        "hint": Mountain existed anyway",
        "answers": ["mount everest", "everest"],
        "xp": 30,
    },


    # ========================================================
    # PATTERN
    # ========================================================

    {
        "mode": "Pattern",
        "difficulty": "Easy",
        "q": "A, C, E, G, ?",
        "hint": Skip one letter",
        "answers": ["i"],
        "xp": 10,
    },
    {
        "mode": "Pattern",
        "difficulty": "Easy",
        "q": "1, 3, 5, 7, ?",
        "hint": Odd numbers",
        "answers": ["9"],
        "xp": 10,
    },
    {
        "mode": "Pattern",
        "difficulty": "Medium",
        "q": "2, 6, 18, 54, ?",
        "hint": "×3",
        "answers": ["162"],
        "xp": 20,
    },
    {
        "mode": "Pattern",
        "difficulty": "Medium",
        "q": "100, 90, 80, 70, ?",
        "hint": "-10",
        "answers": ["60"],
        "xp": 20,
    },
    {
        "mode": "Pattern",
        "difficulty": "Hard",
        "q": "1, 4, 9, 16, 25, ?",
        "hint": "Perfect squares",
        "answers": ["36"],
        "xp": 30,
    },
    {
        "mode": "Pattern",
        "difficulty": "Hard",
        "q": "2, 3, 5, 8, 12, ?",
        "hint": Increasing addition",
        "answers": ["17"],
        "xp": 30,
    },


    # ========================================================
    # PANIC
    # ========================================================

    {
        "mode": "Panic",
        "difficulty": "Easy",
        "q": "🍎 Apple ka common color?",
        "hint": "🔴 Stop signal",
        "answers": ["red"],
        "xp": 10,
    },
    {
        "mode": "Panic",
        "difficulty": "Easy",
        "q": "🐱 Cat ki awaaz?",
        "hint": "Meow!",
        "answers": ["meow"],
        "xp": 10,
    },
    {
        "mode": "Panic",
        "difficulty": "Medium",
        "q": "🌍 Earth ka natural satellite?",
        "hint": "🌙",
        "answers": ["moon"],
        "xp": 20,
    },
    {
        "mode": "Panic",
        "difficulty": "Medium",
        "q": "🧠 5 + 7 = ?",
        "hint": "12",
        "answers": ["12"],
        "xp": 20,
    },
    {
        "mode": "Panic",
        "difficulty": "Hard",
        "q": "🔢 10 × 10 = ?",
        "hint": "100",
        "answers": ["100"],
        "xp": 30,
    },
    {
        "mode": "Panic",
        "difficulty": "Hard",
        "q": "🌎 How many continents are there?",
        "hint": "Standard school answer",
        "answers": ["7", "seven"],
        "xp": 30,
    },


    # ========================================================
    # BLUFF MASTER
    # ========================================================

    {
        "mode": "Bluff Master",
        "difficulty": "Easy",
        "q": "Which one is NOT a planet?",
        "hint": "Mars / Venus / Pluto",
        "answers": ["pluto"],
        "xp": 10,
    },
    {
        "mode": "Bluff Master",
        "difficulty": "Easy",
        "q": "Which one is NOT a fruit?",
        "hint": "Carrot / Apple / Mango",
        "answers": ["carrot"],
        "xp": 10,
    },
    {
        "mode": "Bluff Master",
        "difficulty": "Medium",
        "q": "Which one is NOT a mammal?",
        "hint": "Whale / Dolphin / Shark",
        "answers": ["shark"],
        "xp": 20,
    },
    {
        "mode": "Bluff Master",
        "difficulty": "Medium",
        "q": "Which one is NOT a programming language?",
        "hint": "Python / Java / Chrome",
        "answers": ["chrome"],
        "xp": 20,
    },
    {
        "mode": "Bluff Master",
        "difficulty": "Hard",
        "q": "Which one is NOT a primary color in the traditional RYB model?",
        "hint": "Green / Red / Blue",
        "answers": ["green"],
        "xp": 30,
    },
    {
        "mode": "Bluff Master",
        "difficulty": "Hard",
        "q": "Which one is NOT a metal?",
        "hint": "Iron / Copper / Carbon",
        "answers": ["carbon"],
        "xp": 30,
    },


    # ========================================================
    # RISK IT
    # ========================================================

    {
        "mode": "Risk It",
        "difficulty": "Easy",
        "q": "How many sides does a triangle have?",
        "hint": "Basic geometry",
        "answers": ["3", "three"],
        "xp": 10,
    },
    {
        "mode": "Risk It",
        "difficulty": "Easy",
        "q": "How many days are in a week?",
        "hint": "Calendar",
        "answers": ["7", "seven"],
        "xp": 10,
    },
    {
        "mode": "Risk It",
        "difficulty": "Medium",
        "q": "What is 15 × 2?",
        "hint": "Double 15",
        "answers": ["30"],
        "xp": 20,
    },
    {
        "mode": "Risk It",
        "difficulty": "Medium",
        "q": "What is 144 ÷ 12?",
        "hint": "Dozen",
        "answers": ["12"],
        "xp": 20,
    },
    {
        "mode": "Risk It",
        "difficulty": "Hard",
        "q": "What is 17 × 6?",
        "hint": "17 × 3 × 2",
        "answers": ["102"],
        "xp": 30,
    },
    {
        "mode": "Risk It",
        "difficulty": "Hard",
        "q": "What is 225 ÷ 15?",
        "hint": "15 × ?",
        "answers": ["15"],
        "xp": 30,
    },


    # ========================================================
    # MEMORY BOMB
    # ========================================================

    {
        "mode": "Memory Bomb",
        "difficulty": "Easy",
        "q": "Remember: 🍎 🐶 🚗. Which was SECOND?",
        "hint": "Don't overthink 😂",
        "answers": ["dog", "🐶"],
        "xp": 10,
    },
    {
        "mode": "Memory Bomb",
        "difficulty": "Easy",
        "q": "Remember: 🔥 🌙 ⭐. Which was FIRST?",
        "hint": "Look at the sequence",
        "answers": ["fire", "🔥"],
        "xp": 10,
    },
    {
        "mode": "Memory Bomb",
        "difficulty": "Medium",
        "q": "Remember: CAT → BLUE → 7. What was the number?",
        "hint": "Last item",
        "answers": ["7", "seven"],
        "xp": 20,
    },
    {
        "mode": "Memory Bomb",
        "difficulty": "Medium",
        "q": "Remember: RED → 42 → MOON. What came SECOND?",
        "hint": "Middle",
        "answers": ["42"],
        "xp": 20,
    },
    {
        "mode": "Memory Bomb",
        "difficulty": "Hard",
        "q": "Remember: TIGER → 19 → BLUE → 7. What came THIRD?",
        "hint": "Count carefully",
        "answers": ["blue"],
        "xp": 30,
    },
    {
        "mode": "Memory Bomb",
        "difficulty": "Hard",
        "q": "Remember: 4 → DOG → 81 → MOON. What came LAST?",
        "hint": "Final item",
        "answers": ["moon"],
        "xp": 30,
    },


    # ========================================================
    # ONE WORD CHAOS
    # ========================================================

    {
        "mode": "One Word Chaos",
        "difficulty": "Easy",
        "q": "Something you use to tell time?",
        "hint": "One word only",
        "answers": ["clock", "watch"],
        "xp": 10,
    },
    {
        "mode": "One Word Chaos",
        "difficulty": "Easy",
        "q": "Something you wear on your feet?",
        "hint": "👟",
        "answers": ["shoes", "shoe"],
        "xp": 10,
    },
    {
        "mode": "One Word Chaos",
        "difficulty": "Medium",
        "q": "A place where books are kept?",
        "hint": "📚",
        "answers": ["library"],
        "xp": 20,
    },
    {
        "mode": "One Word Chaos",
        "difficulty": "Medium",
        "q": "A vehicle that flies?",
        "hint": "✈️",
        "answers": ["airplane", "plane"],
        "xp": 20,
    },
    {
        "mode": "One Word Chaos",
        "difficulty": "Hard",
        "q": "A person who studies stars and planets?",
        "hint": "Space scientist",
        "answers": ["astronomer"],
        "xp": 30,
    },
    {
        "mode": "One Word Chaos",
        "difficulty": "Hard",
        "q": "A person who studies living organisms?",
        "hint": "Biology",
        "answers": ["biologist"],
        "xp": 30,
    },


    # ========================================================
    # TARGET NUMBER
    # ========================================================

    {
        "mode": "Target Number",
        "difficulty": "Easy",
        "q": "Target = 10. What is 6 + 4?",
        "hint": "Reach target",
        "answers": ["10"],
        "xp": 10,
    },
    {
        "mode": "Target Number",
        "difficulty": "Easy",
        "q": "Target = 20. What is 5 × 4?",
        "hint": "Multiply",
        "answers": ["20"],
        "xp": 10,
    },
    {
        "mode": "Target Number",
        "difficulty": "Medium",
        "q": "Target = 25. What is 100 ÷ 4?",
        "hint": "Quarter of 100",
        "answers": ["25"],
        "xp": 20,
    },
    {
        "mode": "Target Number",
        "difficulty": "Medium",
        "q": "Target = 36. What is 6 × 6?",
        "hint": "Square",
        "answers": ["36"],
        "xp": 20,
    },
    {
        "mode": "Target Number",
        "difficulty": "Hard",
        "q": "Target = 81. What is 9²?",
        "hint": "9 × 9",
        "answers": ["81"],
        "xp": 30,
    },
    {
        "mode": "Target Number",
        "difficulty": "Hard",
        "q": "Target = 144. What is 12²?",
        "hint": "12 × 12",
        "answers": ["144"],
        "xp": 30,
    },


    # ========================================================
    # MYSTERY POWER
    # ========================================================

    {
        "mode": "Mystery Power",
        "difficulty": "Easy",
        "q": "Which power would let you become invisible?",
        "hint": "You disappear 👻",
        "answers": ["invisibility", "invisible"],
        "xp": 10,
    },
    {
        "mode": "Mystery Power",
        "difficulty": "Easy",
        "q": "Which power lets you fly?",
        "hint": "Superhero mode",
        "answers": ["flight", "flying"],
        "xp": 10,
    },
    {
        "mode": "Mystery Power",
        "difficulty": "Medium",
        "q": "Which power lets you read minds?",
        "hint": "🧠",
        "answers": ["telepathy", "mind reading"],
        "xp": 20,
    },
    {
        "mode": "Mystery Power",
        "difficulty": "Medium",
        "q": "Which power means moving objects with your mind?",
        "hint": "Tele...",
        "answers": ["telekinesis"],
        "xp": 20,
    },
    {
        "mode": "Mystery Power",
        "difficulty": "Hard",
        "q": "Which fictional power involves controlling time?",
        "hint": "Time manipulation",
        "answers": ["time manipulation", "time control"],
        "xp": 30,
    },
    {
        "mode": "Mystery Power",
        "difficulty": "Hard",
        "q": "Which power would allow instantaneous movement from one place to another?",
        "hint": "Teleport...",
        "answers": ["teleportation", "teleport"],
        "xp": 30,
    },


    # ========================================================
    # SABOTAGE ROUND
    # ========================================================

    {
        "mode": "Sabotage Round",
        "difficulty": "Easy",
        "q": "Which is heavier: 1 kg iron or 1 kg cotton?",
        "hint": "Same mass 😈",
        "answers": ["same", "equal", "both"],
        "xp": 10,
    },
    {
        "mode": "Sabotage Round",
        "difficulty": "Easy",
        "q": "What has to be broken before you can use it?",
        "hint": "Breakfast 🍳",
        "answers": ["egg"],
        "xp": 10,
    },
    {
        "mode": "Sabotage Round",
        "difficulty": "Medium",
        "q": "If you overtake the person in second place, what place are you in?",
        "hint": "Think position",
        "answers": ["second", "2nd"],
        "xp": 20,
    },
    {
        "mode": "Sabotage Round",
        "difficulty": "Medium",
        "q": "How many times can you subtract 10 from 100?",
        "hint": "After first subtraction...",
        "answers": ["once", "1", "one"],
        "xp": 20,
    },
    {
        "mode": "Sabotage Round",
        "difficulty": "Hard",
        "q": "What can travel around the world while staying in one corner?",
        "hint": "Mail 📮",
        "answers": ["stamp"],
        "xp": 30,
    },
    {
        "mode": "Sabotage Round",
        "difficulty": "Hard",
        "q": "What has a neck but no head?",
        "hint": "Kitchen/table",
        "answers": ["bottle"],
        "xp": 30,
    },


    # ========================================================
    # BUZZER BATTLE
    # ========================================================

    {
        "mode": "Buzzer Battle",
        "difficulty": "Easy",
        "q": "Fast! 2 + 2?",
        "hint": "GO GO GO!",
        "answers": ["4", "four"],
        "xp": 10,
    },
    {
        "mode": "Buzzer Battle",
        "difficulty": "Easy",
        "q": "Fast! Capital of France?",
        "hint": "🇫🇷",
        "answers": ["paris"],
        "xp": 10,
    },
    {
        "mode": "Buzzer Battle",
        "difficulty": "Medium",
        "q": "Fast! 9 × 9?",
        "hint": "Square",
        "answers": ["81"],
        "xp": 20,
    },
    {
        "mode": "Buzzer Battle",
        "difficulty": "Medium",
        "q": "Fast! How many letters in ENGLISH?",
        "hint": "Count",
        "answers": ["7", "seven"],
        "xp": 20,
    },
    {
        "mode": "Buzzer Battle",
        "difficulty": "Hard",
        "q": "Fast! Square root of 144?",
        "hint": "12 × 12",
        "answers": ["12", "twelve"],
        "xp": 30,
    },
    {
        "mode": "Buzzer Battle",
        "difficulty": "Hard",
        "q": "Fast! How many degrees in a full circle?",
        "hint": "Geometry",
        "answers": ["360", "three hundred sixty"],
        "xp": 30,
    },


    # ========================================================
    # CHAOS MODE
    # ========================================================

    {
        "mode": "CHAOS MODE",
        "difficulty": "Easy",
        "q": "😂 Brain ka opposite kya hai?",
        "hint": "Kabhi-kabhi user ke paas nahi hota",
        "answers": ["no brain", "nothing", "blank"],
        "xp": 10,
    },
    {
        "mode": "CHAOS MODE",
        "difficulty": "Easy",
        "q": "🤖 Robot ko sabse zyada kya pasand hota hai?",
        "hint": "Logic",
        "answers": ["logic"],
        "xp": 10,
    },
    {
        "mode": "CHAOS MODE",
        "difficulty": "Medium",
        "q": "🧠 Agar brain hang ho jaye to kya karoge?",
        "hint": "Classic solution 😂",
        "answers": ["restart", "reboot"],
        "xp": 20,
    },
    {
        "mode": "CHAOS MODE",
        "difficulty": "Medium",
        "q": "😈 GuessArena ka sabse dangerous enemy?",
        "hint": "Question ke saamne baitha hai",
        "answers": ["player", "me", "myself"],
        "xp": 20,
    },
    {
        "mode": "CHAOS MODE",
        "difficulty": "Hard",
        "q": "🚨 Brain ne resignation de diya. Ab replacement kaun?",
        "hint": "Google nahi chalega 😭",
        "answers": ["another brain", "brain"],
        "xp": 30,
    },
    {
        "mode": "CHAOS MODE",
        "difficulty": "Hard",
        "q": "💀 Question easy tha, phir bhi galat hua. Problem?",
        "hint": "System mein nahi...",
        "answers": ["brain", "me", "player"],
        "xp": 30,
    },


    # ========================================================
    # KING OF THE HILL
    # ========================================================

    {
        "mode": "King of the Hill",
        "difficulty": "Easy",
        "q": "Who is known as the King of the Jungle?",
        "hint": "🦁",
        "answers": ["lion"],
        "xp": 10,
    },
    {
        "mode": "King of the Hill",
        "difficulty": "Easy",
        "q": "What is the highest chess piece?",
        "hint": "👑",
        "answers": ["king"],
        "xp": 10,
    },
    {
        "mode": "King of the Hill",
        "difficulty": "Medium",
        "q": "Which mountain is the highest above sea level?",
        "hint": "Himalayas",
        "answers": ["mount everest", "everest"],
        "xp": 20,
    },
    {
        "mode": "King of the Hill",
        "difficulty": "Medium",
        "q": "Which planet is the largest in our solar system?",
        "hint": "Gas giant",
        "answers": ["jupiter"],
        "xp": 20,
    },
    {
        "mode": "King of the Hill",
        "difficulty": "Hard",
        "q": "Which ocean is the largest?",
        "hint": "Earth's biggest ocean",
        "answers": ["pacific", "pacific ocean"],
        "xp": 30,
    },
    {
        "mode": "King of the Hill",
        "difficulty": "Hard",
        "q": "Which is the largest continent by area?",
        "hint": "Very big 🌏",
        "answers": ["asia"],
        "xp": 30,
    },

]


# ============================================================
# NORMALIZE ANSWERS
# ============================================================

def normalize(text):
    if text is None:
        return ""

    text = str(text).lower().strip()

    replacements = {
        "’": "'",
        "“": '"',
        "”": '"',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = " ".join(text.split())

    return text


# ============================================================
# PLAYER HELPERS
# ============================================================

def ensure_player(chat_id, user):
    cur.execute(
        """
        INSERT OR IGNORE INTO players(
            chat_id,
            user_id,
            name
        )
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


# ============================================================
# LEVEL / TITLE
# ============================================================

def level_from_xp(xp):
    return max(1, (xp // 100) + 1)


def title_from_level(level):
    if level >= 20:
        return "👑 Arena Legend"

    if level >= 15:
        return "🔥 Brain Overlord"

    if level >= 10:
        return "⚡ Quiz Beast"

    if level >= 7:
        return "🧠 Brain Master"

    if level >= 5:
        return "🎯 Sharp Mind"

    if level >= 3:
        return "🚀 Rising Player"

    return "🌱 Rookie"


# ============================================================
# QUESTION POOL
# ============================================================

def pool_for(mode, difficulty):
    """
    Returns ONLY questions matching requested mode/difficulty.
    No cross-mode fallback.
    """

    pool = [
        q for q in QUESTIONS
        if q["mode"] == mode
        and (
            difficulty == "Any"
            or q["difficulty"] == difficulty
        )
    ]

    # If exact difficulty doesn't exist,
    # stay inside the same mode.
    if not pool:
        pool = [
            q for q in QUESTIONS
            if q["mode"] == mode
        ]

    return pool


def choose_question(mode="Random", difficulty="Any", used=None):
    """
    Select question without immediate/current-session repetition.

    For Random:
      - difficulty Any -> all questions
      - specific difficulty -> only that difficulty

    For a specific mode:
      - only that mode
      - if requested difficulty doesn't exist,
        same mode fallback is used.
    """

    if used is None:
        used = set()

    if mode == "Random":

        if difficulty == "Any":
            pool = QUESTIONS[:]
        else:
            pool = [
                q for q in QUESTIONS
                if q["difficulty"] == difficulty
            ]

            if not pool:
                pool = QUESTIONS[:]

    else:
        pool = pool_for(mode, difficulty)

    if not pool:
        return None

    available = [
        q for q in pool
        if q.get("_key") not in used
    ]

    # Current cycle finished.
    if not available:
        used.clear()
        available = pool[:]

    return random.choice(available)


def question_key(q):
    return (
        q["mode"],
        q["difficulty"],
        q["q"],
    )


# ============================================================
# MENUS
# ============================================================

def main_menu():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎮 PLAY",
                callback_data="menu:play",
            ),
            InlineKeyboardButton(
                "🎯 MODES",
                callback_data="menu:modes",
            ),
        ],
        [
            InlineKeyboardButton(
                "👤 PROFILE",
                callback_data="menu:profile",
            ),
            InlineKeyboardButton(
                "🏆 LEADERBOARD",
                callback_data="menu:leaderboard",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏅 ACHIEVEMENTS",
                callback_data="menu:achievements",
            ),
            InlineKeyboardButton(
                "📅 DAILY",
                callback_data="menu:daily",
            ),
        ],
    ])


def mode_menu():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🧩 Word",
                callback_data="mode:Word",
            ),
            InlineKeyboardButton(
                "🐾 Animal",
                callback_data="mode:Animal",
            ),
        ],
        [
            InlineKeyboardButton(
                "😂 Emoji",
                callback_data="mode:Emoji",
            ),
            InlineKeyboardButton(
                "🌍 City",
                callback_data="mode:City",
            ),
        ],
        [
            InlineKeyboardButton(
                "🧠 Riddle",
                callback_data="mode:Riddle",
            ),
            InlineKeyboardButton(
                "🔢 Logic",
                callback_data="mode:Logic",
            ),
        ],
        [
            InlineKeyboardButton(
                "😈 Trick",
                callback_data="mode:Trick",
            ),
            InlineKeyboardButton(
                "📈 Pattern",
                callback_data="mode:Pattern",
            ),
        ],
        [
            InlineKeyboardButton(
                "⚡ Panic",
                callback_data="mode:Panic",
            ),
            InlineKeyboardButton(
                "🎭 Bluff Master",
                callback_data="mode:Bluff Master",
            ),
        ],
        [
            InlineKeyboardButton(
                "💰 Risk It",
                callback_data="mode:Risk It",
            ),
            InlineKeyboardButton(
                "💣 Memory Bomb",
                callback_data="mode:Memory Bomb",
            ),
        ],
        [
            InlineKeyboardButton(
                "🗣️ One Word Chaos",
                callback_data="mode:One Word Chaos",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎯 Target Number",
                callback_data="mode:Target Number",
            ),
            InlineKeyboardButton(
                "🃏 Mystery Power",
                callback_data="mode:Mystery Power",
            ),
        ],
        [
            InlineKeyboardButton(
                "😈 Sabotage",
                callback_data="mode:Sabotage Round",
            ),
            InlineKeyboardButton(
                "🚨 Buzzer",
                callback_data="mode:Buzzer Battle",
            ),
        ],
        [
            InlineKeyboardButton(
                "🌪️ CHAOS",
                callback_data="mode:CHAOS MODE",
            ),
            InlineKeyboardButton(
                "👑 King",
                callback_data="mode:King of the Hill",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 Home",
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
                "💀 Extreme",
                callback_data=f"diff:{mode}:Extreme",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎲 Any",
                callback_data=f"diff:{mode}:Any",
            ),
        ],
        [
            InlineKeyboardButton(
                "⬅️ Modes",
                callback_data="menu:modes",
            ),
        ],
    ])


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = update.effective_chat.id

    ensure_player(
        chat_id,
        update.effective_user,
    )

    text = (
        "🎮 <b>WELCOME TO GUESSARENA</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🧠 Yahan knowledge se zyada\n"
        "tumhari timing aur dimaag ki\n"
        "halat matter karti hai 😂\n\n"
        "🔥 XP kamao\n"
        "🏆 Leaderboard chadho\n"
        "🎯 Streak banao\n"
        "💀 Brain ko overheat karo\n\n"
        "<b>Choose your move 👇</b>"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# ============================================================
# HELP
# ============================================================

async def help_cmd(update, context):

    text = (
        "📖 <b>GUESSARENA HELP</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🎮 <b>Play</b> — Random challenge\n"
        "🎯 <b>Modes</b> — Choose your battlefield\n"
        "👤 <b>Profile</b> — Your stats\n"
        "🏆 <b>Leaderboard</b> — Top players\n"
        "🏅 <b>Achievements</b> — Unlock rewards\n"
        "📅 <b>Daily</b> — Daily challenge\n\n"
        "💡 Wrong answer se round khatam nahi hota.\n"
        "🔥 Correct answer par XP + streak milta hai.\n"
        "⚡ Panic mode mein sirf 5 seconds hain.\n\n"
        "Good luck. Brain ko warm-up kara lo 😂"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
    )


# ============================================================
# PANIC COUNTDOWN
# ============================================================

async def panic_countdown(chat_id, context):

    try:

        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⚡ <b>PANIC MODE!</b>\n\n"
                "⏳ <b>5</b>"
            ),
            parse_mode="HTML",
        )

        for seconds in range(4, 0, -1):

            await asyncio.sleep(1)

            game_data = active.get(chat_id)

            if not game_data:
                return

            if not game_data.get("panic", False):
                return

            try:

                await msg.edit_text(
                    (
                        "⚡ <b>PANIC MODE!</b>\n\n"
                        f"⏳ <b>{seconds}</b>"
                    ),
                    parse_mode="HTML",
                )

            except Exception:
                pass

        await asyncio.sleep(0.5)

        game_data = active.get(chat_id)

        if not game_data:
            return

        if not game_data.get("panic", False):
            return

        active.pop(chat_id, None)

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "💀 <b>TIME UP!</b>\n\n"
                "5 seconds khatam! 😂\n"
                "Panic ne tumhara brain uninstall kar diya.\n\n"
                "🚀 <b>NEXT QUESTION...</b>"
            ),
            parse_mode="HTML",
        )

        await asyncio.sleep(0.7)

        await send_next_question(
            context.bot,
            chat_id,
            game_data["mode"],
            game_data["difficulty"],
            game_data.get("used", set()),
        )

    except asyncio.CancelledError:
        return

    except Exception:
        return


# ============================================================
# SEND NEXT QUESTION
# ============================================================

async def send_next_question(
    bot,
    chat_id,
    mode,
    difficulty,
    used=None,
):

    if used is None:
        used = set()

    q = choose_question(
        mode,
        difficulty,
        used,
    )

    if q is None:
        return

    key = question_key(q)

    used.add(key)

    # If current chat has no game, create it.
    active[chat_id] = {
        "answers": [
            normalize(a)
            for a in q["answers"]
        ],
        "hint": q["hint"],
        "xp": q["xp"],
        "mode": q["mode"],
        "difficulty": q["difficulty"],
        "panic": (
            q["mode"] == "Panic"
        ),
        "panic_task": None,
        "used": used,
    }

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💡 Hint",
                callback_data=f"hint:{chat_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 Menu",
                callback_data="menu:home",
            ),
        ],
    ])

    safe_mode = html.escape(
        str(q["mode"])
    )

    safe_difficulty = html.escape(
        str(q["difficulty"])
    )

    safe_question = html.escape(
        str(q["q"])
    )

    text = (
        f"🎮 <b>{safe_mode} MODE</b>\n"
        f"🔥 Difficulty: <b>{safe_difficulty}</b>\n\n"
        f"🧩 <b>{safe_question}</b>\n\n"
        "✍️ Answer bhejo!"
    )

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    if active[chat_id]["panic"]:

        active[chat_id]["panic_task"] = (
            asyncio.create_task(
                panic_countdown(
                    chat_id,
                    type(
                        "Ctx",
                        (),
                        {"bot": bot}
                    )(),
                )
            )
        )


# ============================================================
# START GAME
# ============================================================

async def start_game(
    update,
    context,
    mode="Random",
    difficulty="Any",
):

    chat_id = update.effective_chat.id

    if chat_id in active:

        await update.effective_message.reply_text(
            "⚡ <b>Round already running!</b>\n\n"
            "Pehle current question ka answer do 😎\n"
            "Brain ko ek time pe ek hi tab kholna aata hai 😂",
            parse_mode="HTML",
        )

        return

    used = set()

    q = choose_question(
        mode,
        difficulty,
        used,
    )

    if q is None:

        await update.effective_message.reply_text(
            "😵 Is mode mein abhi questions nahi hain.",
            parse_mode="HTML",
        )

        return

    used.add(question_key(q))

    active[chat_id] = {
        "answers": [
            normalize(a)
            for a in q["answers"]
        ],
        "hint": q["hint"],
        "xp": q["xp"],
        "mode": q["mode"],
        "difficulty": q["difficulty"],
        "panic": q["mode"] == "Panic",
        "panic_task": None,
        "used": used,
    }

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💡 Hint",
                callback_data=f"hint:{chat_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 Menu",
                callback_data="menu:home",
            ),
        ],
    ])

    safe_mode = html.escape(
        str(q["mode"])
    )

    safe_difficulty = html.escape(
        str(q["difficulty"])
    )

    safe_question = html.escape(
        str(q["q"])
    )

    text = (
        f"🎮 <b>{safe_mode} MODE</b>\n"
        f"🔥 Difficulty: <b>{safe_difficulty}</b>\n\n"
        f"🧩 <b>{safe_question}</b>\n\n"
        "✍️ Answer bhejo!"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    if active[chat_id]["panic"]:

        active[chat_id]["panic_task"] = (
            asyncio.create_task(
                panic_countdown(
                    chat_id,
                    context,
                )
            )
        )


# ============================================================
# ANSWER HANDLER
# ============================================================

async def answer(update, context):

    chat_id = update.effective_chat.id

    if chat_id not in active:
        return

    game_data = active.get(chat_id)

    if not game_data:
        return

    guess = normalize(
        update.message.text
    )

    if guess not in game_data["answers"]:

        await update.message.reply_text(
            "❌ <b>Not quite!</b>\n\n"
            "😂 Brain ko thoda aur load de.\n"
            "Round abhi zinda hai!",
            parse_mode="HTML",
        )

        return

    # --------------------------------------------------------
    # Correct answer
    # --------------------------------------------------------

    panic_task = game_data.get(
        "panic_task"
    )

    if panic_task:

        try:
            panic_task.cancel()
        except Exception:
            pass

    mode = game_data["mode"]
    difficulty = game_data["difficulty"]
    xp_reward = game_data["xp"]

    used = game_data.get(
        "used",
        set(),
    )

    # IMPORTANT:
    # Remove old round BEFORE next question.
    active.pop(chat_id, None)

    ensure_player(
        chat_id,
        update.effective_user,
    )

    cur.execute(
        """
        SELECT xp,games,wins,streak,best_streak
        FROM players
        WHERE chat_id=? AND user_id=?
        """,
        (
            chat_id,
            update.effective_user.id,
        ),
    )

    row = cur.fetchone()

    if row:

        xp, games, wins, streak, best_streak = row

    else:

        xp = 0
        games = 0
        wins = 0
        streak = 0
        best_streak = 0

    xp += xp_reward
    games += 1
    wins += 1
    streak += 1

    if streak > best_streak:
        best_streak = streak

    cur.execute(
        """
        UPDATE players
        SET xp=?,
            games=?,
            wins=?,
            streak=?,
            best_streak=?
        WHERE chat_id=? AND user_id=?
        """,
        (
            xp,
            games,
            wins,
            streak,
            best_streak,
            chat_id,
            update.effective_user.id,
        ),
    )

    conn.commit()

    await update.message.reply_text(
        "🎉 <b>CORRECT!</b> 🔥🔥\n\n"
        f"⚡ +{xp_reward} XP\n"
        f"🔥 Streak: <b>{streak}</b>\n\n"
        "🚀 <b>NEXT QUESTION...</b>",
        parse_mode="HTML",
    )

    await asyncio.sleep(0.7)

    await send_next_question(
        context.bot,
        chat_id,
        mode,
        difficulty,
        used,
    )


# ============================================================
# PROFILE
# ============================================================

async def profile(update, context):

    chat_id = update.effective_chat.id
    user = update.effective_user

    ensure_player(
        chat_id,
        user,
    )

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

    xp, wins, streak, best_streak, games = row

    level = level_from_xp(xp)
    title = title_from_level(level)

    accuracy = 0

    if games:
        accuracy = round(
            (wins / games) * 100
        )

    safe_name = html.escape(
        user.full_name
    )

    text = (
        "👤 <b>MY PROFILE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 {safe_name}\n"
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


# ============================================================
# LEADERBOARD
# ============================================================

async def leaderboard(update, context):

    chat_id = update.effective_chat.id

    cur.execute(
        """
        SELECT name,xp,wins,streak
        FROM players
        WHERE chat_id=?
        ORDER BY xp DESC
        LIMIT 10
        """,
        (chat_id,),
    )

    rows = cur.fetchall()

    if not rows:

        await update.effective_message.reply_text(
            "🏆 Abhi leaderboard khaali hai 😂",
            parse_mode="HTML",
        )

        return

    medals = [
        "🥇",
        "🥈",
        "🥉",
    ]

    lines = [
        "🏆 <b>GUESSARENA LEADERBOARD</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for index, row in enumerate(rows):

        name, xp, wins, streak = row

        prefix = (
            medals[index]
            if index < 3
            else f"{index + 1}."
        )

        safe_name = html.escape(
            str(name)
        )

        lines.append(
            f"{prefix} "
            f"<b>{safe_name}</b>\n"
            f"   ⭐ {xp} XP • "
            f"🏆 {wins} wins • "
            f"🔥 {streak} streak"
        )

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ============================================================
# ACHIEVEMENTS
# ============================================================

async def achievements(update, context):

    chat_id = update.effective_chat.id
    user = update.effective_user

    ensure_player(
        chat_id,
        user,
    )

    cur.execute(
        """
        SELECT xp,wins,games,best_streak
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

    xp, wins, games, best_streak = row

    achievements = []

    if games >= 1:
        achievements.append(
            "🎮 First Blood — First game played"
        )

    if wins >= 5:
        achievements.append(
            "🔥 Getting Serious — 5 wins"
        )

    if wins >= 10:
        achievements.append(
            "🏆 Winner — 10 wins"
        )

    if best_streak >= 5:
        achievements.append(
            "⚡ On Fire — 5 streak"
        )

    if best_streak >= 10:
        achievements.append(
            "💀 Unstoppable — 10 streak"
        )

    if xp >= 500:
        achievements.append(
            "🧠 Brain Machine — 500 XP"
        )

    if xp >= 1000:
        achievements.append(
            "👑 Arena Legend — 1000 XP"
        )

    if not achievements:
        achievements.append(
            "🌱 No achievements yet.\n"
            "Khel bhai, badge khud aayega 😂"
        )

    text = (
        "🏅 <b>ACHIEVEMENTS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        + "\n\n".join(
            achievements
        )
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
    )


# ============================================================
# DAILY CHALLENGE
# ============================================================

async def daily(update, context):

    chat_id = update.effective_chat.id

    if chat_id in active:

        await update.effective_message.reply_text(
            "⚡ Pehle current round finish karo 😎",
            parse_mode="HTML",
        )

        return

    # Stable daily question for the day/chat.
    today = date.today().isoformat()

    seed = sum(
        ord(c)
        for c in (
            today
            + str(chat_id)
        )
    )

    rng = random.Random(seed)

    q = rng.choice(QUESTIONS)

    active[chat_id] = {
        "answers": [
            normalize(a)
            for a in q["answers"]
        ],
        "hint": q["hint"],
        "xp": q["xp"] + 10,
        "mode": q["mode"],
        "difficulty": q["difficulty"],
        "panic": False,
        "panic_task": None,
        "used": {
            question_key(q)
        },
        "daily": True,
    }

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💡 Hint",
                callback_data=f"hint:{chat_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 Menu",
                callback_data="menu:home",
            ),
        ],
    ])

    safe_question = html.escape(
        str(q["q"])
    )

    await update.effective_message.reply_text(
        "📅 <b>DAILY CHALLENGE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🎁 Daily question = bonus XP!\n\n"
        f"🧩 <b>{safe_question}</b>\n\n"
        "✍️ Answer bhejo!",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# ============================================================
# BUTTON HANDLER
# ============================================================

async def button(update, context):

    query = update.callback_query

    await query.answer()

    data = query.data

    # --------------------------------------------------------
    # HOME
    # --------------------------------------------------------

    if data == "menu:home":

        await query.message.reply_text(
            "🏠 <b>GUESSARENA HOME</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Choose your next move 👇",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )

        return

    # --------------------------------------------------------
    # PLAY
    # --------------------------------------------------------

    if data == "menu:play":

        await start_game(
            update,
            context,
        )

        return

    # --------------------------------------------------------
    # MODES
    # --------------------------------------------------------

    if data == "menu:modes":

        await query.message.reply_text(
            "🎯 <b>CHOOSE YOUR MODE</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Har mode mein alag type ka challenge hai.\n"
            "Good luck. 😂",
            parse_mode="HTML",
            reply_markup=mode_menu(),
        )

        return

    # --------------------------------------------------------
    # PROFILE
    # --------------------------------------------------------

    if data == "menu:profile":

        await profile(
            update,
            context,
        )

        return

    # --------------------------------------------------------
    # LEADERBOARD
    # --------------------------------------------------------

    if data == "menu:leaderboard":

        await leaderboard(
            update,
            context,
        )

        return

    # --------------------------------------------------------
    # ACHIEVEMENTS
    # --------------------------------------------------------

    if data == "menu:achievements":

        await achievements(
            update,
            context,
        )

        return

    # --------------------------------------------------------
    # DAILY
    # --------------------------------------------------------

    if data == "menu:daily":

        await daily(
            update,
            context,
        )

        return

    # --------------------------------------------------------
    # MODE SELECTED
    # --------------------------------------------------------

    if data.startswith("mode:"):

        mode = data.split(
            ":",
            1,
        )[1]

        await query.message.reply_text(
            f"🎯 <b>{html.escape(mode.upper())} MODE</b>\n\n"
            "Difficulty choose karo 👇",
            parse_mode="HTML",
            reply_markup=difficulty_menu(mode),
        )

        return

    # --------------------------------------------------------
    # DIFFICULTY SELECTED
    # --------------------------------------------------------

    if data.startswith("diff:"):

        parts = data.split(":", 2)

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

    # --------------------------------------------------------
    # HINT
    # --------------------------------------------------------

    if data.startswith("hint:"):

        try:
            chat_id = int(
                data.split(":", 1)[1]
            )
        except ValueError:

            await query.answer(
                "Invalid hint.",
                show_alert=True,
            )

            return

        game_data = active.get(
            chat_id
        )

        if not game_data:

            await query.answer(
                "Round already finished 😂",
                show_alert=True,
            )

            return

        safe_hint = html.escape(
            str(game_data["hint"])
        )

        await query.message.reply_text(
            "💡 <b>HINT</b>\n\n"
            f"{safe_hint}",
            parse_mode="HTML",
        )

        return


# ============================================================
# /GAME
# ============================================================

async def game_command(update, context):

    await start_game(
        update,
        context,
        mode="Random",
        difficulty="Any",
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update, context):

    print(
        "GuessArena error:",
        repr(context.error),
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not TOKEN:

        raise SystemExit(
            "BOT_TOKEN missing. "
            "Set BOT_TOKEN environment variable."
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
            game_command,
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

    # Buttons
    application.add_handler(
        CallbackQueryHandler(
            button
        )
    )

    # Answers
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
        "GuessArena 2.0 is running..."
    )

    application.run_polling(
        poll_interval=1,
        timeout=60,
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
