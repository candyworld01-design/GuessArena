# ============================================================
# GUESSARENA 3.0
# Mature Group Quiz / Chaos Game
# Complete replacement: bot_v2.py
# ============================================================

import os
import random
import sqlite3
import html
import asyncio
import uuid
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
BUZZER_TIME = 8


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

panic_tasks = {}
buzzer_tasks = {}


# ============================================================
# QUESTION BANK
#
# Format:
# mode, difficulty, question, hint, answers, xp
#
# The bank intentionally avoids childish "apple = red" style
# questions. Questions are reasoning / traps / knowledge /
# prediction / calculation oriented.
# ============================================================

RAW_QUESTIONS = [

    # ========================================================
    # WORD
    # ========================================================

    ("Word", "Easy",
     "What is the opposite of 'scarce'?",
     "Think about availability.",
     ["abundant", "plentiful"], 10),

    ("Word", "Easy",
     "What does 'ambiguous' mean?",
     "More than one possible interpretation.",
     ["unclear", "uncertain", "having multiple meanings"], 10),

    ("Word", "Medium",
     "What is a person who speaks two languages fluently called?",
     "Two languages.",
     ["bilingual"], 20),

    ("Word", "Medium",
     "What is the noun form of 'decide'?",
     "It ends with -sion.",
     ["decision"], 20),

    ("Word", "Medium",
     "What does 'contradict' mean?",
     "To say the opposite.",
     ["oppose", "deny", "disagree"], 20),

    ("Word", "Hard",
     "What is a word that has the same spelling but a different meaning called?",
     "Same written form.",
     ["homonym"], 30),

    ("Word", "Hard",
     "What does 'pragmatic' most closely mean?",
     "Practical rather than purely theoretical.",
     ["practical"], 30),

    ("Word", "Hard",
     "What is the study of how words are formed called?",
     "Language structure.",
     ["morphology"], 30),

    ("Word", "Extreme",
     "What does 'ephemeral' mean?",
     "It does not last long.",
     ["short lived", "short-lived", "temporary", "brief"], 50),

    ("Word", "Extreme",
     "What is the term for a statement that seems self-contradictory but may contain truth?",
     "Classic example: less is more.",
     ["paradox"], 50),


    # ========================================================
    # ANIMAL
    # ========================================================

    ("Animal", "Easy",
     "Which animal is famous for having fingerprints remarkably similar to humans?",
     "It is a primate.",
     ["koala"], 10),

    ("Animal", "Easy",
     "Which animal is known for using echolocation to navigate?",
     "Think nocturnal mammal.",
     ["bat"], 10),

    ("Animal", "Medium",
     "Which animal has the strongest bite force among living land animals?",
     "Large reptile.",
     ["hippopotamus", "hippo"], 20),

    ("Animal", "Medium",
     "Which mammal lays eggs?",
     "Australia has two famous examples.",
     ["platypus"], 20),

    ("Animal", "Medium",
     "Which animal can regenerate lost arms and has a highly decentralized nervous system?",
     "Ocean animal.",
     ["starfish", "sea star"], 20),

    ("Animal", "Hard",
     "Which bird is famous for being unable to fly but can run extremely fast?",
     "African bird.",
     ["ostrich"], 30),

    ("Animal", "Hard",
     "Which animal is known for having blue blood due to copper-based hemocyanin?",
     "Eight-armed ocean creature.",
     ["octopus"], 30),

    ("Animal", "Hard",
     "What is the only mammal capable of sustained powered flight?",
     "Not gliding.",
     ["bat"], 30),

    ("Animal", "Extreme",
     "Which animal has the largest brain of any living animal?",
     "The largest animal too.",
     ["sperm whale"], 50),

    ("Animal", "Extreme",
     "Which microscopic animal is famous for surviving extreme conditions and is commonly called a water bear?",
     "Tiny and surprisingly tough.",
     ["tardigrade", "water bear"], 50),


    # ========================================================
    # EMOJI
    # ========================================================

    ("Emoji", "Easy",
     "Decode: 🧠 + 💻 + 🔥 = what kind of situation?",
     "Brain + computer + heat.",
     ["overthinking", "brain overload", "overload"], 10),

    ("Emoji", "Easy",
     "Decode: 🔒 + 🔑 + 🚪. What is the obvious concept?",
     "Access.",
     ["security", "locked door", "access"], 10),

    ("Emoji", "Medium",
     "Decode: 🧊 + ☕. What does this most likely describe?",
     "Cold coffee.",
     ["iced coffee", "ice coffee", "cold coffee"], 20),

    ("Emoji", "Medium",
     "Decode: 🕵️ + 🔎 + ❓. What role is being represented?",
     "Someone investigating.",
     ["detective", "investigator"], 20),

    ("Emoji", "Medium",
     "Decode: 📈 + 💰 + 🚀. What market emotion does this suggest?",
     "Very optimistic.",
     ["bullish", "bull market", "optimism"], 20),

    ("Emoji", "Hard",
     "Decode: 🧠 + 🔄 + 🌙. What common human problem is this?",
     "Your brain refuses to shut down at night.",
     ["overthinking", "insomnia", "night overthinking"], 30),

    ("Emoji", "Hard",
     "Decode: 👀 + 🧠 + 🪤. What kind of question is being represented?",
     "Looks simple. Isn't.",
     ["trick question", "trap question"], 30),

    ("Emoji", "Hard",
     "Decode: 🎯 + 🧠 + ⏱️. What skill is being tested?",
     "Accuracy under time pressure.",
     ["speed and accuracy", "timing", "quick thinking"], 30),

    ("Emoji", "Extreme",
     "Decode: 🧠 + 📚 + ☕ + 🌙 + 😵. What happened?",
     "The classic exam-night storyline.",
     ["all nighter", "study all night", "exam preparation"], 50),

    ("Emoji", "Extreme",
     "Decode: 👑 + 🧠 + 🎯 + 🔥. What type of player does this describe?",
     "Someone dominating the game.",
     ["quiz master", "champion", "dominant player"], 50),


    # ========================================================
    # CITY
    # ========================================================

    ("City", "Easy",
     "Which city is home to the headquarters of the United Nations?",
     "USA.",
     ["new york", "new york city", "nyc"], 10),

    ("City", "Easy",
     "Which city is famous for the Colosseum?",
     "Italy.",
     ["rome"], 10),

    ("City", "Medium",
     "Which city is famous for the Sagrada Familia?",
     "Spain.",
     ["barcelona"], 20),

    ("City", "Medium",
     "Which city is known as the financial capital of India?",
     "Western coast.",
     ["mumbai", "bombay"], 20),

    ("City", "Medium",
     "Which city is famous for the ancient Acropolis?",
     "Greece.",
     ["athens"], 20),

    ("City", "Hard",
     "Which city is divided by the Bosporus Strait?",
     "It sits between Europe and Asia.",
     ["istanbul"], 30),

    ("City", "Hard",
     "Which city is famous for the Rijksmuseum and extensive canal network?",
     "Netherlands.",
     ["amsterdam"], 30),

    ("City", "Hard",
     "Which city is often called the City of Canals?",
     "Think Italy.",
     ["venice"], 30),

    ("City", "Extreme",
     "Which city was historically known as Constantinople?",
     "Modern Turkey.",
     ["istanbul"], 50),

    ("City", "Extreme",
     "Which city is the world's highest national capital by elevation?",
     "Bolivia.",
     ["la paz"], 50),


    # ========================================================
    # RIDDLE
    # ========================================================

    ("Riddle", "Easy",
     "I disappear the moment you say my name. What am I?",
     "Silence.",
     ["silence"], 10),

    ("Riddle", "Easy",
     "I have keys but no locks, space but no room, and you can enter but cannot go inside. What am I?",
     "You are probably using one right now.",
     ["keyboard"], 10),

    ("Riddle", "Medium",
     "The more you remove from me, the bigger I become. What am I?",
     "Think underground.",
     ["hole"], 20),

    ("Riddle", "Medium",
     "I can be cracked, made, told and played. What am I?",
     "Four common phrases use this word.",
     ["joke"], 20),

    ("Riddle", "Medium",
     "I have branches but no fruit, trunk or leaves. What am I?",
     "Money-related.",
     ["bank"], 20),

    ("Riddle", "Hard",
     "I am always in front of you but can never be seen. What am I?",
     "It has not happened yet.",
     ["future"], 30),

    ("Riddle", "Hard",
     "What can run but never walks, has a mouth but never talks, and has a bed but never sleeps?",
     "Natural feature.",
     ["river"], 30),

    ("Riddle", "Hard",
     "What has 13 hearts but no other organs?",
     "Look inside a deck.",
     ["deck of cards", "deck"], 30),

    ("Riddle", "Extreme",
     "A man shaves several times a day, yet still has a beard. Who is he?",
     "His job gives it away.",
     ["barber"], 50),

    ("Riddle", "Extreme",
     "You see me once in June, twice in November, but not at all in May. What am I?",
     "Look at the spelling.",
     ["letter e", "e"], 50),


    # ========================================================
    # LOGIC
    # ========================================================

    ("Logic", "Easy",
     "A clock shows 3:15. What is the smaller angle between its hands?",
     "The minute hand is not exactly at 3.",
     ["7.5", "7.5 degrees"], 10),

    ("Logic", "Easy",
     "If all bloops are razzies and all razzies are lazzies, are all bloops lazzies?",
     "Transitive relationship.",
     ["yes"], 10),

    ("Logic", "Medium",
     "A farmer has 17 sheep. All but 9 run away. How many remain?",
     "Read 'all but 9'.",
     ["9", "nine"], 20),

    ("Logic", "Medium",
     "If 3 workers finish 3 tasks in 3 hours at the same rate, how many tasks can 6 workers finish in 3 hours?",
     "Double the workers.",
     ["6"], 20),

    ("Logic", "Medium",
     "A number is doubled and then 6 is added, giving 20. What was the number?",
     "Work backwards.",
     ["7"], 20),

    ("Logic", "Hard",
     "You have 8 identical-looking balls. One is heavier. With a balance scale, what is the minimum number of weighings needed to guarantee finding it?",
     "Split into groups.",
     ["2", "two"], 30),

    ("Logic", "Hard",
     "A father is 30 years older than his son. In 5 years he will be twice his son's age. How old is the son now?",
     "Set up one equation.",
     ["25", "25 years"], 30),

    ("Logic", "Hard",
     "If yesterday was two days before Thursday, what day is today?",
     "Yesterday = Tuesday.",
     ["wednesday", "wednesday"], 30),

    ("Logic", "Extreme",
     "You have 9 coins. One is lighter. What is the minimum number of balance-scale weighings needed to guarantee finding it?",
     "Three groups of three.",
     ["2", "two"], 50),

    ("Logic", "Extreme",
     "A bat and ball cost ₹110 total. The bat costs ₹100 more than the ball. What does the ball cost?",
     "Don't answer ₹10 too quickly.",
     ["5", "₹5", "5 rupees"], 50),


    # ========================================================
    # TRICK
    # ========================================================

    ("Trick", "Easy",
     "A doctor gives you 3 pills and says take one every 30 minutes. How long until all are taken?",
     "First pill is taken immediately.",
     ["1 hour", "60 minutes", "one hour"], 10),

    ("Trick", "Easy",
     "If you pass the person in last place during a race, what position are you in?",
     "Can you actually pass last place?",
     ["impossible", "cannot", "you can't"], 10),

    ("Trick", "Medium",
     "A rooster lays an egg on top of a roof. Which side does it roll down?",
     "Who laid it?",
     ["rooster doesn't lay eggs", "rooster cannot lay eggs"], 20),

    ("Trick", "Medium",
     "How many times can you subtract 5 from 25?",
     "After the first subtraction, you're no longer subtracting from 25.",
     ["once", "1", "one"], 20),

    ("Trick", "Medium",
     "A bus driver goes the wrong way down a one-way street but is not stopped. Why?",
     "The driver is not necessarily driving.",
     ["he is walking", "walking", "not driving"], 20),

    ("Trick", "Hard",
     "What five-letter word becomes shorter when you add two letters?",
     "Classic wordplay.",
     ["short"], 30),

    ("Trick", "Hard",
     "A plane crashes exactly on the border between two countries. Where are the survivors buried?",
     "Survivors...",
     ["nowhere", "they are not buried"], 30),

    ("Trick", "Hard",
     "Before Mount Everest was measured, what was the highest mountain in the world?",
     "It existed before measurement.",
     ["mount everest", "everest"], 30),

    ("Trick", "Extreme",
     "You enter a room with a candle, a lamp and a fireplace. You have one match. What do you light first?",
     "The thing in your hand.",
     ["match"], 50),

    ("Trick", "Extreme",
     "A man was born in 2000 and died in 2000 at age 80. How is this possible?",
     "2000 is not necessarily a year.",
     ["room number", "hospital room", "born in room 2000", "2000 was a place"], 50),


    # ========================================================
    # PATTERN
    # ========================================================

    ("Pattern", "Easy",
     "What comes next: 2, 6, 12, 20, 30, ?",
     "Products of consecutive numbers.",
     ["42"], 10),

    ("Pattern", "Easy",
     "What comes next: 1, 4, 10, 22, 46, ?",
     "Multiply by 2, then add 2.",
     ["94"], 10),

    ("Pattern", "Medium",
     "What comes next: 3, 8, 15, 24, 35, ?",
     "Differences increase by 2.",
     ["48"], 20),

    ("Pattern", "Medium",
     "What comes next: 81, 27, 9, 3, ?",
     "Divide by 3.",
     ["1"], 20),

    ("Pattern", "Medium",
     "What comes next: 5, 10, 20, 40, 80, ?",
     "Double it.",
     ["160"], 20),

    ("Pattern", "Hard",
     "What comes next: 2, 5, 11, 23, 47, ?",
     "Double then add 1.",
     ["95"], 30),

    ("Pattern", "Hard",
     "What comes next: 1, 2, 6, 24, 120, ?",
     "Factorial pattern.",
     ["720"], 30),

    ("Pattern", "Hard",
     "What comes next: 100, 96, 88, 76, 60, ?",
     "Subtract 4, 8, 12, 16...",
     ["40"], 30),

    ("Pattern", "Extreme",
     "What comes next: 7, 10, 16, 28, 52, ?",
     "Differences double.",
     ["100"], 50),

    ("Pattern", "Extreme",
     "What comes next: 1, 11, 21, 1211, 111221, ?",
     "Describe the previous term.",
     ["312211"], 50),


    # ========================================================
    # PANIC
    # ========================================================

    ("Panic", "Easy",
     "No calculator: 17 + 28 = ?",
     "Think 17 + 20 + 8.",
     ["45"], 10),

    ("Panic", "Easy",
     "What is 15% of 200?",
     "10% + 5%.",
     ["30"], 10),

    ("Panic", "Medium",
     "What is 13 × 7?",
     "10×7 + 3×7.",
     ["91"], 20),

    ("Panic", "Medium",
     "A ₹500 item is discounted by 20%. Final price?",
     "You save ₹100.",
     ["400", "₹400"], 20),

    ("Panic", "Medium",
     "What is the next prime number after 29?",
     "31 is prime.",
     ["31"], 20),

    ("Panic", "Hard",
     "What is 17²?",
     "17 × 17.",
     ["289"], 30),

    ("Panic", "Hard",
     "A train travels 60 km in 45 minutes. What is its average speed?",
     "Convert 45 minutes to 0.75 hour.",
     ["80", "80 km/h"], 30),

    ("Panic", "Hard",
     "What is 999 × 9?",
     "1000×9 minus 9.",
     ["8991"], 30),

    ("Panic", "Extreme",
     "What is 25² + 24²?",
     "625 + 576.",
     ["1201"], 50),

    ("Panic", "Extreme",
     "If x + x/2 = 30, what is x?",
     "Multiply the equation by 2.",
     ["20"], 50),


    # ========================================================
    # BLUFF MASTER
    # ========================================================

    ("Bluff Master", "Easy",
     "Which one is NOT a programming language: Python, Java, Rust, Firefox?",
     "One is a browser.",
     ["firefox"], 10),

    ("Bluff Master", "Easy",
     "Which one is NOT a prime number: 29, 31, 37, 39?",
     "Check divisibility by 3.",
     ["39"], 10),

    ("Bluff Master", "Medium",
     "Which one is NOT a renewable energy source: solar, wind, coal, hydro?",
     "Fossil fuel.",
     ["coal"], 20),

    ("Bluff Master", "Medium",
     "Which one is NOT a Shakespeare play: Hamlet, Macbeth, Othello, Odyssey?",
     "Ancient Greek epic.",
     ["odyssey"], 20),

    ("Bluff Master", "Medium",
     "Which one is NOT a SI base unit: metre, second, kilogram, litre?",
     "Volume unit, not SI base.",
     ["litre", "liter"], 20),

    ("Bluff Master", "Hard",
     "Which one is NOT a binary digit: 0, 1, 2, 0?",
     "Binary has only two digits.",
     ["2"], 30),

    ("Bluff Master", "Hard",
     "Which one is NOT a gas giant: Jupiter, Saturn, Uranus, Earth?",
     "Rocky planet.",
     ["earth"], 30),

    ("Bluff Master", "Hard",
     "Which one is NOT a noble gas: helium, neon, argon, nitrogen?",
     "Nitrogen is not in group 18.",
     ["nitrogen"], 30),

    ("Bluff Master", "Extreme",
     "Which one is NOT a prime: 97, 101, 103, 105?",
     "105 has small factors.",
     ["105"], 50),

    ("Bluff Master", "Extreme",
     "Which one is NOT a valid chess piece: bishop, knight, rook, emperor?",
     "Chess has no emperor.",
     ["emperor"], 50),


    # ========================================================
    # RISK IT
    # ========================================================

    ("Risk It", "Easy",
     "SAFE: What is 12 × 5?",
     "Basic multiplication.",
     ["60"], 10),

    ("Risk It", "Easy",
     "SAFE: What is 144 ÷ 12?",
     "A dozen times what?",
     ["12"], 10),

    ("Risk It", "Medium",
     "RISK: What is 18 × 7?",
     "20×7 minus 2×7.",
     ["126"], 20),

    ("Risk It", "Medium",
     "RISK: What is 225 ÷ 15?",
     "15 × 15.",
     ["15"], 20),

    ("Risk It", "Medium",
     "RISK: What is 37 + 48?",
     "37 + 40 + 8.",
     ["85"], 20),

    ("Risk It", "Hard",
     "HIGH RISK: What is 23²?",
     "529.",
     ["529"], 30),

    ("Risk It", "Hard",
     "HIGH RISK: What is 125 × 16?",
     "125 × 8 × 2.",
     ["2000"], 30),

    ("Risk It", "Hard",
     "HIGH RISK: What is 9999 ÷ 9?",
     "Nearly 10000/9.",
     ["1111"], 30),

    ("Risk It", "Extreme",
     "ALL IN: What is 37 × 27?",
     "37 × (30 - 3).",
     ["999"], 50),

    ("Risk It", "Extreme",
     "ALL IN: What is 48²?",
     "Think (50 - 2)².",
     ["2304"], 50),


    # ========================================================
    # MEMORY BOMB
    # ========================================================

    ("Memory Bomb", "Easy",
     "MEMORIZE: RED → 17 → TIGER → GLASS. What was SECOND?",
     "Sequence matters.",
     ["17"], 10),

    ("Memory Bomb", "Easy",
     "MEMORIZE: MOON → 42 → BLUE → CLOCK. What was LAST?",
     "Final item.",
     ["clock"], 10),

    ("Memory Bomb", "Medium",
     "MEMORIZE: 8 → RIVER → BLACK → 31 → KEY. What was THIRD?",
     "Count from the left.",
     ["black"], 20),

    ("Memory Bomb", "Medium",
     "MEMORIZE: STAR → 91 → TRAIN → GREEN → 6. What was FOURTH?",
     "One before the final number.",
     ["green"], 20),

    ("Memory Bomb", "Medium",
     "MEMORIZE: 14 → EAGLE → GLASS → 72 → RED. What was FIRST?",
     "Beginning.",
     ["14"], 20),

    ("Memory Bomb", "Hard",
     "MEMORIZE: BLACK → 27 → OCEAN → 9 → TIGER → 44. What was FIFTH?",
     "Second-last item.",
     ["tiger"], 30),

    ("Memory Bomb", "Hard",
     "MEMORIZE: 5 → BLUE → 19 → MOON → 73 → RING. What was THIRD?",
     "Middle-ish.",
     ["19"], 30),

    ("Memory Bomb", "Hard",
     "MEMORIZE: TRAIN → 81 → RED → 12 → GLASS → 4 → STAR. What was SIXTH?",
     "Count carefully.",
     ["4"], 30),

    ("Memory Bomb", "Extreme",
     "MEMORIZE: 7 → LION → 42 → BLACK → 19 → RIVER → 88 → KEY. What was FOURTH?",
     "No guessing.",
     ["black"], 50),

    ("Memory Bomb", "Extreme",
     "MEMORIZE: BLUE → 13 → TRAIN → 71 → MOON → 4 → EAGLE → 29. What was SEVENTH?",
     "Second-last.",
     ["eagle"], 50),


    # ========================================================
    # ONE WORD CHAOS
    # ========================================================

    ("One Word Chaos", "Easy",
     "One word: What do you call a fear of failure?",
     "Starts with A.",
     ["atychiphobia"], 10),

    ("One Word Chaos", "Easy",
     "One word: A person who studies human society?",
     "Social science.",
     ["sociologist"], 10),

    ("One Word Chaos", "Medium",
     "One word: The ability to recover after difficulty?",
     "Mental toughness.",
     ["resilience"], 20),

    ("One Word Chaos", "Medium",
     "One word: A person who studies the mind and behaviour?",
     "Psychology.",
     ["psychologist"], 20),

    ("One Word Chaos", "Medium",
     "One word: Fear of confined spaces?",
     "Opposite of open spaces.",
     ["claustrophobia"], 20),

    ("One Word Chaos", "Hard",
     "One word: The belief that events are predetermined?",
     "Philosophy.",
     ["determinism"], 30),

    ("One Word Chaos", "Hard",
     "One word: A government ruled by a small group?",
     "Greek-derived political term.",
     ["oligarchy"], 30),

    ("One Word Chaos", "Hard",
     "One word: Excessive fear of being judged by others?",
     "Social anxiety is the common phrase.",
     ["social anxiety", "social phobia"], 30),

    ("One Word Chaos", "Extreme",
     "One word: The study of knowledge itself?",
     "Philosophy.",
     ["epistemology"], 50),

    ("One Word Chaos", "Extreme",
     "One word: The study of moral principles?",
     "Philosophy.",
     ["ethics"], 50),


    # ========================================================
    # TARGET NUMBER
    # ========================================================

    ("Target Number", "Easy",
     "TARGET 50: Using 25 × 2, reach the target.",
     "Simple multiplication.",
     ["50"], 10),

    ("Target Number", "Easy",
     "TARGET 64: What is 8²?",
     "Square.",
     ["64"], 10),

    ("Target Number", "Medium",
     "TARGET 72: What is 9 × 8?",
     "Multiplication.",
     ["72"], 20),

    ("Target Number", "Medium",
     "TARGET 96: What is 12 × 8?",
     "Twelve groups of eight.",
     ["96"], 20),

    ("Target Number", "Medium",
     "TARGET 125: What is 1000 ÷ 8?",
     "One eighth.",
     ["125"], 20),

    ("Target Number", "Hard",
     "TARGET 169: What is 13²?",
     "13 × 13.",
     ["169"], 30),

    ("Target Number", "Hard",
     "TARGET 196: What is 14²?",
     "14 × 14.",
     ["196"], 30),

    ("Target Number", "Hard",
     "TARGET 225: What is 15²?",
     "15 × 15.",
     ["225"], 30),

    ("Target Number", "Extreme",
     "TARGET 625: What is 25²?",
     "Quarter of 100 squared.",
     ["625"], 50),

    ("Target Number", "Extreme",
     "TARGET 1296: What is 36²?",
     "Think (30 + 6)².",
     ["1296"], 50),


    # ========================================================
    # MYSTERY POWER
    # ========================================================

    ("Mystery Power", "Easy",
     "A power that lets you know what someone is thinking?",
     "Mind-based ability.",
     ["telepathy", "mind reading"], 10),

    ("Mystery Power", "Easy",
     "A power that lets you control objects using your mind?",
     "Starts with tele-.",
     ["telekinesis"], 10),

    ("Mystery Power", "Medium",
     "A power that lets you manipulate time?",
     "Time control.",
     ["time manipulation", "time control"], 20),

    ("Mystery Power", "Medium",
     "A power that lets you see events from the future?",
     "Future sight.",
     ["precognition", "future sight"], 20),

    ("Mystery Power", "Medium",
     "A power that allows instant movement between locations?",
     "No travel time.",
     ["teleportation", "teleport"], 20),

    ("Mystery Power", "Hard",
     "A power allowing control over another person's emotions?",
     "Emotional manipulation.",
     ["emotion manipulation", "emotional manipulation"], 30),

    ("Mystery Power", "Hard",
     "A power allowing someone to create copies of themselves?",
     "One becomes many.",
     ["duplication", "cloning"], 30),

    ("Mystery Power", "Hard",
     "A power allowing communication with the dead in fiction?",
     "Spirit communication.",
     ["necromancy", "mediumship"], 30),

    ("Mystery Power", "Extreme",
     "A power that would theoretically let you alter probability itself?",
     "Luck taken to the extreme.",
     ["probability manipulation"], 50),

    ("Mystery Power", "Extreme",
     "A power that lets you alter reality itself?",
     "The ultimate fictional cheat code.",
     ["reality manipulation", "reality warping"], 50),


    # ========================================================
    # SABOTAGE ROUND
    # ========================================================

    ("Sabotage Round", "Easy",
     "If you overtake second place, what position are you now?",
     "You take their position.",
     ["second", "2nd"], 10),

    ("Sabotage Round", "Easy",
     "Which weighs more: 1 kg iron or 1 kg cotton?",
     "Ignore the volume.",
     ["same", "equal", "both"], 10),

    ("Sabotage Round", "Medium",
     "A doctor has 4 apples and gives you 3. How many does the doctor have?",
     "Read the sentence carefully.",
     ["1", "one"], 20),

    ("Sabotage Round", "Medium",
     "If 10 people shake hands with every other person exactly once, how many handshakes happen?",
     "Combination problem.",
     ["45"], 20),

    ("Sabotage Round", "Medium",
     "You have 6 glasses: 3 full and 3 empty. Move only one glass to alternate full and empty.",
     "Pouring is allowed.",
     ["move the second full glass", "pour the second full glass"], 20),

    ("Sabotage Round", "Hard",
     "A farmer has chickens and cows. There are 10 heads and 28 legs. How many cows?",
     "Set up two equations.",
     ["4", "four"], 30),

    ("Sabotage Round", "Hard",
     "A number plus its half equals 45. What is the number?",
     "x + x/2 = 45.",
     ["30"], 30),

    ("Sabotage Round", "Hard",
     "A room has 4 corners. In each corner sits a cat. Each cat sees 3 cats. How many cats are there?",
     "Don't multiply blindly.",
     ["4", "four"], 30),

    ("Sabotage Round", "Extreme",
     "There are 100 lockers. Every 2nd locker is toggled, then every 3rd, every 4th... Which lockers remain open?",
     "Perfect squares.",
     ["1,4,9,16,25,36,49,64,81,100"], 50),

    ("Sabotage Round", "Extreme",
     "A snail climbs 3 m each day and slips 2 m each night. A 10 m wall. How many days to reach the top?",
     "The final climb does not have a night slip.",
     ["8", "eight"], 50),


    # ========================================================
    # BUZZER BATTLE
    # ========================================================

    ("Buzzer Battle", "Easy",
     "BUZZER: What is 17 + 19?",
     "Answer fast.",
     ["36"], 10),

    ("Buzzer Battle", "Easy",
     "BUZZER: What is 9²?",
     "Nine squared.",
     ["81"], 10),

    ("Buzzer Battle", "Medium",
     "BUZZER: What is 15% of 300?",
     "10% + 5%.",
     ["45"], 20),

    ("Buzzer Battle", "Medium",
     "BUZZER: What is the next prime after 47?",
     "Check 49.",
     ["53"], 20),

    ("Buzzer Battle", "Medium",
     "BUZZER: How many degrees are in a straight angle?",
     "Geometry.",
     ["180"], 20),

    ("Buzzer Battle", "Hard",
     "BUZZER: What is 19²?",
     "361.",
     ["361"], 30),

    ("Buzzer Battle", "Hard",
     "BUZZER: What is 2⁵?",
     "Five factors of 2.",
     ["32"], 30),

    ("Buzzer Battle", "Hard",
     "BUZZER: What is √225?",
     "15 × 15.",
     ["15"], 30),

    ("Buzzer Battle", "Extreme",
     "BUZZER: What is 99 × 101?",
     "Difference of squares.",
     ["9999"], 50),

    ("Buzzer Battle", "Extreme",
     "BUZZER: What is 125 × 24?",
     "125 × 6 × 4.",
     ["3000"], 50),


    # ========================================================
    # CHAOS MODE
    # ========================================================

    ("CHAOS MODE", "Easy",
     "CHAOS: Which is greater: 0.9 or 0.89?",
     "Compare decimal places.",
     ["0.9", "0.90"], 10),

    ("CHAOS MODE", "Easy",
     "CHAOS: If a question has no correct answer among the options, what should you do?",
     "Don't force a wrong option.",
     ["say none", "none", "none of them"], 10),

    ("CHAOS MODE", "Medium",
     "CHAOS: A question says 'choose the smallest number' and gives -3, -7, -1. Which wins?",
     "Negative numbers reverse intuition.",
     ["-7"], 20),

    ("CHAOS MODE", "Medium",
     "CHAOS: What is heavier: a kilogram of gold or a kilogram of feathers?",
     "Mass is already given.",
     ["same", "equal"], 20),

    ("CHAOS MODE", "Medium",
     "CHAOS: If everyone in a room is above average, what must be true?",
     "Think mathematically.",
     ["impossible", "cannot happen"], 20),

    ("CHAOS MODE", "Hard",
     "CHAOS: If you randomly guess a yes/no question, what is the basic probability of being correct?",
     "Two equally likely outcomes.",
     ["50%", "50", "one half"], 30),

    ("CHAOS MODE", "Hard",
     "CHAOS: What is the only even prime number?",
     "There is exactly one.",
     ["2", "two"], 30),

    ("CHAOS MODE", "Hard",
     "CHAOS: If a statement says 'This statement is false', what famous logical problem does it resemble?",
     "Self-reference.",
     ["liar paradox", "liar's paradox"], 30),

    ("CHAOS MODE", "Extreme",
     "CHAOS: If you know that you know nothing, which philosopher is famously associated with that idea?",
     "Ancient Greece.",
     ["socrates"], 50),

    ("CHAOS MODE", "Extreme",
     "CHAOS: A fair coin lands heads 5 times in a row. What is the probability the next flip is heads?",
     "Previous flips do not change a fair coin.",
     ["50%", "50", "one half"], 50),


    # ========================================================
    # KING OF THE HILL
    # ========================================================

    ("King of the Hill", "Easy",
     "KING: Which planet has the shortest year?",
     "Closest planet to the Sun.",
     ["mercury"], 10),

    ("King of the Hill", "Easy",
     "KING: What is the largest ocean?",
     "Earth's biggest ocean.",
     ["pacific", "pacific ocean"], 10),

    ("King of the Hill", "Medium",
     "KING: Which element has atomic number 1?",
     "The lightest element.",
     ["hydrogen"], 20),

    ("King of the Hill", "Medium",
     "KING: Which blood cells primarily carry oxygen?",
     "Hemoglobin-containing cells.",
     ["red blood cells", "red cells", "erythrocytes"], 20),

    ("King of the Hill", "Medium",
     "KING: Which planet rotates on its side relative to most planets?",
     "Extreme axial tilt.",
     ["uranus"], 20),

    ("King of the Hill", "Hard",
     "KING: Which scientist formulated the three laws of motion?",
     "Classical mechanics.",
     ["newton", "isaac newton"], 30),

    ("King of the Hill", "Hard",
     "KING: What is the hardest natural substance commonly known?",
     "Carbon allotrope.",
     ["diamond"], 30),

    ("King of the Hill", "Hard",
     "KING: Which organelle is often called the powerhouse of the cell?",
     "Cellular energy production.",
     ["mitochondria", "mitochondrion"], 30),

    ("King of the Hill", "Extreme",
     "KING: What is the SI unit of electric resistance?",
     "Named after a scientist.",
     ["ohm", "ohms"], 50),

    ("King of the Hill", "Extreme",
     "KING: Which particle carries the electromagnetic force in the Standard Model?",
     "Massless gauge boson.",
     ["photon"], 50),
]


