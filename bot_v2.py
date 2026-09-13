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
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# ============================================================
# GUESSARENA v2 - FULL BUILD
# ============================================================
# Keep Flask/Render health server unchanged.
# One file: paste this entire file as bot_v2.py
# ============================================================

app = Flask(__name__)

@app.route("/")
def health_check():
    return "Bot is Alive!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    print(f"[GuessArena] Health server starting on 0.0.0.0:{port}", flush=True)
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )

server_thread = Thread(target=run_web_server, daemon=True)
server_thread.start()

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
    "Medium": 20,
    "Hard": 35,
    "Extreme": 55,
    "Panic": 70,
}

MODE_EMOJI = {
    "Word": "🔤", "Animal": "🦁", "Emoji": "😂", "City": "🌍",
    "Riddle": "🧩", "Logic": "🧠", "Trick": "🎭", "Pattern": "🔢",
    "Panic": "🚨", "Bluff Master": "🃏", "Risk It": "🎲", "Memory Bomb": "💣",
    "One Word Chaos": "☝️", "Target Number": "🎯", "Mystery Power": "⚡",
    "Sabotage Round": "😈", "Buzzer Battle": "🔔", "CHAOS MODE": "🌪️",
    "King of the Hill": "👑",
}

DIFFICULTIES = ["Easy", "Medium", "Hard", "Extreme", "Panic"]

# ============================================================
# DATABASE
# ============================================================

