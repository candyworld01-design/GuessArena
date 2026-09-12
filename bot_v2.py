import os
import random
import sqlite3
import html
import asyncio
import uuid
from threading import Thread
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


# ============================================================
# GUESSARENA
# ============================================================

# DO NOT CHANGE - RENDER / UPTIME SETUP
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

TIMERS = {
    "Easy": 15,
    "Medium": 15,
    "Hard": 20,
    "Extreme": 20,
    "Panic": 8,
}

XP_VALUES = {
    "Easy": 10,
    "Medium": 15,
    "Hard": 25,
    "Extreme": 35,
    "Panic": 40,
}

active = {}
panic_tasks = {}


# ============================================================
# DATABASE
# ============================================================

def db():
    return sqlite3.connect(DB_FILE)


with db() as con:
    con.execute("""
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


# ============================================================
# QUESTION BANK
# ============================================================

# (question, answer, difficulty, aliases)

RAW_QUESTIONS = {

"Word": [
("What word means deliberately avoiding a topic?", "evasion", "Medium", ["evasion"]),
("What is the term for a word that sounds like what it describes?", "onomatopoeia", "Hard", ["onomatopoeia"]),
("Which word means 'existing everywhere'?", "ubiquitous", "Hard", ["ubiquitous"]),
("What is an anagram of LISTEN that means silent?", "silent", "Medium", ["silent"]),
("What word describes fear of confined spaces?", "claustrophobia", "Medium", ["claustrophobia"]),
("What is the opposite of 'scarce'?", "abundant", "Easy", ["abundant", "plentiful"]),
("Which word means a person who studies ancient societies through artifacts?", "archaeologist", "Medium", ["archaeologist"]),
("What is a word with the opposite meaning of another word called?", "antonym", "Easy", ["antonym"]),
("What do we call a phrase whose meaning isn't literal, like 'break the ice'?", "idiom", "Easy", ["idiom"]),
("Which word means extremely careful and precise?", "meticulous", "Hard", ["meticulous"]),
],

"Animal": [
("Which animal has fingerprints so similar to humans that they can be difficult to distinguish?", "koala", "Medium", ["koala"]),
("Which mammal is capable of true powered flight?", "bat", "Easy", ["bat"]),
("Which animal is famous for having three hearts?", "octopus", "Easy", ["octopus"]),
("Which bird can fly backwards?", "hummingbird", "Medium", ["hummingbird"]),
("What is the largest living land animal?", "elephant", "Easy", ["elephant", "african elephant"]),
("Which animal is known for changing the color and texture of its skin?", "octopus", "Medium", ["octopus"]),
("Which mammal lays eggs?", "platypus", "Medium", ["platypus"]),
("Which animal is famous for regenerating lost limbs?", "axolotl", "Hard", ["axolotl"]),
("Which animal has the strongest bite among living land animals?", "hippopotamus", "Hard", ["hippopotamus", "hippo"]),
("Which sea creature is biologically closer to humans than to fish?", "octopus", "Extreme", ["octopus"]),
],

"Emoji": [
("Decode: 👀 + 🧠 + 🪤. What kind of question is represented?", "trick question", "Hard", ["trick question", "trick"]),
("Decode: 🌧️ + 🐱🐶. What phrase is represented?", "raining cats and dogs", "Medium", ["raining cats and dogs", "cats and dogs"]),
("Decode: 🔥 + 🧊. What concept is represented?", "opposites", "Medium", ["opposites", "opposite"]),
("Decode: 🧠 + 💥. What phrase suggests a sudden idea?", "brainstorm", "Medium", ["brainstorm"]),
("Decode: 👑 + 🐝. What famous phrase is suggested?", "queen bee", "Easy", ["queen bee"]),
("Decode: 🕰️ + 💰. What concept is suggested?", "time is money", "Medium", ["time is money"]),
("Decode: 👂 + 🧱. What phrase means refusing to listen?", "wall of silence", "Hard", ["wall of silence"]),
("Decode: 🐟 + 🚶. What phrase suggests doing something unusual?", "fish out of water", "Hard", ["fish out of water"]),
("Decode: 🌍 + 🏃. What concept means travelling widely?", "world tour", "Easy", ["world tour"]),
("Decode: 🧩 + 🧠. What are these together strongly suggesting?", "puzzle", "Easy", ["puzzle"]),
],

"City": [
("Which city is known as the 'City of Canals'?", "venice", "Easy", ["venice"]),
("Which city is home to the Sagrada Familia?", "barcelona", "Easy", ["barcelona"]),
("Which city sits on the Bosporus and spans two continents?", "istanbul", "Medium", ["istanbul"]),
("Which city is famous for the ancient Colosseum?", "rome", "Easy", ["rome"]),
("Which city is associated with Wall Street?", "new york", "Easy", ["new york", "new york city", "nyc"]),
("Which city is famous for the Marina Bay Sands?", "singapore", "Easy", ["singapore"]),
("Which city is nicknamed the 'City of Light'?", "paris", "Easy", ["paris"]),
("Which city is famous for the Shibuya Crossing?", "tokyo", "Medium", ["tokyo"]),
("Which city is the traditional home of the Oscars' Hollywood district?", "los angeles", "Medium", ["los angeles", "la"]),
("Which city is famous for its historic red double-decker buses?", "london", "Easy", ["london"]),
],

"Riddle": [
("I have cities but no houses, forests but no trees, and rivers but no water. What am I?", "map", "Easy", ["map"]),
("The more you take, the more you leave behind. What are they?", "footsteps", "Medium", ["footsteps", "steps"]),
("I speak without a mouth and hear without ears. What am I?", "echo", "Easy", ["echo"]),
("I get wetter as I dry something else. What am I?", "towel", "Easy", ["towel"]),
("I have keys but no locks, space but no room, and you can enter but not go inside. What am I?", "keyboard", "Medium", ["keyboard"]),
("I can be cracked, made, told and played. What am I?", "joke", "Medium", ["joke"]),
("I disappear the moment you say my name. What am I?", "silence", "Medium", ["silence"]),
("I have one eye but cannot see. What am I?", "needle", "Easy", ["needle"]),
("I have branches but no fruit, trunk or leaves. What am I?", "bank", "Hard", ["bank"]),
("What has a head and a tail but no body?", "coin", "Easy", ["coin"]),
],

"Logic": [
("A clock shows 3:15. What is the smaller angle between its hands?", "7.5", "Hard", ["7.5", "7.5 degrees"]),
("If all Bloops are Razzies and all Razzies are Lazzies, are all Bloops Lazzies?", "yes", "Easy", ["yes"]),
("You have 3 switches downstairs and one bulb upstairs. You can go upstairs once. How do you identify the switch?", "heat", "Extreme", ["heat", "temperature"]),
("A farmer has 17 sheep. All but 9 run away. How many remain?", "9", "Easy", ["9"]),
("If yesterday was Monday, what day is tomorrow?", "wednesday", "Easy", ["wednesday"]),
("A train travels north while smoke blows east. Which direction does the train's smoke go?", "east", "Medium", ["east"]),
("You have 8 identical-looking balls and one is heavier. What is the minimum number of balance weighings needed?", "2", "Hard", ["2"]),
("If two people can build two walls in two hours, how long for four people to build four walls?", "2 hours", "Hard", ["2", "2 hours"]),
("A number doubled and then increased by 6 becomes 20. What is the number?", "7", "Easy", ["7"]),
("You overtake the person in second place during a race. What position are you now?", "second", "Easy", ["second", "2nd"]),
],

"Trick": [
("How many months have at least 28 days?", "12", "Easy", ["12", "twelve"]),
("A plane crashes exactly on the border of two countries. Where do they bury the survivors?", "nowhere", "Easy", ["nowhere"]),
("What becomes smaller when you turn it upside down?", "number 9", "Hard", ["9", "number 9"]),
("If you have one match and enter a dark room with a candle, lamp and fireplace, what do you light first?", "match", "Easy", ["match", "the match"]),
("A doctor gives you 3 pills and says take one every 30 minutes. How long until all are taken?", "1 hour", "Medium", ["1 hour", "60 minutes", "60"]),
("What question can you never answer 'yes' to honestly?", "are you asleep", "Medium", ["are you asleep"]),
("Before Mount Everest was discovered, what was the highest mountain?", "mount everest", "Easy", ["mount everest", "everest"]),
("You see a boat filled with people, but there isn't a single person on board. How?", "all married", "Hard", ["all married", "they are all married"]),
("A rooster lays an egg on a roof. Which way does it roll?", "roosters don't lay eggs", "Easy", ["roosters don't lay eggs", "rooster doesn't lay eggs"]),
("What has to be broken before you can use it?", "egg", "Easy", ["egg"]),
],

"Pattern": [
("Complete: 2, 6, 12, 20, 30, ?", "42", "Medium", ["42"]),
("Complete: 1, 1, 2, 3, 5, 8, ?", "13", "Easy", ["13"]),
("Complete: 3, 9, 27, 81, ?", "243", "Easy", ["243"]),
("Complete: 100, 50, 25, 12.5, ?", "6.25", "Medium", ["6.25"]),
("Complete: 2, 3, 5, 8, 12, 17, ?", "23", "Medium", ["23"]),
("Complete: 81, 27, 9, 3, ?", "1", "Easy", ["1"]),
("Complete: 1, 4, 9, 16, 25, ?", "36", "Easy", ["36"]),
("Complete: 7, 10, 16, 25, 37, ?", "52", "Hard", ["52"]),
("Complete: 5, 10, 20, 40, ?", "80", "Easy", ["80"]),
("Complete: 2, 5, 10, 17, 26, ?", "37", "Medium", ["37"]),
],

"Panic": [
("What is the capital of Australia?", "canberra", "Panic", ["canberra"]),
("How many sides does a hexagon have?", "6", "Panic", ["6", "six"]),
("Which planet is known as the Red Planet?", "mars", "Panic", ["mars"]),
("What is 15 × 4?", "60", "Panic", ["60"]),
("Which gas do humans need to breathe?", "oxygen", "Panic", ["oxygen"]),
("What is the largest ocean?", "pacific", "Panic", ["pacific", "pacific ocean"]),
("How many continents are there?", "7", "Panic", ["7", "seven"]),
("Which metal has the chemical symbol Fe?", "iron", "Panic", ["iron"]),
("What is the square root of 144?", "12", "Panic", ["12", "twelve"]),
("Which instrument has 88 keys?", "piano", "Panic", ["piano"]),
],

"Bluff Master": [
("Which statement is FALSE? A) Octopuses have three hearts. B) Bats are blind. C) Honey can last a very long time.", "b", "Hard", ["b", "bats are blind", "bats"]),
("Which statement is FALSE? A) Lightning can strike the same place twice. B) Goldfish have a 3-second memory. C) Bananas are berries botanically.", "b", "Medium", ["b", "goldfish", "3 second"]),
("Which statement is FALSE? A) Venus rotates slowly. B) Sharks are mammals. C) Water can exist as solid, liquid and gas.", "b", "Easy", ["b", "sharks are mammals"]),
("Which statement is FALSE? A) The Moon has no atmosphere like Earth's. B) Sound travels faster in water than air. C) Humans can breathe underwater naturally.", "c", "Easy", ["c", "humans can breathe underwater"]),
("Which statement is FALSE? A) A day on Venus is longer than its year. B) Mercury is the hottest planet. C) Jupiter is the largest planet.", "b", "Hard", ["b", "mercury is the hottest"]),
("Which statement is FALSE? A) Some turtles can breathe through skin. B) Penguins live only in Antarctica. C) Crows can use tools.", "b", "Medium", ["b", "penguins live only in antarctica"]),
("Which statement is FALSE? A) Humans share DNA with bananas. B) DNA is found in cells. C) Humans have no DNA in their blood.", "c", "Hard", ["c", "humans have no dna"]),
("Which statement is FALSE? A) Sharks existed before trees. B) Dinosaurs lived before humans. C) Humans and dinosaurs lived together naturally.", "c", "Easy", ["c", "humans and dinosaurs"]),
("Which statement is FALSE? A) Water expands when it freezes. B) Ice is less dense than liquid water. C) Ice always sinks in water.", "c", "Medium", ["c", "ice always sinks"]),
("Which statement is FALSE? A) Lightning is extremely hot. B) Thunder is caused by lightning heating air. C) Thunder is produced by clouds rubbing together.", "c", "Hard", ["c", "clouds rubbing"]),
],

"Risk It": [
("Which number is prime: 21, 29, 35 or 39?", "29", "Medium", ["29"]),
("What is 17 × 3?", "51", "Hard", ["51"]),
("Which planet has the most famous ring system?", "saturn", "Easy", ["saturn"]),
("What is the chemical symbol for sodium?", "na", "Medium", ["na", "sodium"]),
("Which country has the city of Kyoto?", "japan", "Easy", ["japan"]),
("What is 144 ÷ 12?", "12", "Easy", ["12"]),
("Which element has atomic number 6?", "carbon", "Hard", ["carbon"]),
("What is 19²?", "361", "Hard", ["361"]),
("Which ocean lies between Africa and Australia?", "indian", "Medium", ["indian", "indian ocean"]),
("Which number is both a square and a cube?", "64", "Extreme", ["64"]),
],

"Memory Bomb": [
("Remember: 4 - 9 - 2 - 7. What was the SECOND number?", "9", "Medium", ["9"]),
("Remember: RED - BLUE - GREEN - GOLD. What was the LAST word?", "gold", "Easy", ["gold"]),
("Remember: 17 - 31 - 44 - 58. What was the THIRD number?", "44", "Medium", ["44"]),
("Remember: MARS - VENUS - EARTH - SATURN. What was the SECOND planet?", "venus", "Easy", ["venus"]),
("Remember: 8 - 3 - 6 - 1 - 9. What was the FOURTH number?", "1", "Medium", ["1"]),
("Remember: ALPHA - DELTA - GAMMA - OMEGA. What was the FIRST word?", "alpha", "Easy", ["alpha"]),
("Remember: 22 - 41 - 13 - 77 - 5. What was the FIFTH number?", "5", "Hard", ["5"]),
("Remember: TIGER - EAGLE - WOLF - PANDA. What was the THIRD animal?", "wolf", "Medium", ["wolf"]),
("Remember: 91 - 14 - 63 - 28. Which number came immediately after 14?", "63", "Hard", ["63"]),
("Remember: JAVA - PYTHON - RUST - GO. Which language came before GO?", "rust", "Hard", ["rust"]),
],

"One Word Chaos": [
("What do you call fear of spiders?", "arachnophobia", "Medium", ["arachnophobia"]),
("What is the fastest land animal?", "cheetah", "Easy", ["cheetah"]),
("What is the opposite of inflation?", "deflation", "Hard", ["deflation"]),
("What is the hardest natural substance?", "diamond", "Easy", ["diamond"]),
("Which blood type is commonly called the universal donor?", "o negative", "Medium", ["o negative", "o-"]),
("Which planet has the shortest year?", "mercury", "Medium", ["mercury"]),
("What is the study of earthquakes called?", "seismology", "Hard", ["seismology"]),
("Which language has the most native speakers?", "mandarin", "Hard", ["mandarin", "chinese"]),
("What is the largest internal organ in humans?", "liver", "Medium", ["liver"]),
("Which vitamin is mainly produced through sunlight exposure?", "d", "Easy", ["d", "vitamin d"]),
],

"Target Number": [
("Use +, −, × or ÷: make 24 from 6, 4, 2.", "6*4", "Medium", ["24", "6*4", "6 x 4"]),
("What number added to 37 gives 100?", "63", "Easy", ["63"]),
("What is 12 × 12?", "144", "Easy", ["144"]),
("What is 250 − 87?", "163", "Medium", ["163"]),
("What is 15 × 7?", "105", "Medium", ["105"]),
("What is 999 + 1?", "1000", "Easy", ["1000", "one thousand"]),
("What is 18²?", "324", "Hard", ["324"]),
("What is 720 ÷ 9?", "80", "Medium", ["80"]),
("What is 2⁵?", "32", "Medium", ["32"]),
("What is 45% of 200?", "90", "Medium", ["90"]),
],

"Mystery Power": [
("A superhero can freeze water with a glance. What physical process is being accelerated?", "freezing", "Medium", ["freezing"]),
("If you could see infrared radiation, what would warm objects generally appear to emit strongly?", "heat", "Medium", ["heat"]),
("A character becomes invisible but still casts a shadow. What is the biggest clue that the power has a flaw?", "light", "Hard", ["light"]),
("A machine doubles every number you enter. What happens to 7?", "14", "Easy", ["14"]),
("A device reverses gravity for 3 seconds. What direction would you expect an object to accelerate?", "up", "Medium", ["up", "upward"]),
("A fictional suit absorbs sunlight and stores energy. What real-world technology is most related?", "solar cell", "Hard", ["solar cell", "solar panel", "solar"]),
("A character can hear frequencies humans normally cannot. What ability is this?", "ultrasound", "Hard", ["ultrasound", "ultrasonic"]),
("A machine predicts tomorrow's temperature perfectly. What type of data would it need most directly?", "weather", "Easy", ["weather", "weather data"]),
("A fictional crystal glows only when electricity passes through it. What phenomenon is being used?", "electroluminescence", "Extreme", ["electroluminescence"]),
("A robot learns from rewards and penalties. What broad AI concept does this resemble?", "reinforcement learning", "Hard", ["reinforcement learning"]),
],

"Sabotage Round": [
("A man shaves several times a day but still has a beard. Who is he?", "barber", "Medium", ["barber"]),
("You are in a room with no windows or doors. How do you get out?", "stop imagining", "Hard", ["stop imagining", "imagination"]),
("A word becomes shorter when you add two letters. What word?", "short", "Hard", ["short"]),
("What can travel around the world while staying in one corner?", "stamp", "Easy", ["stamp"]),
("What has many teeth but cannot bite?", "comb", "Easy", ["comb"]),
("What has a neck but no head?", "bottle", "Easy", ["bottle"]),
("What has words but never speaks?", "book", "Easy", ["book"]),
("What has an eye but cannot see and is useful for sewing?", "needle", "Easy", ["needle"]),
("What has four wheels and flies?", "garbage truck", "Medium", ["garbage truck"]),
("What can you catch but never throw?", "cold", "Easy", ["cold"]),
],

"Buzzer Battle": [
("Which planet is closest to the Sun?", "mercury", "Easy", ["mercury"]),
("Who painted the Mona Lisa?", "leonardo da vinci", "Easy", ["leonardo da vinci", "da vinci"]),
("What is the capital of Canada?", "ottawa", "Medium", ["ottawa"]),
("What is the chemical symbol for gold?", "au", "Medium", ["au"]),
("Which is the largest planet?", "jupiter", "Easy", ["jupiter"]),
("How many bones are in the adult human body approximately?", "206", "Medium", ["206"]),
("Which country gifted the Statue of Liberty to the United States?", "france", "Easy", ["france"]),
("What is the smallest prime number?", "2", "Easy", ["2"]),
("Which scientist developed the theory of relativity?", "einstein", "Easy", ["einstein", "albert einstein"]),
("What is the deepest ocean trench called?", "mariana trench", "Hard", ["mariana trench"]),
],

"CHAOS MODE": [
("Which came first: the chicken or the egg? In evolutionary terms, what is the better answer?", "egg", "Hard", ["egg"]),
("If you drop a feather and a hammer in a vacuum, which reaches the ground first?", "same time", "Hard", ["same time", "together"]),
("What is heavier: 1 kg of iron or 1 kg of feathers?", "same", "Easy", ["same", "equal"]),
("If a mirror reverses left and right, why doesn't it reverse up and down?", "depth", "Extreme", ["depth", "it reverses front back"]),
("Which is technically a berry: strawberry or banana?", "banana", "Hard", ["banana"]),
("What color is a black hole?", "black", "Easy", ["black"]),
("If Earth suddenly stopped rotating, would you feel it immediately?", "yes", "Extreme", ["yes"]),
("Can sound travel through empty space?", "no", "Easy", ["no"]),
("What is faster: light or sound?", "light", "Easy", ["light"]),
("If you are moving at constant velocity, is there a net force?", "no", "Hard", ["no"]),
],

"King of the Hill": [
("Which number is NOT prime: 17, 19, 21, 23?", "21", "Easy", ["21"]),
("What is 13 × 13?", "169", "Medium", ["169"]),
("Which country has the largest land area?", "russia", "Easy", ["russia"]),
("What is the freezing point of water in Celsius?", "0", "Easy", ["0", "zero"]),
("Which organ pumps blood through the body?", "heart", "Easy", ["heart"]),
("What is the capital of Japan?", "tokyo", "Easy", ["tokyo"]),
("Which planet rotates on its side most dramatically?", "uranus", "Hard", ["uranus"]),
("What is the square root of 225?", "15", "Medium", ["15"]),
("Which element has the symbol K?", "potassium", "Hard", ["potassium"]),
("What is the largest desert on Earth?", "antarctica", "Extreme", ["antarctica", "antarctic desert"]),
],
}


# ============================================================
# QUESTION PROCESSING
# ============================================================

def normalize(text):
    text = text.lower().strip()
    text = text.replace("’", "'")
    text = text.replace("×", "x")
    text = text.replace("−", "-")
    text = text.replace("°", "")
    text = text.replace(",", "")
    text = " ".join(text.split())

    for ch in ["?", "!", ".", ":", ";", "(", ")", "[", "]"]:
        text = text.replace(ch, "")

    return text


def question_key(q):
    return (
        q["mode"],
        q["difficulty"],
        q["q"],
    )


def build_questions():
    all_questions = {}

    for mode, rows in RAW_QUESTIONS.items():
        all_questions[mode] = []

        for q, answer, difficulty, aliases in rows:
            all_questions[mode].append({
                "mode": mode,
                "q": q,
                "answer": answer,
                "difficulty": difficulty,
                "aliases": aliases,
            })

    return all_questions


QUESTIONS = build_questions()


def pool_for(mode, difficulty):
    pool = QUESTIONS.get(mode, [])

    if difficulty == "Any":
        return pool

    exact = [
        q for q in pool
        if q["difficulty"] == difficulty
        or (difficulty == "Extreme" and q["difficulty"] == "Hard")
        or (difficulty == "Panic" and q["difficulty"] == "Panic")
    ]

    return exact or pool


def choose_question(mode, difficulty, used):
    pool = pool_for(mode, difficulty)

    available = [
        q for q in pool
        if question_key(q) not in used
    ]

    if not available:
        used.clear()
        available = pool[:]

    q = random.choice(available)
    used.add(question_key(q))

    return q


def is_correct(user_answer, q):
    normalized = normalize(user_answer)

    valid = {
        normalize(q["answer"])
    }

    valid.update(
        normalize(x)
        for x in q.get("aliases", [])
    )

    # Numeric shortcuts
    if normalized.endswith(" degrees"):
        normalized = normalized[:-8].strip()

    return normalized in valid


# ============================================================
# PLAYER SYSTEM
# ============================================================

def ensure_player(chat_id, user):
    name = user.full_name or user.username or "Player"

    with db() as con:
        con.execute("""
            INSERT INTO players(chat_id,user_id,name)
            VALUES(?,?,?)
            ON CONFLICT(chat_id,user_id)
            DO UPDATE SET name=excluded.name
        """, (chat_id, user.id, name))


def get_player(chat_id, user_id):
    with db() as con:
        return con.execute("""
            SELECT chat_id,user_id,name,xp,wins,streak,
                   best_streak,games,hints,achievements
            FROM players
            WHERE chat_id=? AND user_id=?
        """, (chat_id, user_id)).fetchone()


def add_win(chat_id, user_id, name, xp):
    ensure_player(chat_id, type(
        "U", (), {
            "id": user_id,
            "full_name": name,
            "username": name
        }
    )())

    with db() as con:
        row = con.execute("""
            SELECT streak,best_streak
            FROM players
            WHERE chat_id=? AND user_id=?
        """, (chat_id, user_id)).fetchone()

        streak = (row[0] if row else 0) + 1
        best = max(row[1] if row else 0, streak)

        con.execute("""
            UPDATE players
            SET xp=xp+?,
                wins=wins+1,
                games=games+1,
                streak=?,
                best_streak=?
            WHERE chat_id=? AND user_id=?
        """, (
            xp,
            streak,
            best,
            chat_id,
            user_id,
        ))

        return streak, best


def add_timeout(chat_id, user_id):
    with db() as con:
        con.execute("""
            UPDATE players
            SET games=games+1,
                streak=0
            WHERE chat_id=? AND user_id=?
        """, (chat_id, user_id))


def add_wrong_streak_break(chat_id, user_id):
    with db() as con:
        con.execute("""
            UPDATE players
            SET streak=0
            WHERE chat_id=? AND user_id=?
        """, (chat_id, user_id))


def level_from_xp(xp):
    return (xp // 100) + 1


def title_from_level(level):
    if level >= 30:
        return "🏆 Arena Legend"
    if level >= 20:
        return "👑 Arena King"
    if level >= 15:
        return "🔥 Arena Beast"
    if level >= 10:
        return "⚡ Arena Veteran"
    if level >= 5:
        return "🎯 Arena Fighter"

    return "🌱 Arena Rookie"


# ============================================================
# FUN REACTIONS
# ============================================================

WRONG_ROASTS = [
    "😂 Confidence toh IAS level ka tha, answer nursery ka nikla.",
    "💀 Bhai answer ne khud tumse distance bana liya.",
    "🧠 Brain online tha... bas correct server se connect nahi hua.",
    "😂 Ye answer dekh ke question bhi confused ho gaya.",
    "📉 Accuracy ne abhi resignation submit kiya hai.",
    "🤣 Itna confidence galat jagah invest kar diya!",
    "💀 Calculator hota toh shayad calculator bhi sochta.",
    "😂 Bro chose violence against logic.",
    "🫠 Dimaag ne bola 'main nahi jaanta, tu bhej de'.",
    "🤣 Ye answer dekhkar Google bhi 2 minute silent raha.",
    "💀 Galat... lekin confidence respect-worthy tha.",
    "😂 Tumhara answer aur correct answer ek hi planet pe nahi rehte.",
    "🧠 Processing... ERROR 404: logic not found.",
    "🤣 Aaj knowledge vacation pe hai kya?",
    "💀 Answer galat hai, attitude sahi tha.",
]

CORRECT_REACTIONS = [
    "🔥 BOOM! Correct!",
    "🧠 Brain officially online!",
    "👑 Arena mein ek aur victim... question ka. Correct!",
    "⚡ Lightning-fast brain!",
    "🎯 Direct hit!",
    "🔥 Ye hui na baat!",
    "🗿 Calm. Calculated. Correct.",
    "💯 Knowledge ne attendance laga di!",
    "🚀 Straight to the leaderboard!",
    "😂 Question ko laga tha bach jayega. Nahi bacha.",
]

TIMEOUT_REACTIONS = [
    "💀 TIME OVER! Brain buffering mein hi reh gaya.",
    "⏰ Khatam. Ghadi ne mercy nahi dikhayi 😂",
    "💀 Timer ne bola: 'Bas bhai, ab ghar ja.'",
    "⌛ Time up! Answer ab reveal hoga.",
    "😂 Dimaag ne loading complete ki... timer pehle hi chala gaya.",
    "🚨 TIMEOUT! Knowledge thi, speed nahi thi.",
    "💀 Question ab tumhe roast karne wala hai.",
]

LATE_REACTIONS = [
    "⏰ Too late! Round already lock ho chuka hai 😂",
    "💀 Bhai buzzer baj chuka. Ab answer ka koi value nahi.",
    "😂 Late entry allowed nahi hai, ye railway platform nahi.",
    "🚫 Round closed! Agli baar speed dikhao.",
]


# ============================================================
# MENUS
# ============================================================

MODES = [
    ("🧩", "Word"),
    ("🐾", "Animal"),
    ("😀", "Emoji"),
    ("🌍", "City"),
    ("🧠", "Riddle"),
    ("🔐", "Logic"),
    ("🎭", "Trick"),
    ("🔢", "Pattern"),
    ("💀", "Panic"),
    ("🎩", "Bluff Master"),
    ("🎲", "Risk It"),
    ("💣", "Memory Bomb"),
    ("🌪️", "One Word Chaos"),
    ("🎯", "Target Number"),
    ("⚡", "Mystery Power"),
    ("🕵️", "Sabotage Round"),
    ("🔔", "Buzzer Battle"),
    ("🌋", "CHAOS MODE"),
    ("👑", "King of the Hill"),
]


def main_menu():
    buttons = []

    for icon, mode in MODES:
        buttons.append([
            InlineKeyboardButton(
                f"{icon} {mode}",
                callback_data=f"mode:{mode}"
            )
        ])

    buttons.extend([
        [
            InlineKeyboardButton("🎮 Random Mode", callback_data="random_mode"),
            InlineKeyboardButton("🔥 Daily", callback_data="daily"),
        ],
        [
            InlineKeyboardButton("👤 Profile", callback_data="profile"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
        ],
        [
            InlineKeyboardButton("🏅 Achievements", callback_data="achievements"),
            InlineKeyboardButton("ℹ️ Help", callback_data="help"),
        ],
    ])

    return InlineKeyboardMarkup(buttons)


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
            InlineKeyboardButton("🎲 Any", callback_data=f"diff:{mode}:Any"),
            InlineKeyboardButton("💀 Panic 8s", callback_data=f"diff:{mode}:Panic"),
        ],
        [
            InlineKeyboardButton("🏠 Home", callback_data="menu:home")
        ],
    ])


# ============================================================
# TIMER CONTROL
# ============================================================

def cancel_panic_task(chat_id):
    task = panic_tasks.pop(chat_id, None)

    if task and not task.done():
        task.cancel()


async def countdown(chat_id, bot, round_id):
    try:
        game = active.get(chat_id)

        if not game or game["round_id"] != round_id:
            return

        seconds = game["seconds"]

        timer_message = await bot.send_message(
            chat_id=chat_id,
            text=f"⏳ <b>{seconds}s</b>",
            parse_mode="HTML",
        )

        for remaining in range(seconds - 1, 0, -1):
            await asyncio.sleep(1)

            game = active.get(chat_id)

            if (
                not game
                or game["round_id"] != round_id
                or game.get("closed")
            ):
                return

            try:
                await timer_message.edit_text(
                    f"⏳ <b>{remaining}s</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass

        await asyncio.sleep(1)

        game = active.get(chat_id)

        if (
            not game
            or game["round_id"] != round_id
            or game.get("closed")
        ):
            return

        game["closed"] = True

        mode = game["mode"]
        q = game["question"]

        player = game.get("player_id")

        if player:
            add_timeout(chat_id, player)

        active.pop(chat_id, None)

        try:
            await timer_message.edit_text(
                "💀 <b>TIME OVER!</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass

        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"{random.choice(TIMEOUT_REACTIONS)}\n\n"
                f"🧩 <b>Answer:</b> "
                f"<code>{html.escape(q['answer'])}</code>\n\n"
                f"🚫 <b>0 XP</b> — speed bhi game ka part hai."
            ),
            parse_mode="HTML",
        )

    except asyncio.CancelledError:
        return

    except Exception:
        active.pop(chat_id, None)

    finally:
        if panic_tasks.get(chat_id) is asyncio.current_task():
            panic_tasks.pop(chat_id, None)


# ============================================================
# ROUND ENGINE
# ============================================================

async def send_round(
    bot,
    chat_id,
    mode,
    difficulty,
    used=None,
    daily=False,
    player_id=None,
):
    cancel_panic_task(chat_id)

    if used is None:
        used = set()

    q = choose_question(mode, difficulty, used)

    seconds = TIMERS.get(
        difficulty,
        TIMERS["Medium"]
    )

    round_id = uuid.uuid4().hex

    active[chat_id] = {
        "round_id": round_id,
        "mode": mode,
        "difficulty": difficulty,
        "question": q,
        "used": used,
        "seconds": seconds,
        "daily": daily,
        "player_id": player_id,
        "closed": False,
    }

    xp = XP_VALUES.get(
        difficulty,
        XP_VALUES["Medium"]
    )

    icon = dict(MODES).get(mode, "🎮")

    text = (
        f"{icon} <b>{html.escape(mode.upper())}</b>\n"
        f"🔥 Difficulty: <b>{html.escape(difficulty)}</b>\n"
        f"⭐ Reward: <b>+{xp} XP</b>\n\n"
        f"⏱️ <b>{seconds} SECONDS</b>\n"
        f"🧠 <b>READ TWICE. ANSWER ONCE.</b>\n\n"
        f"🧩 <b>{html.escape(q['q'])}</b>\n\n"
        f"✍️ Answer bhejo!"
    )

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
    )

    task = asyncio.create_task(
        countdown(
            chat_id,
            bot,
            round_id,
        )
    )

    panic_tasks[chat_id] = task


# ============================================================
# COMMANDS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    ensure_player(chat_id, user)

    cancel_panic_task(chat_id)
    active.pop(chat_id, None)

    name = html.escape(
        user.first_name or "Player"
    )

    text = (
        "🎮 <b>WELCOME TO GUESSARENA</b> 🔥\n\n"
        f"Yo <b>{name}</b>! 👋\n\n"
        "Yahan knowledge ke saath-saath "
        "<b>speed, logic aur thoda pagalpan</b> bhi chahiye. 😂\n\n"
        "🎯 Correct = XP\n"
        "❌ Wrong = roast\n"
        "⏰ Timeout = answer reveal + 0 XP\n"
        "🏆 First correct player = winner\n"
        "🔀 Questions = shuffled + no-repeat\n\n"
        "👇 <b>Apna battlefield choose karo.</b>"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 <b>GUESSARENA — HOW TO PLAY</b>\n\n"
        "1️⃣ Mode choose karo\n"
        "2️⃣ Difficulty choose karo\n"
        "3️⃣ Timer ke andar answer bhejo\n"
        "4️⃣ Correct hua → XP + streak 🔥\n"
        "5️⃣ Wrong hua → roast 😂\n"
        "6️⃣ Time over → answer reveal, 0 XP 💀\n\n"
        "<b>Timers</b>\n"
        "🟢 Easy: 15s\n"
        "🟡 Medium: 15s\n"
        "🔴 Hard: 20s\n"
        "🟣 Extreme: 20s\n"
        "💀 Panic: 8s\n\n"
        "🏆 Group mein jo pehle correct answer deta hai, "
        "usi ko reward milta hai.\n\n"
        "⚠️ Timer ke baad bheja answer count nahi hoga.",
        parse_mode="HTML",
    )


# ============================================================
# PROFILE
# ============================================================

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    ensure_player(chat_id, user)
    row = get_player(chat_id, user.id)

    if not row:
        return

    (
        _,
        _,
        name,
        xp,
        wins,
        streak,
        best,
        games,
        hints,
        achievements,
    ) = row

    level = level_from_xp(xp)
    title = title_from_level(level)

    accuracy = (
        round((wins / games) * 100, 1)
        if games else 0
    )

    text = (
        f"👤 <b>{html.escape(name)}</b>\n\n"
        f"{title}\n"
        f"⭐ XP: <b>{xp}</b>\n"
        f"🎚️ Level: <b>{level}</b>\n"
        f"🏆 Wins: <b>{wins}</b>\n"
        f"🎮 Resolved Rounds: <b>{games}</b>\n"
        f"🎯 Accuracy: <b>{accuracy}%</b>\n"
        f"🔥 Current Streak: <b>{streak}</b>\n"
        f"👑 Best Streak: <b>{best}</b>\n"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


# ============================================================
# LEADERBOARD
# ============================================================

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    with db() as con:
        rows = con.execute("""
            SELECT name,xp,wins,streak
            FROM players
            WHERE chat_id=?
            ORDER BY xp DESC
            LIMIT 10
        """, (chat_id,)).fetchall()

    if not rows:
        await update.message.reply_text(
            "🏆 Abhi leaderboard khaali hai."
        )
        return

    medals = ["🥇", "🥈", "🥉"]

    lines = [
        "🏆 <b>GUESSARENA LEADERBOARD</b>\n"
    ]

    for i, row in enumerate(rows):
        name, xp, wins, streak = row

        prefix = (
            medals[i]
            if i < 3
            else f"<b>{i+1}.</b>"
        )

        lines.append(
            f"{prefix} {html.escape(name)} — "
            f"<b>{xp} XP</b> "
            f"({wins} wins, 🔥{streak})"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ============================================================
# ACHIEVEMENTS
# ============================================================

async def achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    row = get_player(chat_id, user.id)

    if not row:
        return

    xp = row[3]
    wins = row[4]
    best = row[6]

    unlocked = []

    if wins >= 1:
        unlocked.append("🎯 First Blood")

    if wins >= 10:
        unlocked.append("🔥 Getting Serious")

    if wins >= 25:
        unlocked.append("⚡ Arena Addict")

    if best >= 5:
        unlocked.append("👑 Streak Machine")

    if xp >= 1000:
        unlocked.append("💎 XP Monster")

    if not unlocked:
        unlocked.append(
            "🔒 No achievement yet — go cause some chaos."
        )

    await update.message.reply_text(
        "🏅 <b>ACHIEVEMENTS</b>\n\n"
        + "\n".join(unlocked),
        parse_mode="HTML",
    )


# ============================================================
# DAILY
# ============================================================

async def daily_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id in active:
        await update.message.reply_text(
            "😂 Pehle current round finish karo."
        )
        return

    # Deterministic daily selection
    random.seed(
        f"{date.today().isoformat()}:{chat_id}"
    )

    mode = random.choice(list(QUESTIONS.keys()))

    random.seed()

    used = set()

    await send_round(
        context.bot,
        chat_id,
        mode,
        "Hard",
        used=used,
        daily=True,
        player_id=update.effective_user.id,
    )


# ============================================================
# BUTTON HANDLER
# ============================================================

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    user = query.from_user

    ensure_player(chat_id, user)

    data = query.data or ""

    # HOME
    if data == "menu:home":
        cancel_panic_task(chat_id)
        active.pop(chat_id, None)

        await query.message.reply_text(
            "🏠 <b>GUESSARENA HOME</b>\n\n"
            "Round closed. No ghosts left behind. 👻😂\n\n"
            "👇 Choose your next mode.",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        return

    # PROFILE
    if data == "profile":
        row = get_player(chat_id, user.id)

        if not row:
            return

        (
            _,
            _,
            name,
            xp,
            wins,
            streak,
            best,
            games,
            hints,
            achievements_text,
        ) = row

        level = level_from_xp(xp)
        title = title_from_level(level)

        accuracy = (
            round((wins / games) * 100, 1)
            if games else 0
        )

        await query.message.reply_text(
            f"👤 <b>{html.escape(name)}</b>\n\n"
            f"{title}\n"
            f"⭐ XP: <b>{xp}</b>\n"
            f"🎚️ Level: <b>{level}</b>\n"
            f"🏆 Wins: <b>{wins}</b>\n"
            f"🎯 Accuracy: <b>{accuracy}%</b>\n"
            f"🔥 Streak: <b>{streak}</b>\n"
            f"👑 Best: <b>{best}</b>",
            parse_mode="HTML",
        )
        return

    # LEADERBOARD
    if data == "leaderboard":
        with db() as con:
            rows = con.execute("""
                SELECT name,xp,wins,streak
                FROM players
                WHERE chat_id=?
                ORDER BY xp DESC
                LIMIT 10
            """, (chat_id,)).fetchall()

        if not rows:
            await query.message.reply_text(
                "🏆 Leaderboard abhi khaali hai."
            )
            return

        medals = ["🥇", "🥈", "🥉"]

        lines = [
            "🏆 <b>LEADERBOARD</b>\n"
        ]

        for i, row in enumerate(rows):
            name, xp, wins, streak = row

            prefix = (
                medals[i]
                if i < 3
                else f"{i+1}."
            )

            lines.append(
                f"{prefix} <b>{html.escape(name)}</b> — "
                f"{xp} XP"
            )

        await query.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
        )
        return

    # ACHIEVEMENTS
    if data == "achievements":
        await achievements(
            Update(update.update_id, message=query.message),
            context,
        )
        return

    # HELP
    if data == "help":
        await query.message.reply_text(
            "ℹ️ <b>HOW TO PLAY</b>\n\n"
            "🎯 Correct = XP\n"
            "😂 Wrong = roast\n"
            "⏰ Time over = answer reveal\n"
            "🚫 Late answer = 0 XP\n"
            "🔀 No-repeat shuffle\n\n"
            "🟢 Easy 15s\n"
            "🟡 Medium 15s\n"
            "🔴 Hard 20s\n"
            "🟣 Extreme 20s\n"
            "💀 Panic 8s",
            parse_mode="HTML",
        )
        return

    # RANDOM MODE
    if data == "random_mode":
        if chat_id in active:
            await query.message.reply_text(
                "😂 Current round abhi zinda hai!"
            )
            return

        mode = random.choice(list(QUESTIONS.keys()))

        await query.message.reply_text(
            f"🎲 <b>RANDOM MODE</b>\n\n"
            f"Tonight's victim: <b>{html.escape(mode)}</b> 😂\n\n"
            f"Difficulty choose karo:",
            parse_mode="HTML",
            reply_markup=difficulty_menu(mode),
        )
        return

    # DAILY
    if data == "daily":
        if chat_id in active:
            await query.message.reply_text(
                "😂 Pehle current round finish karo."
            )
            return

        random.seed(
            f"{date.today().isoformat()}:{chat_id}"
        )

        mode = random.choice(list(QUESTIONS.keys()))

        random.seed()

        await query.message.reply_text(
            f"🔥 <b>DAILY CHALLENGE</b>\n\n"
            f"Today's battlefield: <b>{html.escape(mode)}</b>\n"
            f"One chance. No excuses. 😂",
            parse_mode="HTML",
        )

        await send_round(
            context.bot,
            chat_id,
            mode,
            "Hard",
            used=set(),
            daily=True,
            player_id=user.id,
        )
        return

    # MODE SELECTED
    if data.startswith("mode:"):
        mode = data.split(":", 1)[1]

        if mode not in QUESTIONS:
            return

        if chat_id in active:
            await query.message.reply_text(
                "😂 Bhai ek time pe ek hi battlefield! "
                "Current round pehle finish karo."
            )
            return

        await query.message.reply_text(
            f"🎮 <b>{html.escape(mode.upper())}</b>\n\n"
            f"Difficulty choose karo.\n"
            f"Har level ka apna timer + XP hai 🔥",
            parse_mode="HTML",
            reply_markup=difficulty_menu(mode),
        )
        return

    # DIFFICULTY
    if data.startswith("diff:"):
        parts = data.split(":")

        if len(parts) != 3:
            return

        mode = parts[1]
        difficulty = parts[2]

        if mode not in QUESTIONS:
            return

        if difficulty not in TIMERS and difficulty != "Any":
            return

        if chat_id in active:
            await query.message.reply_text(
                "😂 Round already running!"
            )
            return

        await send_round(
            context.bot,
            chat_id,
            mode,
            difficulty,
            used=set(),
            daily=False,
            player_id=user.id,
        )

        return


# ============================================================
# ANSWER HANDLER
# ============================================================

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    text = update.message.text or ""

    game = active.get(chat_id)

    # No active game
    if not game:
        return

    # Round already closed
    if game.get("closed"):
        await update.message.reply_text(
            random.choice(LATE_REACTIONS)
        )
        return

    q = game["question"]

    # Correct answer
    if is_correct(text, q):

        game["closed"] = True

        round_id = game["round_id"]
        mode = game["mode"]
        difficulty = game["difficulty"]
        daily = game.get("daily", False)

        cancel_panic_task(chat_id)
        active.pop(chat_id, None)

        xp = XP_VALUES.get(
            difficulty,
            XP_VALUES["Medium"]
        )

        if daily:
            xp += 25

        name = user.full_name or user.username or "Player"

        streak, best = add_win(
            chat_id,
            user.id,
            name,
            xp,
        )

        level = level_from_xp(
            get_player(chat_id, user.id)[3]
        )

        bonus = ""

        if streak >= 3:
            bonus = (
                f"\n🔥 <b>{streak} STREAK!</b>"
            )

        if daily:
            bonus += "\n🌟 Daily bonus included!"

        await update.message.reply_text(
            f"{random.choice(CORRECT_REACTIONS)}\n\n"
            f"👑 <b>{html.escape(name)}</b>\n"
            f"⭐ <b>+{xp} XP</b>\n"
            f"🎚️ Level: <b>{level}</b>"
            f"{bonus}\n\n"
            f"🧩 Answer: <code>{html.escape(q['answer'])}</code>",
            parse_mode="HTML",
        )

        return

    # Wrong answer
    add_wrong_streak_break(
        chat_id,
        user.id,
    )

    await update.message.reply_text(
        random.choice(WRONG_ROASTS),
        parse_mode="HTML",
    )


# ============================================================
# GAME COMMAND
# ============================================================

async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id in active:
        await update.message.reply_text(
            "😂 Current round already running!"
        )
        return

    await update.message.reply_text(
        "🎮 <b>GUESSARENA</b>\n\n"
        "Choose your battlefield 👇",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update, context):
    print("GuessArena error:", context.error)


# ============================================================
# MAIN
# ============================================================

def main():
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    request = HTTPXRequest(
        connect_timeout=30,
        read_timeout=30,
        write_timeout=30,
        pool_timeout=30,
    )

    application = (
        Application.builder()
        .token(TOKEN)
        .request(request)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_cmd)
    )

    application.add_handler(
        CommandHandler("game", game_command)
    )

    application.add_handler(
        CommandHandler("profile", profile)
    )

    application.add_handler(
        CommandHandler("leaderboard", leaderboard)
    )

    application.add_handler(
        CommandHandler("achievements", achievements)
    )

    application.add_handler(
        CommandHandler("daily", daily_challenge)
    )

    application.add_handler(
        CallbackQueryHandler(button)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            answer,
        )
    )

    application.add_error_handler(
        error_handler
    )

    print("🔥 GuessArena is running...")

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