# ============================================================
# BUILD QUESTIONS
# ============================================================

QUESTIONS = []

for mode, difficulty, question, hint, answers, xp in RAW_QUESTIONS:
    QUESTIONS.append({
        "mode": mode,
        "difficulty": difficulty,
        "q": question,
        "hint": hint,
        "answers": answers,
        "xp": xp,
    })


# ============================================================
# NORMALIZATION
# ============================================================

def normalize(text):
    if text is None:
        return ""

    text = str(text).lower().strip()

    replacements = {
        "’": "'",
        "“": '"',
        "”": '"',
        "₹": "",
        ",": "",
        ".": "",
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


def question_key(q):
    return (
        q["mode"],
        q["difficulty"],
        q["q"],
    )


# ============================================================
# LEVEL / TITLE
# ============================================================

def level_from_xp(xp):
    return max(1, (xp // 100) + 1)


def title_from_level(level):
    if level >= 25:
        return "👑 Arena Legend"

    if level >= 20:
        return "💀 Final Boss"

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
# FUN REACTIONS
# ============================================================

CORRECT_REACTIONS = [
    "🧠 Neurons finally held a meeting.",
    "🔥 That was actually clean.",
    "🎯 Direct hit. No unnecessary drama.",
    "⚡ Brain.exe is fully operational.",
    "👑 Someone woke up dangerous today.",
    "🗿 Cold answer. Respect.",
    "🚀 That one had zero hesitation.",
    "💀 Okay Einstein, calm down.",
    "🔥 Group ko thoda competition mil gaya.",
    "🧠 Processing power detected.",
]

WRONG_REACTIONS = [
    "😂 Confidence 100%, answer unfortunately not.",
    "💀 Brain.exe has entered maintenance mode.",
    "😭 Question ne tumhe nahi, tumne khud ko hara diya.",
    "🗿 Itna confidence dekh ke answer ko bhi bura lag raha hai.",
    "😂 Google ko bhi 2 second milte toh bach jaate.",
    "💀 Neurons ne collectively 'not my problem' bola.",
    "😭 Almost... but almost se XP nahi milta.",
    "🧠 Brain loading... please don't unplug the device.",
    "😂 Answer interesting tha. Correct nahi tha, but interesting tha.",
    "💀 Aaj dimaag ne work-from-home le liya.",
]

TIMEOUT_REACTIONS = [
    "💀 Time over. Brain ne loading screen se bahar aane se mana kar diya.",
    "😭 Clock won. You lost.",
    "😂 5 seconds ka pressure aur system crash.",
    "💀 Question ab bhi wahi tha. Time nahi tha.",
]


# ============================================================
# QUESTION POOL
# ============================================================

def pool_for(mode, difficulty):
    pool = [
        q for q in QUESTIONS
        if q["mode"] == mode
        and (
            difficulty == "Any"
            or q["difficulty"] == difficulty
        )
    ]

    if not pool:
        pool = [
            q for q in QUESTIONS
            if q["mode"] == mode
        ]

    return pool


def choose_question(mode="Random", difficulty="Any", used=None):
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
        if question_key(q) not in used
    ]

    if not available:
        used.clear()
        available = pool[:]

    return random.choice(available)


# ============================================================
# TIMER HELPERS
# ============================================================

def cancel_task(task_map, chat_id):
    task = task_map.pop(chat_id, None)

    if task and not task.done():
        task.cancel()


def cancel_all_timers(chat_id):
    cancel_task(panic_tasks, chat_id)
    cancel_task(buzzer_tasks, chat_id)


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
            InlineKeyboardButton("🧩 Word", callback_data="mode:Word"),
            InlineKeyboardButton("🐾 Animal", callback_data="mode:Animal"),
        ],
        [
            InlineKeyboardButton("😂 Emoji", callback_data="mode:Emoji"),
            InlineKeyboardButton("🌍 City", callback_data="mode:City"),
        ],
        [
            InlineKeyboardButton("🧠 Riddle", callback_data="mode:Riddle"),
            InlineKeyboardButton("🔢 Logic", callback_data="mode:Logic"),
        ],
        [
            InlineKeyboardButton("😈 Trick", callback_data="mode:Trick"),
            InlineKeyboardButton("📈 Pattern", callback_data="mode:Pattern"),
        ],
        [
            InlineKeyboardButton("⚡ Panic", callback_data="mode:Panic"),
            InlineKeyboardButton("🎭 Bluff", callback_data="mode:Bluff Master"),
        ],
        [
            InlineKeyboardButton("💰 Risk It", callback_data="mode:Risk It"),
            InlineKeyboardButton("💣 Memory", callback_data="mode:Memory Bomb"),
        ],
        [
            InlineKeyboardButton(
                "🗣️ One Word",
                callback_data="mode:One Word Chaos",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎯 Target",
                callback_data="mode:Target Number",
            ),
            InlineKeyboardButton(
                "🃏 Mystery",
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
                "👑 KING",
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


def game_keyboard(chat_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💡 Hint",
                callback_data=f"hint:{chat_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 Stop / Menu",
                callback_data="menu:home",
            ),
        ],
    ])