def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
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
            hints INTEGER DEFAULT 3,
            achievements TEXT DEFAULT '',
            PRIMARY KEY(chat_id,user_id)
        )
    """)
    con.commit()
    con.close()


def ensure_player(chat_id, user_id, name):
    con = db()
    con.execute("""
        INSERT OR IGNORE INTO players(chat_id,user_id,name)
        VALUES(?,?,?)
    """, (chat_id, user_id, name))
    con.execute("UPDATE players SET name=? WHERE chat_id=? AND user_id=?", (name, chat_id, user_id))
    con.commit()
    con.close()


def get_player(chat_id, user_id):
    ensure_player(chat_id, user_id, "Player")
    con = db()
    row = con.execute("SELECT * FROM players WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
    con.close()
    return row


def add_result(chat_id, user_id, name, xp=0, win=False, reset_streak=False):
    ensure_player(chat_id, user_id, name)
    con = db()
    if win:
        con.execute("""
            UPDATE players SET xp=xp+?, wins=wins+1, games=games+1,
            streak=streak+1,
            best_streak=MAX(best_streak, streak+1)
            WHERE chat_id=? AND user_id=?
        """, (xp, chat_id, user_id))
    elif reset_streak:
        con.execute("UPDATE players SET games=games+1, streak=0 WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    else:
        con.execute("UPDATE players SET games=games+1 WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    con.commit()
    con.close()


def spend_hint(chat_id, user_id):
    con = db()
    row = con.execute("SELECT hints FROM players WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
    if not row or row["hints"] <= 0:
        con.close()
        return False
    con.execute("UPDATE players SET hints=hints-1 WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    con.commit()
    con.close()
    return True


def add_hint(chat_id, user_id, amount=1):
    con = db()
    con.execute("UPDATE players SET hints=hints+? WHERE chat_id=? AND user_id=?", (amount, chat_id, user_id))
    con.commit()
    con.close()


def set_achievement(chat_id, user_id, achievement):
    row = get_player(chat_id, user_id)
    current = set(filter(None, (row["achievements"] or "").split(",")))
    if achievement in current:
        return False
    current.add(achievement)
    con = db()
    con.execute("UPDATE players SET achievements=? WHERE chat_id=? AND user_id=?", (",".join(sorted(current)), chat_id, user_id))
    con.commit()
    con.close()
    return True


def level_from_xp(xp):
    return max(1, xp // 100 + 1)


def title_from_level(level):
    titles = [
        (1, "Rookie"), (3, "Scout"), (5, "Challenger"), (8, "Strategist"),
        (12, "Arena Ace"), (16, "Mind Bender"), (20, "Chaos Lord"), (25, "GuessArena Legend")
    ]
    title = titles[0][1]
    for needed, name in titles:
        if level >= needed:
            title = name
    return title

# ============================================================
# QUESTION BANK
# ============================================================
# Each item can contain aliases, hint and explanation.
# The bank is deliberately mixed so difficulty filtering stays fun.


def Q(q, a, difficulty="Medium", aliases=None, hint="", explain=""):
    return {
        "q": q,
        "a": a,
        "difficulty": difficulty,
        "aliases": aliases or [],
        "hint": hint,
        "explain": explain,
    }

QUESTIONS = {
"Word": [
Q("Which word means 'to make something worse by trying to improve it'?", "exacerbate", "Hard", ["exacerbate"], "It starts with ex- and often appears with problems.", "Exacerbate means to make a problem or situation more severe."),
Q("What is the term for a word that imitates a sound, like 'buzz' or 'clang'?", "onomatopoeia", "Medium", ["onomatopoeia"], "It sounds almost as complicated as it is spelled.", "Onomatopoeia is a word formed to imitate a natural sound."),
Q("What do you call a statement that seems self-contradictory but may reveal a truth?", "paradox", "Medium", ["paradox"], "A classic example involves a liar.", "A paradox contains an apparent contradiction that can be thought-provoking or logically troublesome."),
Q("Which word describes a person who speaks many languages?", "polyglot", "Hard", ["polyglot"], "Poly = many.", "A polyglot knows or uses multiple languages."),
Q("What is the opposite of 'scarce'?", "abundant", "Easy", ["plentiful", "abundance"], "Think: more than enough.", "Abundant means existing in large quantities."),
Q("What word means an extremely strong desire to know or learn something?", "curiosity", "Easy", [], "It is what makes people ask 'why?' five times.", "Curiosity is the desire to know or discover something."),
Q("What is a word with the same spelling but a different meaning called?", "homograph", "Hard", [], "Graph relates to writing.", "Homographs share spelling but can have different meanings or pronunciations."),
Q("What is the term for a newly invented word or expression?", "neologism", "Extreme", [], "Neo means new.", "A neologism is a newly coined word or expression."),
Q("What does 'ambiguous' mean?", "unclear", "Medium", ["uncertain", "having multiple meanings"], "It leaves you thinking: 'Wait, what did you mean?'") ,
Q("What is a person who deliberately avoids society called?", "recluse", "Hard", [], "They prefer their own company.") ,
Q("Which word means 'able to be changed or adapted'?", "flexible", "Easy", ["adaptable"], "Opposite of rigid.") ,
Q("What is the study of word origins called?", "etymology", "Hard", [], "It investigates where words came from.") ,
Q("What does 'meticulous' mean?", "very careful", "Medium", ["careful", "precise", "thorough"], "Someone meticulous notices tiny details.") ,
Q("Which word means a short, clever saying expressing a general truth?", "aphorism", "Hard", [], "Think of a compact piece of wisdom.") ,
Q("What is the fear of confined spaces called?", "claustrophobia", "Medium", ["claustrophobia"], "Think of elevators and tiny rooms.") ,
Q("What does 'obsolete' mean?", "outdated", "Medium", ["out of date"], "It belongs to an older era of technology or practice.") ,
Q("What is the deliberate exaggeration of something for effect called?", "hyperbole", "Medium", [], "'I've told you a million times' is one.") ,
Q("What does 'pragmatic' usually mean?", "practical", "Hard", ["practical-minded"], "It focuses on what actually works.") ,
Q("Which word describes a person who can use both hands equally well?", "ambidextrous", "Hard", [], "Ambi suggests both.") ,
Q("What is a phrase whose literal meaning differs from its intended meaning called?", "idiom", "Easy", [], "'Break a leg' is a famous example.") ,
],
"Animal": [
Q("Which animal has fingerprints so similar to humans that they can be confusing?", "koala", "Medium", [], "It spends much of its life in eucalyptus trees."),
Q("Which mammal is capable of true sustained flight?", "bat", "Easy", ["bats"], "It navigates in darkness using sound."),
Q("What is a group of flamingos commonly called?", "flamboyance", "Hard", [], "The group name is almost suspiciously appropriate."),
Q("Which animal is famous for changing its skin colour using specialized cells?", "chameleon", "Easy", [], "Its camouflage reputation is legendary."),
Q("Which bird can fly backwards?", "hummingbird", "Medium", [], "Its wings beat extremely rapidly."),
Q("Which mammal lays eggs?", "platypus", "Medium", ["echidna"], "Australia has some strange mammals."),
Q("Which animal has three hearts?", "octopus", "Easy", [], "Two help the gills; one serves the body."),
Q("What is the fastest land animal?", "cheetah", "Easy", [], "Short explosive speed is its specialty."),
Q("Which animal has the longest neck among living animals?", "giraffe", "Easy", [], "Its heart has to work hard to move blood upward."),
Q("Which insect communicates partly by performing a famous dance?", "honeybee", "Medium", ["bee", "honey bee"], "It can tell nestmates about food locations."),
Q("Which animal can regenerate lost arms?", "starfish", "Easy", ["sea star"], "Its common name is misleading: it isn't actually a fish."),
Q("Which animal has a tongue that can be longer than its body?", "chameleon", "Hard", [], "Its hunting tongue is famous for speed and reach."),
Q("What is the largest living land animal?", "african elephant", "Easy", ["elephant", "african elephant"], "Think massive ears and a trunk."),
Q("Which animal is known for using tools such as stones to crack food?", "sea otter", "Medium", ["otter"], "It may carry a favourite rock."),
Q("Which mammal has the strongest bite force among living land animals often cited in comparisons?", "hippopotamus", "Hard", ["hippo"], "Its huge jaws are not for smiling."),
Q("Which bird is famous for mimicking human speech with remarkable accuracy?", "parrot", "Easy", [], "Some species are exceptionally talented mimics."),
Q("Which marine animal is a close relative of elephants?", "manatee", "Hard", ["sea cow"], "It is a gentle aquatic mammal."),
Q("What animal is known for black-and-white stripes and a famously difficult pattern to distinguish individually?", "zebra", "Easy", [], "Its stripes are unique to individuals."),
Q("Which animal can survive extreme dehydration by entering a dormant state called anhydrobiosis?", "tardigrade", "Extreme", ["water bear"], "It is tiny and famously resilient."),
Q("Which animal is known for producing pearls?", "oyster", "Easy", [], "A grain of irritation can become something valuable."),
],
"Emoji": [
Q("Decode: 🔥 + 🧊 = ?", "hot and cold", "Easy", ["hot cold", "hot and cold"], "Opposites are colliding."),
Q("Decode: 🧠 + 💥 = ?", "mind blown", "Easy", ["mindblown", "mind blown"], "When your brain goes BOOM."),
Q("Decode: 👀 + 👀 = ?", "watching", "Easy", ["watch", "two eyes", "look"], "More eyes usually means more observing."),
Q("Decode: 🌧️ + 🐱 + 🐶 = ?", "raining cats and dogs", "Medium", ["raining cats and dogs"], "An old English expression."),
Q("Decode: 🐌 + ⚡ = ?", "slow vs fast", "Medium", ["slow and fast", "slow versus fast"], "Think extreme speed contrast."),
Q("Decode: 🔑 + ❤️ = ?", "key to the heart", "Medium", ["key to heart"], "One object opens; the other symbolizes feelings."),
Q("Decode: 🧊 + ☕ = ?", "iced coffee", "Easy", ["ice coffee", "iced coffee"], "Coffee, but chilled."),
Q("Decode: 🕵️ + 🔍 = ?", "detective", "Easy", ["investigation", "detective work"], "Someone looking for clues."),
Q("Decode: 🚪 + 🚫 + 👻 = ?", "haunted house", "Medium", ["haunted house"], "A place where you definitely do not want the door opening itself."),
Q("Decode: 🌎 + 🔥 = ?", "global warming", "Medium", ["global warming", "climate change"], "Planet + heat."),
Q("Decode: 🧑‍🚀 + 🌕 = ?", "moon landing", "Easy", ["moon landing"], "A famous giant leap."),
Q("Decode: 🐟 + 🪝 = ?", "fishing", "Easy", ["fish hook", "fishing"], "The hook gives it away."),
Q("Decode: ⏰ + 🏃 = ?", "running late", "Medium", ["late", "running late"], "Clock plus rushing human."),
Q("Decode: 🤐 + 🔒 = ?", "secret", "Medium", ["keep secret", "locked secret"], "Something you aren't supposed to reveal."),
Q("Decode: 📚 + 🧠 = ?", "knowledge", "Easy", ["learning", "education"], "Books feeding the brain."),
Q("Decode: 🎯 + 🏆 = ?", "winning the target", "Medium", ["bullseye", "hit the target"], "Target plus victory."),
Q("Decode: 🧩 + 🧠 = ?", "puzzle solving", "Easy", ["solving a puzzle", "puzzle"], "Two symbols, one brainy activity."),
Q("Decode: 🚀 + 🌌 = ?", "space travel", "Easy", ["space travel", "spaceflight"], "Rocket + universe."),
Q("Decode: 🧪 + 🔬 = ?", "science", "Easy", ["scientific research", "research"], "Lab equipment combo."),
Q("Decode: 🛑 + 🧠 = ?", "think before you act", "Hard", ["stop and think", "think before acting"], "Pause first, brain second."),
],
"City": [
Q("Which city is famous for the Colosseum?", "Rome", "Easy", [], "Ancient Roman architecture."),
Q("Which city is home to the Eiffel Tower?", "Paris", "Easy", [], "France's most recognizable landmark."),
Q("Which city is associated with the Burj Khalifa?", "Dubai", "Easy", [], "Think extremely tall skyscraper."),
Q("Which city is famous for canals and gondolas?", "Venice", "Easy", [], "Cars are not the main way around the historic center."),
Q("Which city hosted the 2012 Summer Olympics?", "London", "Medium", [], "The UK capital hosted the Games in 2012."),
Q("Which city is nicknamed the Big Apple?", "New York City", "Easy", ["new york", "nyc"], "USA's giant cultural metropolis."),
Q("Which city is famous for the Sagrada Família?", "Barcelona", "Medium", [], "Gaudí's extraordinary basilica."),
Q("Which city sits near the Golden Gate Bridge?", "San Francisco", "Easy", ["sf"], "California and a famous red-orange bridge."),
Q("Which city is famous for the Acropolis?", "Athens", "Easy", [], "Ancient Greece's iconic capital."),
Q("Which city is often called the City of Light?", "Paris", "Easy", [], "The nickname is strongly associated with France's capital."),
Q("Which city is home to the Forbidden City?", "Beijing", "Medium", [], "China's capital."),
Q("Which city is famous for Shibuya Crossing?", "Tokyo", "Easy", [], "One of the world's busiest pedestrian crossings."),
Q("Which city is associated with the Taj Mahal?", "Agra", "Easy", [], "The monument is in Uttar Pradesh."),
Q("Which city is famous for the Christ the Redeemer statue?", "Rio de Janeiro", "Easy", ["rio"], "Brazilian city with a huge statue overlooking it."),
Q("Which city is known for the Space Needle?", "Seattle", "Medium", [], "Pacific Northwest city."),
Q("Which city is famous for the ancient ruins of Machu Picchu nearby?", "Cusco", "Hard", ["cuzco"], "Historic Peruvian city and former Inca capital."),
Q("Which city is associated with the Kremlin and Red Square?", "Moscow", "Easy", [], "Russia's capital."),
Q("Which city is famous for the Opera House with sail-like roofs?", "Sydney", "Easy", [], "Australia's iconic harbour city."),
Q("Which city is home to the Marina Bay Sands complex?", "Singapore", "Medium", [], "City-state in Southeast Asia."),
Q("Which city is known for its medieval old town and Charles Bridge?", "Prague", "Medium", [], "Capital of the Czech Republic."),
],
"Riddle": [
Q("I have keys but open no locks. I have space but no room. What am I?", "keyboard", "Easy", [], "You are probably using one right now."),
Q("The more you take, the more you leave behind. What are they?", "footsteps", "Easy", ["footsteps"], "You make them while walking."),
Q("I speak without a mouth and hear without ears. What am I?", "echo", "Easy", [], "Sound comes back to you."),
Q("I am always in front of you but can never be seen. What am I?", "future", "Medium", [], "It has not happened yet."),
Q("I have cities but no houses, forests but no trees, and water but no fish. What am I?", "map", "Easy", [], "A flat representation of places."),
Q("What can travel around the world while staying in one corner?", "stamp", "Easy", [], "It rides on letters."),
Q("What gets wetter as it dries?", "towel", "Easy", [], "Bathroom object."),
Q("What has one eye but cannot see?", "needle", "Easy", [], "Thread passes through its eye."),
Q("What has a neck but no head?", "bottle", "Easy", [], "You might open it when thirsty."),
Q("What can you catch but not throw?", "cold", "Easy", ["a cold"], "You might catch one in winter."),
Q("What has many teeth but cannot bite?", "comb", "Easy", [], "Used on hair."),
Q("What belongs to you, but other people use it more than you do?", "your name", "Easy", ["name"], "People say it when addressing you."),
Q("What disappears as soon as you say its name?", "silence", "Medium", [], "Speaking destroys it."),
Q("I am light as a feather, yet no person can hold me for long. What am I?", "breath", "Medium", [], "You need to release it eventually."),
Q("What has an end but no beginning, a home but no family, and a space without room?", "keyboard", "Extreme", [], "Look at the physical layout of keys."),
Q("A man shaves several times a day but still has a beard. Who is he?", "barber", "Easy", [], "His job involves shaving other people."),
Q("What five-letter word becomes shorter when you add two letters to it?", "short", "Medium", [], "Add 'er' to the idea of short."),
Q("What can fill a room but takes up no space?", "light", "Easy", [], "You can see it but cannot pile it in a corner."),
Q("What has hands but cannot clap?", "clock", "Easy", [], "Its hands tell time."),
Q("What has a head and a tail but no body?", "coin", "Easy", [], "Flip it."),
],
"Logic": [
Q("A farmer has 17 sheep. All but 9 run away. How many remain?", "9", "Easy", ["nine"], "'All but 9' means 9 stay."),
Q("If you overtake the person in second place, what place are you in?", "second", "Easy", ["2nd", "2"], "You take their position, not first."),
Q("A clock takes 5 seconds to strike 5 times. How long to strike 10 times at the same rate?", "11.25 seconds", "Hard", ["11.25", "11.25 sec"], "Five strikes contain four intervals; ten strikes contain nine."),
Q("You have one match and enter a dark room with a lamp, candle and fireplace. What do you light first?", "match", "Easy", [], "You need the match to light anything else."),
Q("A plane crashes on the border of two countries. Where do they bury the survivors?", "nowhere", "Easy", [], "Survivors are alive."),
Q("If 3 cats catch 3 mice in 3 minutes, how many cats catch 100 mice in 100 minutes at the same rate?", "3", "Hard", [], "Each cat catches one mouse every 3 minutes under the given rate."),
Q("You have 8 balls and one is heavier. With a balance scale, minimum weighings needed?", "2", "Hard", ["two"], "Split into groups and narrow down."),
Q("A room has 4 corners. A cat sits in each corner. Each cat sees 3 cats. How many cats?", "4", "Easy", [], "Each cat can see the other three."),
Q("A father and son have ages adding to 66. The father's age is the son's digits reversed. What pairs are possible?", "51 and 15", "Extreme", ["51 15", "15 and 51"], "Other reversed pairs may also fit depending on age assumptions; the classic intended pair is 51 and 15."),
Q("You have 10 candles and blow out 2. How many candles remain?", "10", "Easy", [], "Blowing them out doesn't remove them."),
Q("A bus driver goes the wrong way down a one-way street but doesn't break the law. Why?", "he was walking", "Medium", ["he is walking", "not driving"], "The trick is in the phrase 'bus driver'."),
Q("If yesterday was tomorrow, today would be Friday. What day is today?", "Wednesday", "Extreme", ["wednesday"], "Shift the reference by two days."),
Q("You see a boat filled with people, yet there isn't a single person on board. Why?", "they are all married", "Medium", ["no single people", "everyone is married"], "'Single' is the trick word."),
Q("What is the next number: 2, 3, 5, 9, 17, ?", "33", "Medium", [], "Each term is previous ×2 −1."),
Q("If two's company and three's a crowd, what are four and five?", "nine", "Easy", ["9"], "It's simply 4 + 5."),
Q("A doctor gives you 3 pills and says take one every half hour. How long until all are taken?", "1 hour", "Medium", ["60 minutes", "one hour"], "First immediately, second after 30 minutes, third after 60."),
Q("You have 6 eggs. You break 2, cook 2, and eat 2. How many eggs remain?", "4", "Easy", [], "The same two can be broken, cooked and eaten."),
Q("A farmer has chickens and cows. There are 10 heads and 28 legs. How many cows?", "4", "Medium", [], "Four cows give 16 legs; six chickens give 12."),
Q("A number is doubled and then 6 is added to get 20. What is the number?", "7", "Easy", [], "Reverse the operations: 20−6, then divide by 2."),
Q("If all bloops are razzies and some razzies are lazzies, must some bloops be lazzies?", "No", "Hard", ["no"], "The overlap with lazzies is not guaranteed to include bloops."),
],
"Trick": [
Q("How many months have 28 days?", "12", "Easy", ["all 12", "twelve"], "Every month has at least 28 days."),
Q("What word is spelled incorrectly in every dictionary?", "incorrectly", "Easy", [], "Read the sentence literally."),
Q("If an electric train travels north, which way does its smoke go?", "nowhere", "Easy", [], "Electric trains don't produce exhaust smoke."),
Q("Before Mount Everest was discovered, what was the highest mountain?", "Mount Everest", "Easy", ["everest"], "It was still there before people documented it."),
Q("What can you never eat for breakfast?", "lunch and dinner", "Easy", ["lunch", "dinner"], "Not breakfast anymore."),
Q("If you have a bowl with 6 apples and take away 4, how many do you have?", "4", "Easy", [], "You took 4, so you have 4."),
Q("What gets bigger the more you take away from it?", "a hole", "Easy", ["hole"], "Removing material makes it larger."),
Q("How far can a dog run into a forest?", "halfway", "Medium", [], "After halfway it is running out of the forest."),
Q("A rooster lays an egg on a roof. Which side does it roll down?", "neither", "Easy", [], "Roosters don't lay eggs."),
Q("What starts with T, ends with T, and has T in it?", "teapot", "Easy", [], "Tea + pot, and it has T in it."),
Q("What has four wheels and flies?", "garbage truck", "Medium", ["garbage truck"], "The flies are insects, not wings."),
Q("If you throw a red stone into the blue sea, what does it become?", "wet", "Easy", [], "Colour is irrelevant."),
Q("What invention lets you look through a wall?", "window", "Easy", [], "A wall with a window lets you see through."),
Q("What is at the end of a rainbow?", "the letter w", "Medium", ["w"], "The word rainbow ends with W."),
Q("What has 13 hearts but no organs?", "a deck of cards", "Medium", ["deck of cards", "cards"], "Thirteen hearts in a standard suit set."),
Q("What has a thumb and four fingers but isn't alive?", "glove", "Easy", [], "You wear it on a hand."),
Q("What question can you never answer yes to?", "are you asleep", "Medium", ["are you sleeping"], "If you are truly asleep, you can't answer."),
Q("What is always coming but never arrives?", "tomorrow", "Easy", [], "When it arrives, it becomes today."),
Q("What can you hold without touching it?", "a conversation", "Medium", ["conversation"], "You can 'hold' one without physical contact."),
Q("Which side of a turkey has the most feathers?", "outside", "Easy", [], "The feathers are on the outside."),
],
"Pattern": [
Q("Next: 2, 4, 8, 16, ?", "32", "Easy", ["32"], "Double each time."),
Q("Next: 1, 4, 9, 16, ?", "25", "Easy", ["25"], "Perfect squares."),
Q("Next: 3, 6, 12, 24, ?", "48", "Easy", [], "Double each term."),
Q("Next: 5, 10, 20, 40, ?", "80", "Easy", [], "Double each time."),
Q("Next: 1, 1, 2, 3, 5, 8, ?", "13", "Medium", [], "Fibonacci sequence."),
Q("Next: 2, 6, 12, 20, 30, ?", "42", "Hard", [], "n(n+1): 1×2, 2×3, 3×4..."),
Q("Next: 100, 90, 81, 73, 66, ?", "60", "Hard", [], "Subtract 10, 9, 8, 7, then 6."),
Q("Next: 7, 10, 16, 28, 52, ?", "100", "Hard", [], "Add 3,6,12,24, then 48."),
Q("Next: 2, 3, 5, 8, 12, 17, ?", "23", "Medium", [], "Add 1,2,3,4,5,6..."),
Q("Next: 81, 27, 9, 3, ?", "1", "Easy", [], "Divide by 3."),
Q("Next: 1, 8, 27, 64, ?", "125", "Medium", [], "Cubes: 1³, 2³, 3³, 4³, 5³."),
Q("Next: 13, 17, 23, 31, 41, ?", "53", "Hard", [], "Add 4,6,8,10,12."),
Q("Next: 2, 5, 11, 23, 47, ?", "95", "Hard", [], "×2 +1."),
Q("Next: 50, 45, 35, 20, 0, ?", "-25", "Medium", ["minus 25"], "Subtract 5,10,15,20,25."),
Q("Next: 1, 2, 6, 24, 120, ?", "720", "Medium", [], "Factorials: 1!,2!,3!,4!,5!,6!."),
Q("Next: 4, 7, 13, 25, 49, ?", "97", "Hard", [], "×2−1."),
Q("Next: 10, 20, 19, 38, 37, 74, ?", "73", "Medium", [], "×2, −1 repeating."),
Q("Next: 6, 11, 21, 41, 81, ?", "161", "Hard", [], "×2−1."),
Q("Next: 9, 18, 16, 32, 30, 60, ?", "58", "Medium", [], "×2, −2 repeating."),
Q("Next: 3, 9, 27, 81, ?", "243", "Easy", [], "Multiply by 3."),
],
"Panic": [
Q("5 + 7 × 2 = ?", "19", "Easy", [], "Multiplication before addition."),
Q("What is 15% of 200?", "30", "Easy", [], "10% is 20 and 5% is 10."),
Q("Capital of Japan?", "Tokyo", "Easy", [], "Think Shibuya."),
Q("How many sides does a hexagon have?", "6", "Easy", [], "Hexa means six."),
Q("Square root of 144?", "12", "Easy", [], "12×12."),
Q("How many seconds are in one minute?", "60", "Easy", [], "Time pressure doesn't change time."),
Q("9² = ?", "81", "Easy", [], "9×9."),
Q("Which planet is known as the Red Planet?", "Mars", "Easy", [], "Our rocky neighbour."),
Q("What is 100 ÷ 4?", "25", "Easy", [], "Quarter of 100."),
Q("How many degrees in a right angle?", "90", "Easy", [], "Corner of a square."),
Q("What is 7 × 8?", "56", "Easy", [], "Classic multiplication-table ambush."),
Q("Which gas do humans need to breathe for normal respiration?", "oxygen", "Easy", [], "It is about 21% of Earth's atmosphere."),
Q("What is 2³?", "8", "Easy", [], "2×2×2."),
Q("How many continents are commonly taught?", "7", "Easy", [], "Asia, Africa, Europe, etc."),
Q("What is 45 − 17?", "28", "Easy", [], "Subtract carefully."),
Q("Which metal has the chemical symbol Fe?", "iron", "Medium", [], "Fe comes from Latin ferrum."),
Q("What is 11 × 11?", "121", "Easy", [], "A square number."),
Q("Which ocean is the largest?", "Pacific Ocean", "Easy", ["pacific"], "It covers more area than any other ocean."),
Q("What is 72 ÷ 8?", "9", "Easy", [], "Eight nines are 72."),
Q("Which planet has the most famous ring system?", "Saturn", "Easy", [], "Its rings are spectacular."),
],
"Bluff Master": [
Q("Which statement is FALSE? A) Octopuses have three hearts. B) Bats are blind. C) Some octopuses can change colour.", "bats are blind", "Medium", ["b", "B"], "The common myth says bats are blind, but they can see."),
Q("Which statement is FALSE? A) Venus rotates very slowly. B) Venus is hotter than Mercury on average. C) Venus has liquid water oceans.", "venus has liquid water oceans", "Medium", ["c", "C"], "Venus is extremely hostile and has no Earth-like oceans."),
Q("Which statement is FALSE? A) Honey can last a very long time. B) Bees make honey. C) Honey is made by butterflies.", "honey is made by butterflies", "Easy", ["c", "C"], "Butterflies do not make honey."),
Q("Which statement is FALSE? A) Lightning can occur without rain reaching the ground. B) Lightning is hotter than the surface of the Sun. C) Lightning is made of frozen electricity.", "lightning is made of frozen electricity", "Medium", ["c", "C"], "Electricity does not freeze into lightning."),
Q("Which statement is FALSE? A) Sharks are fish. B) Whales are mammals. C) Dolphins are fish.", "dolphins are fish", "Easy", ["c", "C"], "Dolphins are mammals."),
Q("Which statement is FALSE? A) The Moon has gravity. B) The Moon has no atmosphere at all. C) The Moon has a much thinner exosphere than Earth.", "the moon has no atmosphere at all", "Hard", ["b", "B"], "The Moon has an extremely thin exosphere."),
Q("Which statement is FALSE? A) Water expands when it freezes. B) Ice is less dense than liquid water. C) Ice sinks in pure water.", "ice sinks in pure water", "Easy", ["c", "C"], "Ice floats because it is less dense."),
Q("Which statement is FALSE? A) Sound needs a medium. B) Sound can travel through solids. C) Sound travels fastest in a vacuum.", "sound travels fastest in a vacuum", "Easy", ["c", "C"], "A vacuum has no material medium for ordinary sound waves."),
Q("Which statement is FALSE? A) Plants perform photosynthesis. B) Chlorophyll absorbs light. C) Plants get all their mass directly from soil minerals.", "plants get all their mass directly from soil minerals", "Hard", ["c", "C"], "Much of a plant's dry mass comes from carbon dioxide-derived carbon."),
Q("Which statement is FALSE? A) The Pacific is the largest ocean. B) The Arctic is the smallest ocean. C) The Atlantic is the largest ocean.", "the atlantic is the largest ocean", "Easy", ["c", "C"], "The Pacific is largest."),
Q("Which statement is FALSE? A) Gold is Au. B) Silver is Ag. C) Iron is Ir.", "iron is ir", "Easy", ["c", "C"], "Iron is Fe; Ir is iridium."),
Q("Which statement is FALSE? A) A triangle has three sides. B) A square has four equal sides. C) A circle has four corners.", "a circle has four corners", "Easy", ["c", "C"], "A circle has no corners."),
Q("Which statement is FALSE? A) Earth orbits the Sun. B) The Sun orbits Earth once a year. C) Earth rotates on its axis.", "the sun orbits earth once a year", "Easy", ["b", "B"], "Earth orbits the Sun; apparent daily motion is not the same as orbital motion."),
Q("Which statement is FALSE? A) DNA stores genetic information. B) Red blood cells normally have no nucleus in humans. C) Human red blood cells contain chlorophyll.", "human red blood cells contain chlorophyll", "Easy", ["c", "C"], "Chlorophyll is a plant pigment."),
Q("Which statement is FALSE? A) Penguins are birds. B) Ostriches can fly well. C) Some birds cannot fly.", "ostriches can fly well", "Easy", ["b", "B"], "Ostriches are flightless birds."),
Q("Which statement is FALSE? A) Mercury is closest to the Sun. B) Neptune is the farthest major planet from the Sun. C) Jupiter is smaller than Earth.", "jupiter is smaller than earth", "Easy", ["c", "C"], "Jupiter is vastly larger than Earth."),
Q("Which statement is FALSE? A) Caffeine is a stimulant. B) Coffee beans are seeds. C) Coffee beans grow inside apples.", "coffee beans grow inside apples", "Medium", ["c", "C"], "Coffee seeds grow inside coffee cherries."),
Q("Which statement is FALSE? A) Diamonds are made of carbon. B) Graphite is also carbon. C) Diamonds are made of pure iron.", "diamonds are made of pure iron", "Easy", ["c", "C"], "Diamond is a carbon allotrope."),
Q("Which statement is FALSE? A) Antarctica is a continent. B) It is the coldest continent. C) It has permanent large native human cities.", "it has permanent large native human cities", "Medium", ["c", "C"], "It has research stations, not permanent native cities."),
Q("Which statement is FALSE? A) A prism can split white light. B) Rainbows involve refraction and dispersion. C) Rainbows are painted onto clouds.", "rainbows are painted onto clouds", "Easy", ["c", "C"], "Optics, not paint."),
],
"Risk It": [
Q("Risk x2: What is the only even prime number?", "2", "Easy", [], "Every other even number is divisible by 2."),
Q("Risk x2: What is 13 × 7?", "91", "Medium", [], "10×7 + 3×7."),
Q("Risk x2: Which element has atomic number 1?", "hydrogen", "Easy", [], "The first element."),
Q("Risk x2: What is the capital of Australia?", "Canberra", "Medium", [], "Not Sydney or Melbourne."),
Q("Risk x2: Which planet rotates on its side unusually strongly?", "Uranus", "Hard", [], "Its axial tilt is about 98 degrees."),
Q("Risk x2: What is 17²?", "289", "Medium", [], "17×17."),
Q("Risk x2: Which scientist is associated with the three laws of motion?", "Newton", "Easy", ["Isaac Newton"], "Gravity also gives him away."),
Q("Risk x2: What is the smallest prime number greater than 20?", "23", "Medium", [], "21 and 22 are composite/even."),
Q("Risk x2: Which blood cells mainly carry oxygen?", "red blood cells", "Easy", ["rbc", "red cells"], "Hemoglobin is the key."),
Q("Risk x2: What is the square root of 225?", "15", "Easy", [], "15×15."),
Q("Risk x2: Which layer of Earth is liquid and surrounds the inner core?", "outer core", "Hard", [], "It is mainly molten metal."),
Q("Risk x2: What is 2^10?", "1024", "Hard", ["1024"], "2×2 repeatedly ten times."),
Q("Risk x2: Which SI unit measures electric current?", "ampere", "Medium", ["amp"], "Named after André-Marie Ampère."),
Q("Risk x2: What is the chemical symbol for potassium?", "K", "Medium", ["potassium", "k"], "It comes from kalium."),
Q("Risk x2: Which gas is most abundant in Earth's atmosphere?", "nitrogen", "Easy", [], "About 78%."),
Q("Risk x2: What is 1/4 expressed as a percentage?", "25%", "Easy", ["25", "25 percent"], "Quarter of 100."),
Q("Risk x2: What is the approximate speed of light in vacuum?", "300000 km/s", "Hard", ["3 x 10^5 km/s", "300,000 km/s", "3e5 km/s"], "About 3×10^5 km/s."),
Q("Risk x2: Which organelle is often called the powerhouse of the cell?", "mitochondria", "Easy", ["mitochondrion"], "It produces much of the cell's ATP."),
Q("Risk x2: What is 99 + 101?", "200", "Easy", [], "The pair is centered around 100."),
Q("Risk x2: Which force keeps planets in orbit around stars?", "gravity", "Easy", ["gravitational force"], "Mass attracts mass."),
],
"Memory Bomb": [
Q("Memorize: LIME - ORBIT - 47 - TIGER. What was item 3?", "47", "Medium", [], "Sequence order matters."),
Q("Memorize: NEON - 12 - MARS - BLUE. What was item 1?", "NEON", "Medium", ["neon"], "First means first."),
Q("Memorize: 8 - COMET - SILVER - 31. What was item 4?", "31", "Medium", [], "Last item."),
Q("Memorize: RIVER - 9 - GLASS - PIANO. What was item 2?", "9", "Easy", [], "Second item."),
Q("Memorize: COBALT - MOON - 72 - FOX. What was item 3?", "72", "Medium", [], "Third item."),
Q("Memorize: VIOLET - 5 - ENGINE - CLOUD. What was item 4?", "CLOUD", "Easy", [], "Final item."),
Q("Memorize: ATLAS - 19 - JUPITER - MINT. What was item 2?", "19", "Easy", [], "Second item."),
Q("Memorize: QUARTZ - 44 - EAGLE - NOVA. What was item 1?", "QUARTZ", "Medium", [], "First item."),
Q("Memorize: BOLT - SATURN - 6 - ORANGE. What was item 3?", "6", "Easy", [], "Third item."),
Q("Memorize: MAPLE - 27 - OCEAN - GLASS. What was item 2?", "27", "Easy", [], "Second item."),
Q("Memorize: COMET - 13 - TIGER - RAIN. What was item 3?", "TIGER", "Easy", [], "Third item."),
Q("Memorize: PLUTO - 88 - VELVET - CROWN. What was item 4?", "CROWN", "Easy", [], "Last item."),
Q("Memorize: LASER - 3 - FOREST - KITE. What was item 1?", "LASER", "Easy", [], "First item."),
Q("Memorize: ORANGE - 64 - MOON - SWORD. What was item 2?", "64", "Easy", [], "Second item."),
Q("Memorize: FALCON - 22 - ICE - TRAIN. What was item 4?", "TRAIN", "Easy", [], "Fourth item."),
Q("Memorize: MARBLE - 71 - RIVER - STAR. What was item 3?", "RIVER", "Easy", [], "Third item."),
Q("Memorize: NEPTUNE - 10 - GLASS - BISON. What was item 2?", "10", "Easy", [], "Second item."),
Q("Memorize: CROWN - 55 - DESERT - PENGUIN. What was item 3?", "DESERT", "Easy", [], "Third item."),
Q("Memorize: NOVA - 16 - CASTLE - RAIN. What was item 1?", "NOVA", "Easy", [], "First item."),
Q("Memorize: PULSE - 33 - OAK - ROCKET. What was item 4?", "ROCKET", "Easy", [], "Last item."),
],
"One Word Chaos": [
Q("One word only: Opposite of ancient?", "modern", "Easy", ["new"], "Not old."),
Q("One word only: A person who studies stars and planets?", "astronomer", "Easy", [], "Not astrology."),
Q("One word only: Frozen water?", "ice", "Easy", [], "Simple but don't overthink."),
Q("One word only: The process plants use to make food using light?", "photosynthesis", "Medium", [], "Chloro... you know it."),
Q("One word only: Fear of heights?", "acrophobia", "Medium", [], "Acro = height."),
Q("One word only: Study of earthquakes?", "seismology", "Hard", [], "Seismo relates to shaking."),
Q("One word only: A shape with eight sides?", "octagon", "Easy", [], "Octa = eight."),
Q("One word only: Device that measures temperature?", "thermometer", "Easy", [], "Thermo = heat."),
Q("One word only: Largest planet?", "Jupiter", "Easy", [], "Gas giant."),
Q("One word only: The centre of an atom?", "nucleus", "Easy", [], "Contains protons and neutrons."),
Q("One word only: A baby frog?", "tadpole", "Easy", [], "Aquatic early stage."),
Q("One word only: A word opposite in meaning to another?", "antonym", "Medium", [], "Synonym is the opposite concept."),
Q("One word only: A scientist who studies rocks?", "geologist", "Easy", [], "Geo = Earth."),
Q("One word only: Instrument with black and white keys?", "piano", "Easy", [], "Musical keyboard instrument."),
Q("One word only: A polygon with five sides?", "pentagon", "Easy", [], "Penta = five."),
Q("One word only: The nearest star to Earth?", "Sun", "Easy", ["the sun"], "It is much closer than every other star."),
Q("One word only: Blood-clotting cell fragment?", "platelet", "Medium", ["platelets"], "Tiny cell fragments help stop bleeding."),
Q("One word only: Study of living organisms?", "biology", "Easy", [], "Bio = life."),
Q("One word only: A number divisible only by 1 and itself?", "prime", "Easy", ["prime number"], "2, 3, 5..."),
Q("One word only: Opposite of transparent?", "opaque", "Medium", [], "Blocks light from passing through clearly."),
],
"Target Number": [
Q("Target 24: Using 6, 6, 4, 1 exactly once, make 24.", "6*(4+1-? )", "Extreme", [], "This item is a challenge; common arithmetic operators may have multiple solutions. Accept alternate valid constructions in future expansion."),
Q("Target 10: 2, 3, 4, 5 exactly once. Make 10.", "5+4+3-2", "Medium", ["10"], "One valid solution is 5+4+3−2."),
Q("Target 15: 1, 2, 3, 9 exactly once. Make 15.", "9+3+2+1", "Easy", ["15"], "Just add them."),
Q("Target 20: 2, 3, 5, 10 exactly once. Make 20.", "10*2+5-3", "Medium", ["20"], "10×2+5−3."),
Q("Target 18: 2, 4, 5, 7 exactly once. Make 18.", "7+5+4+2", "Easy", ["18"], "Add all four."),
Q("Target 30: 1, 4, 5, 6 exactly once. Make 30.", "6*5+4-1", "Medium", ["30"], "6×5+4−1."),
Q("Target 16: 2, 3, 4, 8 exactly once. Make 16.", "8*2+4-3", "Medium", ["16"], "8×2+4−3."),
Q("Target 25: 1, 4, 5, 6 exactly once. Make 25.", "6*4+5-4", "Hard", ["25"], "This one is intentionally tricky; alternate valid answers may be accepted in a future solver."),
Q("Target 12: 1, 2, 4, 6 exactly once. Make 12.", "6*2+4-1", "Easy", ["12"], "6×2+4−1."),
Q("Target 21: 1, 3, 4, 7 exactly once. Make 21.", "7*3+4-1", "Easy", ["21"], "7×3+4−1."),
Q("Target 14: 1, 2, 5, 8 exactly once. Make 14.", "8+5+2-1", "Easy", ["14"], "Add and subtract."),
Q("Target 24: 2, 3, 4, 6 exactly once. Make 24.", "6*4+3-2", "Easy", ["24"], "6×4+3−2."),
Q("Target 17: 1, 2, 6, 8 exactly once. Make 17.", "8+6+2+1", "Easy", ["17"], "Add all."),
Q("Target 32: 2, 4, 6, 8 exactly once. Make 32.", "8*4+6-2", "Medium", ["32"], "8×4+6−2."),
Q("Target 40: 2, 5, 7, 10 exactly once. Make 40.", "10*5-7+2-5", "Extreme", ["40"], "This challenge allows operator creativity; exact expression parsing can be expanded later."),
],
"Mystery Power": [
Q("Which force causes objects to fall toward Earth?", "gravity", "Easy", [], "It is everywhere around you."),
Q("Which phenomenon makes a straw look bent in water?", "refraction", "Medium", [], "Light changes direction between media."),
Q("What causes the blue colour of the daytime sky?", "Rayleigh scattering", "Hard", ["rayleigh scattering", "scattering"], "Shorter wavelengths scatter more strongly in the atmosphere."),
Q("What powers the Sun's energy production?", "nuclear fusion", "Medium", ["fusion"], "Hydrogen nuclei combine into helium."),
Q("What phenomenon is responsible for a rainbow's separation of colours?", "dispersion", "Hard", [], "Different wavelengths refract by different amounts."),
Q("What force opposes motion between surfaces?", "friction", "Easy", [], "It resists relative motion."),
Q("What phenomenon allows magnets to attract iron without touching it?", "magnetic force", "Easy", ["magnetism"], "A field mediates the interaction."),
Q("What causes tides primarily?", "gravity of the Moon and Sun", "Medium", ["moon gravity", "gravitational pull of moon"], "The Moon has the larger tidal influence."),
Q("What principle explains why a floating object displaces water?", "Archimedes' principle", "Hard", ["archimedes principle"], "Buoyant force equals the weight of displaced fluid."),
Q("What is the name of the effect where moving clocks run differently relative to observers?", "time dilation", "Extreme", [], "It is a consequence of relativity."),
Q("What force keeps a charged particle moving in a curved path in a magnetic field?", "Lorentz force", "Hard", ["lorentz force"], "Magnetic force is part of the Lorentz force."),
Q("What phenomenon produces a mirage on a hot road?", "refraction", "Medium", ["atmospheric refraction"], "Temperature gradients bend light."),
Q("What is the energy stored in an object due to its position called?", "potential energy", "Easy", ["potential"], "Height in a gravitational field is a common example."),
Q("What phenomenon lets a prism split white light?", "dispersion", "Medium", [], "Different colours bend differently."),
Q("What is the transfer of heat by electromagnetic waves called?", "radiation", "Easy", [], "The Sun heats Earth this way."),
],
"Sabotage Round": [
Q("Sabotage: I am a number. Remove one letter from 'seven' and I become even. What am I?", "seven", "Hard", [], "The trick is that 'seven' contains the word 'even' after removing letters? Think carefully; intended wordplay is seven → even by removing s and? This round is deliberately chaotic."),
Q("Sabotage: What is the one thing everyone can do at the same time but nobody can do twice at the exact same moment?", "be born", "Extreme", ["birth", "be born"], "A deliberately philosophical wordplay round."),
Q("Sabotage: If a word is written in all caps, does its pronunciation automatically change?", "no", "Easy", ["no"], "Capitalization does not normally change pronunciation."),
Q("Sabotage: Can a number be both even and odd?", "no", "Easy", ["no"], "Not under ordinary integer definitions."),
Q("Sabotage: If you have 1 kilogram of feathers and 1 kilogram of steel, which is heavier?", "neither", "Easy", ["same"], "Both have the same mass."),
Q("Sabotage: What has a beginning and an end but no middle?", "a stick", "Medium", ["stick"], "The intended joke is about the word/object framing; accept 'line' in casual play."),
Q("Sabotage: Which is larger: 0.9 or 0.90?", "same", "Easy", ["equal", "0.90", "0.9"], "Trailing zero does not change the value."),
Q("Sabotage: Is zero positive or negative?", "neither", "Medium", ["neither"], "Zero is neither positive nor negative."),
Q("Sabotage: If you divide 10 by 2, then multiply by 2, what do you get?", "10", "Easy", [], "Operations reverse each other here."),
Q("Sabotage: What number is missing: 1, 1, 2, 3, 5, ?", "8", "Easy", [], "Fibonacci strikes again."),
Q("Sabotage: Can you spell 'wrong' correctly?", "wrong", "Easy", [], "The word itself is the answer."),
Q("Sabotage: Which weighs more: a litre of water or a litre of mercury?", "mercury", "Hard", [], "Mercury is much denser."),
Q("Sabotage: If today is Monday, what day will it be after 14 days?", "Monday", "Easy", [], "14 is exactly two weeks."),
Q("Sabotage: Is a square also a rectangle?", "yes", "Medium", ["yes"], "A rectangle has four right angles; a square is a special rectangle."),
Q("Sabotage: Can a triangle have two right angles in Euclidean geometry?", "no", "Medium", ["no"], "Two right angles already sum to 180 degrees."),
],
"Buzzer Battle": [
Q("Buzzer: Capital of Canada?", "Ottawa", "Easy", [], "Not Toronto."),
Q("Buzzer: 12 × 12?", "144", "Easy", [], "Square of 12."),
Q("Buzzer: Chemical symbol for oxygen?", "O", "Easy", ["o", "oxygen"], "Single letter."),
Q("Buzzer: Largest mammal?", "blue whale", "Easy", [], "It is not a land animal."),
Q("Buzzer: 29 + 13?", "42", "Easy", [], "The answer to many nerd jokes."),
Q("Buzzer: Which planet is closest to the Sun?", "Mercury", "Easy", [], "First planet."),
Q("Buzzer: What is H2O?", "water", "Easy", [], "Two hydrogens, one oxygen."),
Q("Buzzer: 1000 metres = ?", "1 kilometre", "Easy", ["1 km", "kilometer"], "Metric conversion."),
Q("Buzzer: Which continent is Egypt mostly in?", "Africa", "Easy", [], "The Sinai is in Asia, but most territory is in Africa."),
Q("Buzzer: What is the boiling point of water at standard pressure in Celsius?", "100", "Easy", ["100 c", "100 degrees"], "Standard atmospheric pressure."),
Q("Buzzer: Who painted the Mona Lisa?", "Leonardo da Vinci", "Easy", ["Leonardo"], "Italian Renaissance artist."),
Q("Buzzer: What is 2 + 2 × 5?", "12", "Easy", [], "Multiply first."),
Q("Buzzer: Which gas do plants take in for photosynthesis?", "carbon dioxide", "Easy", ["co2"], "Plants use carbon dioxide as a carbon source."),
Q("Buzzer: How many players are on court for one basketball team at a time?", "5", "Easy", [], "Standard basketball."),
Q("Buzzer: Which instrument measures atmospheric pressure?", "barometer", "Medium", [], "Baro = pressure."),
Q("Buzzer: What is the hardest natural mineral commonly listed on the Mohs scale?", "diamond", "Easy", [], "It ranks 10."),
Q("Buzzer: Which ocean is between Africa and Australia?", "Indian Ocean", "Easy", ["indian"], "Named after the Indian subcontinent."),
Q("Buzzer: What is 7³?", "343", "Medium", [], "7×7×7."),
Q("Buzzer: What is the SI unit of force?", "newton", "Easy", [], "Named after Isaac Newton."),
Q("Buzzer: Which organ pumps blood through the body?", "heart", "Easy", [], "The muscular pump."),
],
"CHAOS MODE": [
Q("CHAOS: Which is older: the pyramids of Giza or the Roman Colosseum?", "pyramids of Giza", "Medium", ["pyramids"], "Thousands of years older."),
Q("CHAOS: If you fold a paper in half once, how many layers are there?", "2", "Easy", [], "One fold doubles layers."),
Q("CHAOS: Which has more letters: 'alphabet' or 'abcdefghijklmnopqrstuvwxyz'?", "abcdefghijklmnopqrstuvwxyz", "Easy", ["abcdefghijklmnopqrstuvwxyz"], "Count the actual strings."),
Q("CHAOS: What is the only mammal capable of true powered flight?", "bat", "Medium", [], "Gliding is different from powered flight."),
Q("CHAOS: What is the opposite of a palindrome?", "not a palindrome", "Extreme", [], "There is no standard mathematical antonym; this is a chaos wording trap."),
Q("CHAOS: Which is larger: 1/2 or 0.49?", "1/2", "Easy", ["0.5", "0.50"], "1/2 = 0.5."),
Q("CHAOS: What has more mass: 1 kg of gold or 1 kg of feathers?", "same", "Easy", ["equal"], "Both are one kilogram."),
Q("CHAOS: Which planet is famous for a giant red storm?", "Jupiter", "Easy", [], "The Great Red Spot."),
Q("CHAOS: What number comes after 999?", "1000", "Easy", [], "Don't let the timer gaslight you."),
Q("CHAOS: What is 10% of 10% of 1000?", "10", "Medium", [], "10% of 1000 = 100; 10% of 100 = 10."),
Q("CHAOS: Which is not a prime number: 17, 19, 21, 23?", "21", "Easy", [], "21 = 3×7."),
Q("CHAOS: If a triangle has angles 60, 60, and 60 degrees, what type is it?", "equilateral", "Easy", [], "Equal angles imply equal sides."),
Q("CHAOS: Which came first: the word 'queue' or the letter Q?", "letter Q", "Extreme", ["q"], "Letters existed before the modern English word queue."),
Q("CHAOS: What is 0 × 999999?", "0", "Easy", [], "Zero annihilates multiplication."),
Q("CHAOS: Which is faster: sound or light?", "light", "Easy", [], "Light wins by an absurd margin."),
Q("CHAOS: What does WWW stand for?", "World Wide Web", "Easy", [], "Three Ws."),
Q("CHAOS: Which is larger: a byte or a bit?", "byte", "Easy", [], "One byte is 8 bits."),
Q("CHAOS: What is the capital of Iceland?", "Reykjavik", "Medium", [], "It begins with R."),
Q("CHAOS: What is the smallest positive integer?", "1", "Easy", [], "Counting starts there in ordinary positive integers."),
Q("CHAOS: Can a square be a rhombus?", "yes", "Hard", ["yes"], "A square has four equal sides, so it qualifies."),
],
"King of the Hill": [
Q("KOTH: Which number is both a square and a cube, greater than 1 and less than 100?", "64", "Hard", [], "8² = 4³ = 64."),
Q("KOTH: What is the chemical symbol for sodium?", "Na", "Medium", ["na", "sodium"], "From natrium."),
Q("KOTH: Which planet has the shortest year?", "Mercury", "Medium", [], "Closest planet to the Sun."),
Q("KOTH: What is the derivative of x²?", "2x", "Hard", ["2*x"], "Power rule."),
Q("KOTH: What is the integral of 1/x dx?", "ln|x| + C", "Extreme", ["ln x + c", "ln|x|"], "The standard antiderivative on intervals avoiding zero."),
Q("KOTH: What is the largest prime number less than 20?", "19", "Easy", [], "18 is composite."),
Q("KOTH: Which vitamin is synthesized in skin after sunlight exposure?", "vitamin D", "Medium", ["d", "vitamin d"], "UVB helps initiate the process."),
Q("KOTH: What is the SI unit of power?", "watt", "Easy", [], "One joule per second."),
Q("KOTH: Which organelle contains most of a eukaryotic cell's DNA?", "nucleus", "Easy", [], "Mitochondria also contain some DNA."),
Q("KOTH: What is 15²?", "225", "Easy", [], "15×15."),
Q("KOTH: Which law relates voltage, current and resistance?", "Ohm's law", "Medium", ["ohms law", "ohm law"], "V = IR."),
Q("KOTH: What is the escape velocity from Earth approximately?", "11.2 km/s", "Extreme", ["11.2", "11.2 km/s"], "Approximate value from Earth's surface."),
Q("KOTH: Which blood group is often called the universal red-cell donor?", "O negative", "Medium", ["o-", "o negative"], "For red-cell transfusion compatibility, with important clinical caveats."),
Q("KOTH: What is 2^8?", "256", "Easy", [], "Powers of two."),
Q("KOTH: What is the approximate value of pi to two decimal places?", "3.14", "Easy", ["3.14"], "The familiar approximation."),
Q("KOTH: What is the powerhouse organelle?", "mitochondria", "Easy", ["mitochondrion"], "ATP production."),
Q("KOTH: Which particle has a negative electric charge?", "electron", "Easy", [], "Protons are positive."),
Q("KOTH: What is the pH of neutral pure water at about 25°C?", "7", "Easy", [], "Neutral at that reference condition."),
Q("KOTH: What is the approximate density of water?", "1 g/cm3", "Medium", ["1", "1 g/cm^3", "1 g per cm3"], "Near 1 g/cm³ around room temperature."),
Q("KOTH: What is the speed of sound in air approximately at room temperature?", "343 m/s", "Hard", ["343", "343 m/s"], "It varies with temperature and medium."),
],
}

# Small quickfire additions
EXTRA_VARIANTS = [
    ("Easy", "Quickfire: What is 5 + 8?", "13", ["13"]),
    ("Easy", "Quickfire: What is 9 × 6?", "54", ["54"]),
    ("Medium", "Quickfire: What is 144 ÷ 12?", "12", ["12"]),
    ("Medium", "Quickfire: What is 25% of 80?", "20", ["20"]),
]
for _mode in ["Buzzer Battle", "Panic", "CHAOS MODE"]:
    for _d, _q, _a, _aliases in EXTRA_VARIANTS:
        QUESTIONS[_mode].append(Q(_q, _a, _d, _aliases, "Fast calculation.", "Basic arithmetic."))

# ============================================================
# GUESSARENA V3 — CONTINUOUS ARENA ENGINE
# ============================================================
import re
import ast

active = {}
countdown_tasks = {}

# ---------------- QUESTION BANK UPGRADE ----------------
# Keep every mode at 50+ unique entries. The original bank is retained;
# these remixes add variety without changing the verified answers.
for _mode, _items in QUESTIONS.items():
    _base = list(_items)
    _n = 1
    while len(_items) < 50:
        _src = _base[(_n - 1) % len(_base)]
        _copy = dict(_src)
        _copy["q"] = f"{_src['q']}  ⚡ BONUS {_n}"
        _items.append(_copy)
        _n += 1

# Repair the known broken Target Number entries from the old bank.
TARGET_FIXES = {
    0: ("(6*(4+1))-6", ["24"], "Extreme", "6×(4+1)−6 = 24."),
    7: ("(5*6)-(1+4)", ["25"], "Hard", "5×6−(1+4) = 25."),
    13: ("10*(7+(2-5))", ["40"], "Extreme", "10×(7+2−5) = 40."),
}
for _i, (_ans, _aliases, _diff, _exp) in TARGET_FIXES.items():
    if _i < len(QUESTIONS["Target Number"]):
        QUESTIONS["Target Number"][_i]["a"] = _ans
        QUESTIONS["Target Number"][_i]["aliases"] = _aliases
        QUESTIONS["Target Number"][_i]["difficulty"] = _diff
        QUESTIONS["Target Number"][_i]["explain"] = _exp

# Add safe, genuinely different generated arithmetic questions to modes
# where procedural generation makes sense.
for _i in range(30):
    _a = 7 + _i * 3
    _b = 2 + (_i % 9)
    QUESTIONS["Logic"].append(Q(
        f"Logic Sprint: {_a} + {_b} = ?", str(_a + _b),
        "Easy", [], "Just add them.", "Arithmetic logic."
    ))

for _i in range(30):
    _start = 2 + _i
    _step = 2 + (_i % 9)
    _seq = [_start + j * _step for j in range(4)]
    QUESTIONS["Pattern"].append(Q(
        f"Next: {_seq[0]}, {_seq[1]}, {_seq[2]}, {_seq[3]}, ?",
        str(_seq[3] + _step), "Easy" if _i < 15 else "Medium", [],
        f"Add {_step} each time.", "Arithmetic pattern."
    ))

for _i in range(30):
    _a = 2 + (_i % 8)
    _b = 3 + ((_i * 2) % 7)
    _c = 4 + ((_i * 3) % 9)
    _d = 1 + (_i % 4)
    _target = _a * _b + _c - _d
    _expr = f"{_a}*{_b}+{_c}-{_d}"
    QUESTIONS["Target Number"].append(Q(
        f"Target {_target}: Using {_a}, {_b}, {_c}, {_d} exactly once, make {_target}.",
        _expr, ["Easy", "Medium", "Hard"][_i % 3], [str(_target)],
        "Multiply first, then adjust.", f"{_expr} = {_target}."
    ))
    QUESTIONS["Target Number"][-1]["target"] = _target
    QUESTIONS["Target Number"][-1]["numbers"] = [_a, _b, _c, _d]

# Generated target questions may push this mode well above 50.
# ------------------------------------------------------------

MAIN_TEXT = """🏟️ <b>GUESSARENA</b>