# ============================================================
# SEND QUESTION
# ============================================================

async def send_question(
    bot,
    chat_id,
    mode,
    difficulty,
    used=None,
    daily=False,
):
    if used is None:
        used = set()

    cancel_all_timers(chat_id)

    q = choose_question(
        mode,
        difficulty,
        used,
    )

    if q is None:
        return False

    used.add(question_key(q))

    round_id = uuid.uuid4().hex

    is_panic = q["mode"] == "Panic"
    is_buzzer = q["mode"] == "Buzzer Battle"

    active[chat_id] = {
        "answers": [
            normalize(a)
            for a in q["answers"]
        ],
        "hint": q["hint"],
        "xp": q["xp"],
        "mode": q["mode"],
        "difficulty": q["difficulty"],
        "panic": is_panic,
        "buzzer": is_buzzer,
        "daily": daily,
        "used": used,
        "round_id": round_id,
    }

    safe_mode = html.escape(str(q["mode"]))
    safe_difficulty = html.escape(str(q["difficulty"]))
    safe_question = html.escape(str(q["q"]))

    if is_panic:
        prefix = "💀 <b>NO THINKING. JUST ANSWER.</b>"
    elif is_buzzer:
        prefix = "🚨 <b>FIRST CORRECT ANSWER WINS!</b>"
    elif q["mode"] == "Risk It":
        prefix = "💰 <b>HIGHER RISK = HIGHER RESPECT.</b>"
    elif q["mode"] == "Chaos":
        prefix = "🌪️ <b>EXPECT THE UNEXPECTED.</b>"
    else:
        prefix = "🧠 <b>READ TWICE. ANSWER ONCE.</b>"

    text = (
        f"🎮 <b>{safe_mode.upper()} MODE</b>\n"
        f"🔥 Difficulty: <b>{safe_difficulty}</b>\n"
        f"⭐ Reward: <b>+{q['xp']} XP</b>\n\n"
        f"{prefix}\n\n"
        f"🧩 <b>{safe_question}</b>\n\n"
        "✍️ <b>Answer bhejo!</b>"
    )

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=game_keyboard(chat_id),
        )
    except Exception:
        active.pop(chat_id, None)
        return False

    game = active.get(chat_id)

    if not game or game["round_id"] != round_id:
        return True

    if is_panic:
        task = asyncio.create_task(
            panic_countdown(
                chat_id,
                bot,
                round_id,
            )
        )

        panic_tasks[chat_id] = task

    elif is_buzzer:
        task = asyncio.create_task(
            buzzer_countdown(
                chat_id,
                bot,
                round_id,
            )
        )

        buzzer_tasks[chat_id] = task

    return True


# ============================================================
# PANIC COUNTDOWN
# ============================================================

async def panic_countdown(chat_id, bot, round_id):
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                "⚡ <b>PANIC TIMER</b>\n\n"
                "⏳ <b>5</b>\n"
                "💀 Don't overthink."
            ),
            parse_mode="HTML",
        )

        for seconds in range(4, 0, -1):
            await asyncio.sleep(1)

            game = active.get(chat_id)

            if (
                not game
                or game.get("round_id") != round_id
                or not game.get("panic")
            ):
                return

            try:
                await msg.edit_text(
                    (
                        "⚡ <b>PANIC TIMER</b>\n\n"
                        f"⏳ <b>{seconds}</b>\n"
                        "💀 DON'T PANIC."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        game = active.get(chat_id)

        if (
            not game
            or game.get("round_id") != round_id
            or not game.get("panic")
        ):
            return

        active.pop(chat_id, None)

        user_id = game.get("current_user_id")

        if user_id:
            cur.execute(
                """
                UPDATE players
                SET games=games+1,
                    streak=0
                WHERE chat_id=? AND user_id=?
                """,
                (chat_id, user_id),
            )
            conn.commit()

        reaction = random.choice(TIMEOUT_REACTIONS)

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "💀 <b>PANIC FAILED</b>\n\n"
                f"{reaction}\n\n"
                "❌ Round over.\n"
                "🎮 Start another one when ready."
            ),
            parse_mode="HTML",
        )

    except asyncio.CancelledError:
        return

    except Exception as exc:
        print("Panic timer error:", repr(exc))

    finally:
        if (
            panic_tasks.get(chat_id)
            is asyncio.current_task()
        ):
            panic_tasks.pop(chat_id, None)