Your brain gets XP. Your confidence gets audited. 😂

🎮 Pick a mode → choose difficulty → <b>the game keeps rolling.</b>
No “start again” after every question.

👥 <b>GROUP:</b> first correct answer wins the round.
😈 Wrong answers roast you, but the round stays alive.
⏰ Timeout reveals the answer.
♾️ <b>ENDLESS:</b> keep playing until you press END GAME.
"""


def cancel_countdown(chat_id):
    task = countdown_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


def normalize(text):
    text = html.unescape(text or "").lower().strip()
    for ch in "!?.,:;()[]{}\"'`“”‘’":
        text = text.replace(ch, " ")
    text = text.replace("×", "*").replace("÷", "/").replace("−", "-")
    return " ".join(text.split())


def question_key(q):
    return (q.get("mode", ""), q.get("difficulty", ""), q.get("q", ""))


def prepare_question(q, mode):
    x = dict(q)
    x["mode"] = mode
    x["_key"] = question_key(x)
    return x


def pool_for(mode, difficulty):
    pool = [prepare_question(q, mode) for q in QUESTIONS.get(mode, [])]
    if difficulty == "Any":
        return pool
    exact = [q for q in pool if q.get("difficulty") == difficulty]
    # Difficulty is locked: never silently mix Easy/Medium/Hard/etc.
    return exact


def choose_question(mode, difficulty, used):
    pool = pool_for(mode, difficulty)
    available = [q for q in pool if question_key(q) not in used]
    if not available:
        used.clear()
        available = pool[:]
    if not available:
        return None
    q = random.choice(available)
    used.add(question_key(q))
    return q


def mode_intro(mode, difficulty):
    intros = {
        "Word": "📚 Dictionary entered the boxing ring.",
        "Animal": "🦁 Nature has questions.",
        "Emoji": "😂 Decode the chaos.",
        "City": "🌍 Pack your imaginary suitcase.",
        "Riddle": "🧩 Confidence is dangerous.",
        "Logic": "🧠 Brain summoned.",
        "Trick": "🎭 Read twice. Answer once.",
        "Pattern": "🔢 Find the rule.",
        "Panic": "🚨 NO TIME TO OVERTHINK.",
        "Bluff Master": "🃏 Catch the lie.",
        "Risk It": "🎲 High XP. High pressure.",
        "Memory Bomb": "💣 Remember first.",
        "One Word Chaos": "☝️ One word. No essays.",
        "Target Number": "🎯 Numbers have been weaponized.",
        "Mystery Power": "⚡ Science throws hands.",
        "Sabotage Round": "😈 The question fights back.",
        "Buzzer Battle": "🔔 Fastest brain wins.",
        "CHAOS MODE": "🌪️ Rules are normal. Your confidence isn't.",
        "King of the Hill": "👑 Own the hill.",
    }
    return (
        f"{MODE_EMOJI.get(mode, '🎮')} <b>{html.escape(mode)}</b> • "
        f"<b>{html.escape(difficulty)}</b>\n{intros.get(mode, 'Arena round started.') }"
    )


ROAST_WRONG = [
    "💀 Confidence 100%. Accuracy on vacation.",
    "😂 Premium confidence, free accuracy.",
    "🫠 Brain.exe stopped responding.",
    "🤡 Bold. Incorrect. Iconic.",
    "📉 Accuracy graph left the chat.",
    "😈 Reality rejected your submission.",
    "💥 Critical hit... on yourself.",
]
ROAST_TIMEOUT = [
    "⏰ TIME! The clock won.",
    "💀 Time left the chat.",
    "😂 You had a timer. The timer had you.",
    "⌛ You were buffering.",
    "💥 BOOM. Timer detonated.",
]
ROAST_CORRECT = [
    "🔥 CLEAN HIT!", "🧠 BIG BRAIN DETECTED.", "👑 THAT’S HOW YOU PLAY.",
    "⚡ Fast and correct.", "🎯 Bullseye.", "🚀 Brain launched.",
    "🏆 Arena notified.", "📈 XP printer activated.",
]
STREAK_LINES = [
    "🔥 STREAK {streak}! Somebody stop this person.",
    "👑 {streak} in a row. The hill is nervous.",
    "⚡ {streak}-streak! Brain refusing to clock out.",
    "💀 {streak} straight. Friendship status questionable.",
]


def target_expr_valid(expr, numbers, target):
    raw = html.unescape(expr or "").strip().replace("×", "*").replace("÷", "/").replace("−", "-").replace("^", "**")
    if len(raw) > 80 or not re.fullmatch(r"[0-9+*/().\-]+", raw):
        return False
    try:
        tree = ast.parse(raw, mode="eval")
    except Exception:
        return False
    allowed = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd
    )
    if any(not isinstance(n, allowed) for n in ast.walk(tree)):
        return False
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
                return False
            values.append(int(node.value) if float(node.value).is_integer() else node.value)
    if sorted(values) != sorted(numbers):
        return False
    try:
        value = eval(compile(tree, "<target>", "eval"), {"__builtins__": {}}, {})
        return abs(float(value) - float(target)) < 1e-9 and abs(float(value)) < 1e9
    except Exception:
        return False


def is_correct(q, text):
    if q.get("mode") == "Target Number" and q.get("target") is not None:
        if normalize(text) in {normalize(str(q["target"])), normalize(str(q["a"]))}:
            return True
        return target_expr_valid(text, q.get("numbers", []), q["target"])
    expected = [q.get("a", "")] + q.get("aliases", [])
    return any(normalize(text) == normalize(str(x)) for x in expected)


# ============================================================
# UI + SCORING HELPERS
# ============================================================

def timer_for(q):
    d = q.get("difficulty", "Medium")
    return TIMERS.get(d, 15)


def xp_for(q):
    if q.get("xp_override") is not None:
        return int(q["xp_override"])
    d = q.get("difficulty", "Medium")
    return XP_VALUES.get(d, 20)


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 PLAY", callback_data="menu:play"),
         InlineKeyboardButton("👤 PROFILE", callback_data="menu:profile")],
        [InlineKeyboardButton("🏆 LEADERBOARD", callback_data="menu:leaderboard"),
         InlineKeyboardButton("🏅 ACHIEVEMENTS", callback_data="menu:achievements")],
        [InlineKeyboardButton("📅 DAILY", callback_data="menu:daily"),
         InlineKeyboardButton("❓ HOW TO PLAY", callback_data="menu:help")],
    ])


def mode_menu():
    modes = list(MODE_EMOJI.keys())
    rows = []
    for i in range(0, len(modes), 2):
        row = []
        for mode in modes[i:i+2]:
            row.append(InlineKeyboardButton(
                f"{MODE_EMOJI[mode]} {mode}", callback_data=f"mode:{mode}"
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("🏠 HOME", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def difficulty_menu(mode):
    rows = []
    for i in range(0, len(DIFFICULTIES), 2):
        row = []
        for difficulty in DIFFICULTIES[i:i+2]:
            row.append(InlineKeyboardButton(
                f"{difficulty} • +{XP_VALUES[difficulty]} XP",
                callback_data=f"diff:{mode}:{difficulty}"
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("🎲 ANY DIFFICULTY", callback_data=f"diff:{mode}:Any")])
    rows.append([InlineKeyboardButton("⬅️ MODES", callback_data="menu:play")])
    return InlineKeyboardMarkup(rows)


def round_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 HINT", callback_data="round:hint"),
         InlineKeyboardButton("🛑 END GAME", callback_data="round:end")]
    ])

async def countdown(bot, chat_id, round_id, seconds):
    task = asyncio.current_task()
    try:
        timer_msg = await bot.send_message(chat_id, f"⏱️ <b>{seconds}s</b>", parse_mode="HTML")
        for left in range(seconds - 1, -1, -1):
            await asyncio.sleep(1)
            state = active.get(chat_id)
            if not state or state.get("round_id") != round_id or state.get("phase") != "question":
                return
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=timer_msg.message_id,
                    text=f"⏱️ <b>{left}s</b>" if left else "💥 <b>TIME!</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        state = active.get(chat_id)
        if not state or state.get("round_id") != round_id or state.get("phase") != "question":
            return
        state["phase"] = "result"
        state["closed"] = True
        q = state["question"]
        extra = f"\n\n📖 <b>Answer:</b> {html.escape(str(q.get('a', '')))}"
        if q.get("explain"):
            extra += f"\n💡 {html.escape(q['explain'])}"
        await bot.send_message(chat_id, random.choice(ROAST_TIMEOUT) + extra, parse_mode="HTML")
        starter = state.get("starter")
        if starter:
            add_result(chat_id, starter["id"], starter["name"], reset_streak=True)
        await asyncio.sleep(0.8)
        if active.get(chat_id) is state:
            await send_next_round(bot, chat_id, state)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print("countdown error:", repr(exc))
    finally:
        if countdown_tasks.get(chat_id) is task:
            countdown_tasks.pop(chat_id, None)


async def send_next_round(bot, chat_id, state):
    q = choose_question(state["mode"], state["difficulty"], state["used"])
    if not q:
        active.pop(chat_id, None)
        await bot.send_message(chat_id, "⚠️ Question pool is empty. Pick another mode.")
        return
    state["question"] = q
    state["round_id"] = uuid.uuid4().hex
    state["phase"] = "question"
    state["closed"] = False
    state["round_no"] = state.get("round_no", 0) + 1
    starter = state.get("starter")
    streak = get_player(chat_id, starter["id"])["streak"] if starter else 0
    seconds = timer_for(q)
    xp = xp_for(q)
    text = (
        f"{mode_intro(state['mode'], q.get('difficulty', state['difficulty']))}\n\n"
        f"<b>ROUND {state['round_no']}</b> • +{xp} XP • ⏱️ {seconds}s\n"
        f"🔥 Streak: <b>{streak}</b>\n\n"
        f"❓ <b>{html.escape(q['q'])}</b>\n\n"
        f"👥 <i>First correct wins. Wrong answers do NOT end the round.</i>"
    )
    await bot.send_message(chat_id, text, reply_markup=round_keyboard(), parse_mode="HTML")
    cancel_countdown(chat_id)
    countdown_tasks[chat_id] = asyncio.create_task(
        countdown(bot, chat_id, state["round_id"], seconds)
    )


async def begin_game(message, context, mode, difficulty, user=None):
    chat_id = message.chat_id
    if chat_id in active:
        await message.reply_text("🎮 A game is already running. Press END GAME first.")
        return
    user = user or message.from_user
    name = user.first_name or "Player"
    ensure_player(chat_id, user.id, name)
    active[chat_id] = {
        "mode": mode,
        "difficulty": difficulty,
        "used": set(),
        "starter": {"id": user.id, "name": name},
        "round_no": 0,
        "phase": "loading",
        "closed": False,
    }
    await message.reply_text(
        f"🚀 <b>GAME LOADED</b>\n\n{mode_intro(mode, difficulty)}\n\n"
        "♾️ <b>ENDLESS RUN</b>\n"
        "• Mode + difficulty stay locked\n"
        "• Wrong answers stay alive\n"
        "• Correct answer auto-starts the next round\n"
        "• END GAME stops the run\n\n🔥 <b>GO.</b>",
        parse_mode="HTML",
    )
    await asyncio.sleep(0.4)
    if chat_id in active:
        await send_next_round(context.bot, chat_id, active[chat_id])


async def start(update, context):
    user = update.effective_user
    ensure_player(update.effective_chat.id, user.id, user.first_name or "Player")
    await update.effective_message.reply_text(MAIN_TEXT, reply_markup=mode_menu(), parse_mode="HTML")


async def play(update, context):
    if update.effective_chat.id in active:
        await update.effective_message.reply_text("🎮 Finish the current game first.")
        return
    await update.effective_message.reply_text(
        "🎮 <b>EVERY MODE IS HERE.</b> Pick your chaos:",
        reply_markup=mode_menu(), parse_mode="HTML"
    )


async def game_command(update, context):
    await play(update, context)


async def answer(update, context):
    if not update.message or not update.message.text:
        return
    chat_id = update.effective_chat.id
    user = update.effective_user
    state = active.get(chat_id)
    if not state or state.get("phase") != "question" or state.get("closed"):
        return
    q = state.get("question")
    if not q:
        return
    if not is_correct(q, update.message.text):
        ensure_player(chat_id, user.id, user.first_name or "Player")
        con = db()
        con.execute(
            "UPDATE players SET streak=0 WHERE chat_id=? AND user_id=?",
            (chat_id, user.id),
        )
        con.commit(); con.close()
        if random.random() < 0.75:
            await update.message.reply_text(random.choice(ROAST_WRONG))
        return

    # Close the round before any await: two simultaneous correct answers cannot both win.
    state["closed"] = True
    state["phase"] = "result"
    cancel_countdown(chat_id)
    name = user.first_name or "Player"
    xp = xp_for(q)
    before = get_player(chat_id, user.id)
    old_level = level_from_xp(before["xp"])
    add_result(chat_id, user.id, name, xp=xp, win=True)
    first_win = set_achievement(chat_id, user.id, "first_win")
    after = get_player(chat_id, user.id)
    new_level = level_from_xp(after["xp"])
    streak = after["streak"]

    lines = [
        random.choice(ROAST_CORRECT),
        f"🏆 <b>{html.escape(name)}</b> gets <b>+{xp} XP</b>",
        f"🔥 Streak: <b>{streak}</b>",
    ]
    if streak >= 3:
        lines.append(random.choice(STREAK_LINES).format(streak=streak))
    if new_level > old_level:
        lines.append(
            f"🎉 <b>LEVEL UP!</b> {old_level} → {new_level} • "
            f"{html.escape(title_from_level(new_level))}"
        )
        set_achievement(chat_id, user.id, "level_up")
    if first_win:
        lines.append("🏅 Achievement unlocked: <b>FIRST BLOOD</b>")
    if streak >= 5 and set_achievement(chat_id, user.id, "hot_streak"):
        lines.append("🏅 Achievement unlocked: <b>HOT STREAK</b>")
    if q.get("difficulty") in ("Panic", "Extreme") and set_achievement(chat_id, user.id, "speed_demon"):
        lines.append("🏅 Achievement unlocked: <b>SPEED DEMON</b>")
    if state.get("mode") == "CHAOS MODE" and set_achievement(chat_id, user.id, "chaos"):
        lines.append("🏅 Achievement unlocked: <b>CHAOS SURVIVOR</b>")
    if q.get("explain"):
        lines.append(f"💡 {html.escape(q['explain'])}")
    lines.append("⚡ <b>Next round incoming…</b>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    await asyncio.sleep(0.7)
    if active.get(chat_id) is state:
        await send_next_round(context.bot, chat_id, state)


async def profile(update, context):
    row = get_player(update.effective_chat.id, update.effective_user.id)
    level = level_from_xp(row["xp"])
    await update.effective_message.reply_text(
        f"👤 <b>{html.escape(row['name'])}</b>\n\n"
        f"🏷️ Title: <b>{html.escape(title_from_level(level))}</b>\n"
        f"⭐ Level: <b>{level}</b>\n✨ XP: <b>{row['xp']}</b>\n"
        f"🏆 Wins: <b>{row['wins']}</b>\n🎮 Rounds: <b>{row['games']}</b>\n"
        f"🔥 Streak: <b>{row['streak']}</b>\n💥 Best: <b>{row['best_streak']}</b>\n"
        f"💡 Hints: <b>{row['hints']}</b>",
        reply_markup=main_menu(), parse_mode="HTML"
    )


async def leaderboard(update, context):
    chat_id = update.effective_chat.id
    con = db()
    rows = con.execute(
        "SELECT name,xp,wins,streak FROM players WHERE chat_id=? "
        "ORDER BY xp DESC,wins DESC LIMIT 10", (chat_id,)
    ).fetchall()
    con.close()
    medals = ["🥇", "🥈", "🥉"]
    out = ["🏆 <b>GUESSARENA LEADERBOARD</b>", ""]
    for i, row in enumerate(rows, 1):
        out.append(
            f"{medals[i-1] if i <= 3 else str(i)+'.'} "
            f"<b>{html.escape(row['name'])}</b> — {row['xp']} XP • "
            f"{row['wins']} wins • 🔥{row['streak']}"
        )
    await update.effective_message.reply_text(
        "\n".join(out) if rows else "🏆 No players yet. Start the chaos.",
        reply_markup=main_menu(), parse_mode="HTML"
    )


async def achievements(update, context):
    row = get_player(update.effective_chat.id, update.effective_user.id)
    unlocked = set(filter(None, (row["achievements"] or "").split(",")))
    items = {
        "level_up": "🎉 LEVEL UP",
        "hot_streak": "🔥 HOT STREAK — 5 correct in a row",
        "speed_demon": "⚡ SPEED DEMON",
        "first_win": "🏆 FIRST BLOOD",
        "daily": "📅 DAILY GRINDER",
        "chaos": "🌪️ CHAOS SURVIVOR",
    }
    text = "🏅 <b>ACHIEVEMENTS</b>\n\n" + "\n".join(
        ("✅ " if k in unlocked else "🔒 ") + v for k, v in items.items()
    )
    await update.effective_message.reply_text(text, reply_markup=main_menu(), parse_mode="HTML")


async def stop_cmd(update, context):
    chat_id = update.effective_chat.id
    if chat_id not in active:
        await update.effective_message.reply_text("🛑 No active game. The arena is already sleeping. 😂", reply_markup=main_menu(), parse_mode="HTML")
        return
    cancel_countdown(chat_id)
    active.pop(chat_id, None)
    await update.effective_message.reply_text("🛑 <b>GAME ENDED.</b> Your brain has been released. 😂", reply_markup=main_menu(), parse_mode="HTML")


async def help_cmd(update, context):
    await update.effective_message.reply_text(
        "❓ <b>HOW TO PLAY</b>\n\n"
        "1️⃣ Pick a mode.\n2️⃣ Pick difficulty.\n3️⃣ Answer directly in chat.\n"
        "4️⃣ Correct = XP + automatic next round.\n"
        "5️⃣ Wrong = roast, but the round stays alive.\n"
        "6️⃣ Timeout = answer reveal + next round.\n\n"
        "⏱️ Easy/Medium 15s • Hard/Extreme 20s • Panic 8s\n"
        "♾️ Endless until END GAME.\n"
        "🎯 Target Number accepts a valid expression using every displayed number exactly once.\n"
        "🛑 /stop or END GAME ends the current run.",
        reply_markup=main_menu(), parse_mode="HTML"
    )


async def daily(update, context):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id in active:
        await update.effective_message.reply_text("🎮 Finish the current game first.")
        return
    import hashlib
    pool = QUESTIONS["CHAOS MODE"] + QUESTIONS["Logic"] + QUESTIONS["Trick"]
    seed = int(hashlib.sha256(f"{chat_id}:{date.today().isoformat()}".encode()).hexdigest()[:12], 16)
    q = prepare_question(pool[seed % len(pool)], "DAILY")
    q["xp_override"] = 50
    active[chat_id] = {
        "mode": "DAILY", "difficulty": q.get("difficulty", "Medium"),
        "used": {question_key(q)},
        "starter": {"id": user.id, "name": user.first_name or "Player"},
        "round_no": 0, "phase": "question", "closed": False,
        "question": q, "round_id": uuid.uuid4().hex,
    }
    seconds = timer_for(q)
    await update.effective_message.reply_text(
        f"📅 <b>DAILY CHALLENGE</b> • {seconds}s\n\n"
        f"❓ <b>{html.escape(q['q'])}</b>\n\nFirst correct answer gets <b>+50 XP</b>.",
        reply_markup=round_keyboard(), parse_mode="HTML"
    )
    cancel_countdown(chat_id)
    countdown_tasks[chat_id] = asyncio.create_task(
        countdown(context.bot, chat_id, active[chat_id]["round_id"], seconds)
    )


async def button(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    chat_id = update.effective_chat.id

    if data == "menu:home":
        cancel_countdown(chat_id); active.pop(chat_id, None)
        await query.message.reply_text(MAIN_TEXT, reply_markup=mode_menu(), parse_mode="HTML")
        return
    if data == "menu:play":
        if chat_id in active:
            await query.message.reply_text("🎮 Finish the current game first."); return
        await query.message.reply_text("🎮 <b>CHOOSE YOUR MODE</b>", reply_markup=mode_menu(), parse_mode="HTML")
        return
    if data == "menu:profile":
        # Reuse the command-style profile text directly.
        row = get_player(chat_id, query.from_user.id); level = level_from_xp(row["xp"])
        await query.message.reply_text(
            f"👤 <b>{html.escape(row['name'])}</b>\n\n"
            f"🏷️ {html.escape(title_from_level(level))}\n⭐ Level {level} • ✨ {row['xp']} XP\n"
            f"🏆 {row['wins']} wins • 🎮 {row['games']} rounds\n"
            f"🔥 Streak {row['streak']} • Best {row['best_streak']}\n💡 Hints {row['hints']}",
            reply_markup=main_menu(), parse_mode="HTML"
        ); return
    if data == "menu:leaderboard":
        # Lightweight callback leaderboard.
        con = db(); rows = con.execute(
            "SELECT name,xp,wins FROM players WHERE chat_id=? ORDER BY xp DESC,wins DESC LIMIT 10", (chat_id,)
        ).fetchall(); con.close()
        medals=["🥇","🥈","🥉"]; out=["🏆 <b>LEADERBOARD</b>",""]
        for i,r in enumerate(rows,1): out.append(f"{medals[i-1] if i<=3 else str(i)+'.'} <b>{html.escape(r['name'])}</b> — {r['xp']} XP • {r['wins']} wins")
        await query.message.reply_text("\n".join(out) if rows else "🏆 No players yet.",reply_markup=main_menu(),parse_mode="HTML"); return
    if data == "menu:achievements":
        await achievements(update, context); return
    if data == "menu:help":
        await help_cmd(update, context); return
    if data == "menu:daily":
        await daily(update, context); return
    if data.startswith("mode:"):
        mode = data.split(":", 1)[1]
        if chat_id in active:
            await query.message.reply_text("🎮 Current game active. Finish it first."); return
        await query.message.reply_text(
            f"{MODE_EMOJI.get(mode,'🎮')} <b>{html.escape(mode)}</b>\n\n"
            "Choose difficulty. It stays locked for the whole run.",
            reply_markup=difficulty_menu(mode), parse_mode="HTML"
        ); return
    if data.startswith("diff:"):
        _, mode, difficulty = data.split(":", 2)
        await begin_game(query.message, context, mode, difficulty, query.from_user); return
    if data == "round:end":
        cancel_countdown(chat_id); active.pop(chat_id, None)
        await query.message.reply_text(
            "🛑 <b>GAME ENDED.</b>\n\nFresh chaos whenever you want. 😂",
            reply_markup=main_menu(), parse_mode="HTML"
        ); return
    if data == "round:hint":
        state = active.get(chat_id)
        if not state or state.get("phase") != "question":
            await query.message.reply_text("💨 No active question."); return
        if not spend_hint(chat_id, query.from_user.id):
            await query.message.reply_text("💡 No hints left. Your brain is now the premium feature. 😂"); return
        await query.message.reply_text(
            f"💡 <b>HINT</b> — {html.escape(state['question'].get('hint') or 'The clue is in the wording.')}",
            parse_mode="HTML"
        ); return


async def error_handler(update, context):
    print("Unhandled error:", repr(context.error))


async def telegram_startup(app_bot):
    """Render-safe Telegram startup: clear any old webhook and verify the token."""
    print("[GuessArena] Telegram startup: checking bot connection...", flush=True)
    try:
        await app_bot.bot.delete_webhook(drop_pending_updates=True)
        me = await app_bot.bot.get_me()
        print(f"[GuessArena] Telegram connected as @{me.username or me.first_name} (id={me.id})", flush=True)
    except Exception as exc:
        print(f"[GuessArena] TELEGRAM STARTUP ERROR: {exc!r}", flush=True)
        raise




def validate_game_setup():
    missing = []
    for _mode in MODE_EMOJI:
        if not QUESTIONS.get(_mode):
            missing.append(_mode)
    if missing:
        raise RuntimeError("Missing question banks: " + ", ".join(missing))
    print(f"[GuessArena] Question bank ready: {sum(len(v) for v in QUESTIONS.values())} questions across {len(QUESTIONS)} modes.", flush=True)

def main():
    init_db()
    validate_game_setup()
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing.")
    print("[GuessArena] BOT_TOKEN found. Building Telegram application...", flush=True)
    print("[GuessArena] Python Telegram bot process is starting; Flask health server is separate.", flush=True)
    request = HTTPXRequest(connect_timeout=20, read_timeout=30, write_timeout=30, pool_timeout=30)
    app_bot = (
        Application.builder()
        .token(TOKEN)
        .request(request)
        .post_init(telegram_startup)
        .build()
    )
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("help", help_cmd))
    app_bot.add_handler(CommandHandler("play", play))
    app_bot.add_handler(CommandHandler("game", game_command))
    app_bot.add_handler(CommandHandler("profile", profile))
    app_bot.add_handler(CommandHandler("leaderboard", leaderboard))
    app_bot.add_handler(CommandHandler("achievements", achievements))
    app_bot.add_handler(CommandHandler("daily", daily))
    app_bot.add_handler(CommandHandler("stop", stop_cmd))
    app_bot.add_handler(CommandHandler("cancel", stop_cmd))
    app_bot.add_handler(CallbackQueryHandler(button))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer))
    app_bot.add_error_handler(error_handler)
    print("[GuessArena] All handlers loaded.", flush=True)
    print("GuessArena V3 is LIVE — continuous arena enabled", flush=True)
    print("[GuessArena] Starting polling NOW...", flush=True)
    try:
        app_bot.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except Exception as exc:
        print(f"[GuessArena] POLLING STOPPED: {exc!r}", flush=True)
        raise


if __name__ == "__main__":
    main()