# ============================================================
# BUZZER COUNTDOWN
# ============================================================

async def buzzer_countdown(chat_id, bot, round_id):
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                "🚨 <b>BUZZER LIVE</b>\n\n"
                "⏳ <b>8</b> seconds\n"
                "🏁 First correct answer takes the XP!"
            ),
            parse_mode="HTML",
        )

        for seconds in range(7, 0, -1):
            await asyncio.sleep(1)

            game = active.get(chat_id)

            if (
                not game
                or game.get("round_id") != round_id
                or not game.get("buzzer")
            ):
                return

            try:
                await msg.edit_text(
                    (
                        "🚨 <b>BUZZER LIVE</b>\n\n"
                        f"⏳ <b>{seconds}</b>\n"
                        "🏁 FIRST CORRECT WINS"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        game = active.get(chat_id)

        if (
            not game
            or game.get("round_id") != round_id
            or not game.get("buzzer")
        ):
            return

        active.pop(chat_id, None)

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "🚨 <b>BUZZER CLOSED!</b>\n\n"
                "😂 Sabke fingers fast the, "
                "brains apparently not.\n\n"
                "🏁 Nobody got it in time."
            ),
            parse_mode="HTML",
        )

    except asyncio.CancelledError:
        return

    except Exception as exc:
        print("Buzzer timer error:", repr(exc))

    finally:
        if (
            buzzer_tasks.get(chat_id)
            is asyncio.current_task()
        ):
            buzzer_tasks.pop(chat_id, None)


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
        "Not your average boring quiz. 😈\n\n"
        "🧠 Logic\n"
        "🪤 Traps\n"
        "⚡ Speed\n"
        "💀 Panic\n"
        "🚨 Buzzer\n"
        "🎲 Risk\n"
        "🌪️ Chaos\n"
        "👑 Competition\n\n"
        "🏆 Earn XP • build streaks • dominate the group.\n\n"
        "<b>Choose your battlefield 👇</b>"
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
        "📖 <b>GUESSARENA — HOW TO PLAY</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🎮 <b>PLAY</b>\n"
        "Random question from the full arena.\n\n"
        "🎯 <b>MODES</b>\n"
        "Choose exactly how you want your brain tortured. 😂\n\n"
        "🚨 <b>BUZZER</b>\n"
        "Group mein first correct answer wins.\n\n"
        "⚡ <b>PANIC</b>\n"
        "Only 5 seconds. No excuses.\n\n"
        "💰 <b>RISK IT</b>\n"
        "Harder questions = more XP.\n\n"
        "💣 <b>MEMORY</b>\n"
        "Remember the sequence. Then survive.\n\n"
        "😈 <b>TRICK</b>\n"
        "Question ko padhna bhi game ka part hai.\n\n"
        "🏆 <b>XP + STREAK</b>\n"
        "Correct answers build your streak.\n\n"
        "💡 Hint available hai, but real players "
        "pehle khud try karte hain. 😏"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
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
            "⚡ <b>ROUND ALREADY RUNNING!</b>\n\n"
            "Pehle current question solve karo.\n\n"
            "😂 Ek waqt pe ek hi brain tab khulta hai.",
            parse_mode="HTML",
        )
        return

    used = set()

    await send_question(
        context.bot,
        chat_id,
        mode,
        difficulty,
        used,
    )


# ============================================================
# ANSWER HANDLER
# ============================================================

async def answer(update, context):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user

    game_data = active.get(chat_id)

    if not game_data:
        return

    # --------------------------------------------------------
    # Buzzer / normal round ownership
    # --------------------------------------------------------

    guess = normalize(update.message.text)

    if guess not in game_data["answers"]:

        reaction = random.choice(WRONG_REACTIONS)

        await update.message.reply_text(
            "❌ <b>WRONG!</b>\n\n"
            f"{reaction}\n\n"
            "💀 Round abhi zinda hai. Try again.",
            parse_mode="HTML",
        )

        return

    # --------------------------------------------------------
    # Correct answer
    # --------------------------------------------------------

    round_id = game_data.get("round_id")

    # Re-check state so two near-simultaneous group answers
    # cannot both win the same round.
    current = active.get(chat_id)

    if (
        not current
        or current.get("round_id") != round_id
    ):
        return

    cancel_all_timers(chat_id)

    mode = game_data["mode"]
    difficulty = game_data["difficulty"]
    xp_reward = game_data["xp"]
    used = game_data.get("used", set())
    is_daily = game_data.get("daily", False)
    is_buzzer = game_data.get("buzzer", False)

    # Winner owns this round.
    active.pop(chat_id, None)

    ensure_player(
        chat_id,
        user,
    )

    cur.execute(
        """
        SELECT xp,games,wins,streak,best_streak
        FROM players
        WHERE chat_id=? AND user_id=?
        """,
        (
            chat_id,
            user.id,
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
            user.id,
        ),
    )

    conn.commit()

    reaction = random.choice(CORRECT_REACTIONS)

    if is_buzzer:
        headline = "🚨 <b>BUZZER WIN!</b>"
    elif mode == "Panic":
        headline = "⚡ <b>PANIC SURVIVED!</b>"
    else:
        headline = "🎯 <b>CORRECT!</b>"

    await update.message.reply_text(
        f"{headline}\n\n"
        f"👤 <b>{html.escape(user.full_name)}</b>\n"
        f"{reaction}\n\n"
        f"⭐ +<b>{xp_reward} XP</b>\n"
        f"🔥 Streak: <b>{streak}</b>",
        parse_mode="HTML",
    )

    # Daily is one-and-done.
    if is_daily:
        await update.message.reply_text(
            "📅 <b>DAILY CHALLENGE COMPLETE!</b>\n\n"
            "🎁 Bonus XP secured.\n"
            "🏆 Come back tomorrow for another one.",
            parse_mode="HTML",
        )
        return

    await asyncio.sleep(0.5)

    # Never start a new question if the user/group
    # already started another game during the delay.
    if chat_id in active:
        return

    await send_question(
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
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 {safe_name}\n"
        f"{title} • Level <b>{level}</b>\n\n"
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
            "🏆 Leaderboard khaali hai.\n"
            "Koi toh pehla victim bane 😂",
            parse_mode="HTML",
        )
        return

    medals = ["🥇", "🥈", "🥉"]

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

        safe_name = html.escape(str(name))

        lines.append(
            f"{prefix} <b>{safe_name}</b>\n"
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

    achievements_list = []

    if games >= 1:
        achievements_list.append(
            "🎮 <b>First Blood</b> — First game"
        )

    if wins >= 5:
        achievements_list.append(
            "🔥 <b>Getting Serious</b> — 5 wins"
        )

    if wins >= 10:
        achievements_list.append(
            "🏆 <b>Winner</b> — 10 wins"
        )

    if wins >= 25:
        achievements_list.append(
            "💀 <b>Problem</b> — 25 wins"
        )

    if best_streak >= 5:
        achievements_list.append(
            "⚡ <b>On Fire</b> — 5 streak"
        )

    if best_streak >= 10:
        achievements_list.append(
            "🔥 <b>Unstoppable</b> — 10 streak"
        )

    if best_streak >= 20:
        achievements_list.append(
            "👑 <b>Final Boss</b> — 20 streak"
        )

    if xp >= 500:
        achievements_list.append(
            "🧠 <b>Brain Machine</b> — 500 XP"
        )

    if xp >= 1000:
        achievements_list.append(
            "👑 <b>Arena Legend</b> — 1000 XP"
        )

    if not achievements_list:
        achievements_list.append(
            "🌱 <b>Nothing unlocked yet.</b>\n\n"
            "Khel bhai. Badge khud darwaza tod ke aayega 😂"
        )

    text = (
        "🏅 <b>ACHIEVEMENTS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        + "\n\n".join(achievements_list)
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
            "⚡ <b>Current round active.</b>\n\n"
            "Pehle usko finish karo.\n"
            "Daily kahin bhaag nahi raha 😂",
            parse_mode="HTML",
        )
        return

    today = date.today().isoformat()

    seed = sum(
        ord(c)
        for c in today + str(chat_id)
    )

    rng = random.Random(seed)

    q = rng.choice(QUESTIONS)

    used = {
        question_key(q)
    }

    cancel_all_timers(chat_id)

    round_id = uuid.uuid4().hex

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
        "buzzer": False,
        "daily": True,
        "used": used,
        "round_id": round_id,
    }

    safe_question = html.escape(
        str(q["q"])
    )

    await update.effective_message.reply_text(
        "📅 <b>DAILY CHALLENGE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🎁 One question.\n"
        "⭐ Bonus XP.\n"
        "🏆 One chance to flex.\n\n"
        f"🧩 <b>{safe_question}</b>\n\n"
        "✍️ Answer bhejo!",
        parse_mode="HTML",
        reply_markup=game_keyboard(chat_id),
    )


# ============================================================
# BUTTON HANDLER
# ============================================================

async def button(update, context):
    query = update.callback_query

    await query.answer()

    data = query.data
    chat_id = query.message.chat.id

    # --------------------------------------------------------
    # HOME
    # --------------------------------------------------------

    if data == "menu:home":

        cancel_all_timers(chat_id)

        active.pop(chat_id, None)

        await query.message.reply_text(
            "🏠 <b>GUESSARENA HOME</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🛑 Current round stopped.\n"
            "🧠 Brain ko reset kar diya.\n"
            "😂 Koi evidence nahi bacha.\n\n"
            "<b>Choose your next move 👇</b>",
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
            "🎯 <b>CHOOSE YOUR BATTLEFIELD</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Har mode ka apna torture mechanism hai. 😂\n\n"
            "👇 Pick one:",
            parse_mode="HTML",
            reply_markup=mode_menu(),
        )

        return

    # --------------------------------------------------------
    # PROFILE
    # --------------------------------------------------------

    if data == "menu:profile":
        await profile(update, context)
        return

    # --------------------------------------------------------
    # LEADERBOARD
    # --------------------------------------------------------

    if data == "menu:leaderboard":
        await leaderboard(update, context)
        return

    # --------------------------------------------------------
    # ACHIEVEMENTS
    # --------------------------------------------------------

    if data == "menu:achievements":
        await achievements(update, context)
        return

    # --------------------------------------------------------
    # DAILY
    # --------------------------------------------------------

    if data == "menu:daily":
        await daily(update, context)
        return

    # --------------------------------------------------------
    # MODE SELECTED
    # --------------------------------------------------------

    if data.startswith("mode:"):

        mode = data.split(
            ":",
            1,
        )[1]

        safe_mode = html.escape(
            mode.upper()
        )

        await query.message.reply_text(
            f"🎯 <b>{safe_mode}</b>\n\n"
            "Difficulty choose karo 👇",
            parse_mode="HTML",
            reply_markup=difficulty_menu(mode),
        )

        return

    # --------------------------------------------------------
    # DIFFICULTY
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
            target_chat_id = int(
                data.split(":", 1)[1]
            )
        except ValueError:
            return

        if target_chat_id != chat_id:
            return

        game_data = active.get(chat_id)

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
            f"{safe_hint}\n\n"
            "😏 Ab answer tumhari responsibility hai.",
            parse_mode="HTML",
        )

        # Track hints without affecting correctness.
        ensure_player(
            chat_id,
            query.from_user,
        )

        cur.execute(
            """
            UPDATE players
            SET hints=hints+1
            WHERE chat_id=? AND user_id=?
            """,
            (
                chat_id,
                query.from_user.id,
            ),
        )

        conn.commit()

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

    # Text answers
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
        "GuessArena 3.0 is running..."
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
