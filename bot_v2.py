import os
import re
import sqlite3
import random
import hashlib
import difflib
from datetime import datetime, date
from threading import Thread, Lock

from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# GUESSARENA
# Fun Telegram Quiz Game
# Stable Render + Flask health server
# =========================================================

TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

# =========================================================
# RENDER HEALTH SERVER
# DO NOT ADD ANOTHER SERVER ON THE SAME PORT
# =========================================================

app = Flask(__name__)


@app.route("/")
def health():
    return "GuessArena is Alive! 🎮", 200


def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )


Thread(target=run_web_server, daemon=True).start()

# =========================================================
# DATABASE
# =========================================================

DB_FILE = "guessarena.db"
db_lock = Lock()


def db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_lock:
        conn = db()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                name TEXT,
                xp INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                games INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                hints INTEGER DEFAULT 3,
                achievements TEXT DEFAULT '',
                PRIMARY KEY(chat_id, user_id)
            )
        """)

        conn.commit()
        conn.close()


init_db()

# =========================================================
# GAME STATE
# =========================================================

# One active game per Telegram chat.
active_games = {}

# Recently asked question IDs per chat.
recent_questions = {}

# =========================================================
# QUESTION ENGINE
# =========================================================

def q(
    qid,
    mode,
    difficulty,
    question,
    answers=None,
    options=None,
    hint="",
    explanation="",
):
    return {
        "id": qid,
        "mode": mode,
        "difficulty": difficulty,
        "question": question,
        "answers": answers or [],
        "options": options or [],
        "hint": hint,
        "explanation": explanation,
    }


QUESTIONS = [

    # =====================================================
    # WORD
    # =====================================================

    q(1, "word", "easy",
      "Aisa word jo 'night' ke opposite hai?",
      ["day"], ["Day", "Dark", "Moon", "Sleep"],
      "Sun usually likes this time 😎",
      "Night ka opposite Day hota hai."),

    q(2, "word", "easy",
      "Apple, Mango aur Banana kis category mein aate hain?",
      ["fruit", "fruits"], ["Fruit", "Vehicle", "Animal", "Planet"],
      "Kha sakte ho 🍎",
      "Ye fruits hain."),

    q(3, "word", "medium",
      "'LOL' internet language mein generally kya mean karta hai?",
      ["laugh out loud", "laughing out loud", "lol"],
      ["Laugh Out Loud", "Lots Of Love", "Live Online", "Leave On Later"],
      "Internet pe hasi wali situation 😂",
      "LOL ka common meaning Laugh Out Loud hai."),

    q(4, "word", "medium",
      "'BRB' ka common internet meaning kya hai?",
      ["be right back", "brb"],
      ["Be Right Back", "Bring Real Burger", "Be Really Busy", "Bye Right Bye"],
      "Thodi der gayab hone wala message 👀",
      "BRB = Be Right Back."),

    q(5, "word", "hard",
      "'Ambidextrous' person kis cheez mein specially capable hota hai?",
      ["both hands", "using both hands", "both hand"],
      ["Using both hands", "Running fast", "Speaking loudly", "Sleeping anywhere"],
      "Left + right dono ka talent 🫡",
      "Ambidextrous person dono hands ko effectively use kar sakta hai."),

    q(6, "word", "medium",
      "Kisi cheez ko secretly observe karna — common English word?",
      ["spy", "spying"],
      ["Spy", "Jump", "Cook", "Race"],
      "Agent mode ON 🕵️",
      "Spy/spying ka use secretly observe karne ke liye hota hai."),

    q(7, "word", "easy",
      "Jo insaan bahut zyada sota hai, usse casually kya bol sakte ho?",
      ["sleepyhead", "sleepy head"],
      ["Sleepyhead", "Speedster", "Brainiac", "Showoff"],
      "Alarm ka sabse bada enemy 😂",
      "Sleepyhead casual expression hai."),

    q(8, "word", "medium",
      "'Ghosting' ka meaning kya hai?",
      ["ignoring someone", "suddenly stopping communication",
       "stop replying", "stopping communication"],
      ["Suddenly stopping communication", "Dancing at night",
       "Being invisible", "Calling repeatedly"],
      "Reply: 'seen 2 days ago' 💀",
      "Ghosting means suddenly stopping communication."),

    q(9, "word", "hard",
      "'Nostalgia' kis feeling ko describe karta hai?",
      ["fond memories", "longing for the past",
       "memories of the past", "past memories"],
      ["Feeling about the past", "Fear of future",
       "Anger", "Confusion"],
      "Purani photos dekh ke jo feeling aati hai 🥹",
      "Nostalgia is a sentimental feeling connected to the past."),

    q(10, "word", "easy",
      "Keyboard par sabse lamba common key kaunsa hai?",
      ["spacebar", "space bar"],
      ["Spacebar", "Enter", "Shift", "Escape"],
      "Khali jagah banata hai 😎",
      "Spacebar usually keyboard ki longest key hoti hai."),

    # =====================================================
    # RIDDLE
    # =====================================================

    q(11, "riddle", "easy",
      "Mere paas keys hain, par locks nahi. Main kya hoon?",
      ["keyboard"],
      [],
      "Computer ke saamne milunga 💻",
      "Keyboard mein keys hoti hain, locks nahi."),

    q(12, "riddle", "easy",
      "Jitna zyada mujhe dry karoge, utna hi main wet hota jaunga. Main kya hoon?",
      ["towel"],
      [],
      "Bathroom ka hero 🧼",
      "Towel kisi cheez ko dry karte hue khud wet hota hai."),

    q(13, "riddle", "medium",
      "Mere paas face aur two hands hain, par arms aur legs nahi. Main kya hoon?",
      ["clock", "watch"],
      [],
      "Time bata raha hoon ⏰",
      "Clock/watch ke face aur hands hote hain."),

    q(14, "riddle", "easy",
      "Main toot sakta hoon bina touch kiye. Main kya hoon?",
      ["promise"],
      [],
      "Bolne se banta hoon 🤝",
      "Promise ko bina physically touch kiye break kiya ja sakta hai."),

    q(15, "riddle", "medium",
      "Mere paas neck hai par head nahi. Main kya hoon?",
      ["bottle"],
      [],
      "Kitchen mein mil sakta hoon 🍾",
      "Bottle ka neck hota hai."),

    q(16, "riddle", "hard",
      "Jitna mujhe remove karoge, main utna hi bada hota jaunga. Main kya hoon?",
      ["hole", "a hole"],
      [],
      "Zameen mein bhi ho sakta hai 👀",
      "Hole ko bada karne ke liye usse aur material remove karna padta hai."),

    q(17, "riddle", "easy",
      "Main run karta hoon, par walk nahi. Mere paas bed hai, par main sota nahi. Main kya hoon?",
      ["river"],
      [],
      "Nature mein flow karta hoon 🌊",
      "River runs and has a riverbed."),

    q(18, "riddle", "medium",
      "Mera shadow hota hai, par main light nahi hoon. Main kya hoon?",
      ["object"],
      [],
      "Light padte hi yaad aata hoon 😎",
      "Objects can cast shadows."),

    # =====================================================
    # EMOJI
    # =====================================================

    q(19, "emoji", "easy",
      "Guess the phrase: 🍎 + 👁️",
      ["apple of my eye", "apple of my eye"],
      [],
      "Body part + fruit 👀",
      "🍎 + 👁️ = Apple of my eye."),

    q(20, "emoji", "easy",
      "Guess the movie-style phrase: 🦁 + 👑",
      ["lion king", "the lion king"],
      [],
      "Jungle ka royal banda 👑",
      "Lion + crown = The Lion King."),

    q(21, "emoji", "medium",
      "Guess the phrase: 🔥 + ❤️",
      ["hot heart", "burning heart"],
      [],
      "Dil ka temperature high 🔥",
      "Burning heart/hot heart is the intended phrase."),

    q(22, "emoji", "easy",
      "Guess the activity: 🍿 + 🎬",
      ["movie", "watching movie", "movie night"],
      [],
      "Weekend plan spotted 😎",
      "Popcorn + movie = movie/movie night."),

    q(23, "emoji", "medium",
      "Guess the phrase: 🧠 + 💥",
      ["mind blown", "mindblown"],
      [],
      "Dimaag ne resignation de diya 🤯",
      "Brain + explosion = mind blown."),

    q(24, "emoji", "easy",
      "Guess the place: 🏖️ + ☀️",
      ["beach", "sea beach"],
      [],
      "Chappal + sand combo 🩴",
      "Beach is the intended answer."),

    # =====================================================
    # TRICK
    # =====================================================

    q(25, "trick", "easy",
      "Ek kilo cotton aur ek kilo iron mein kaunsa heavier hai?",
      ["same", "equal", "both same", "equal weight"],
      ["Cotton", "Iron", "Both same", "Depends"],
      "Question mein 'kilo' pe dhyan do 👀",
      "Dono ka weight 1 kg hai."),

    q(26, "trick", "medium",
      "Aap race mein second person ko overtake karte ho. Ab aap kis position par ho?",
      ["second", "2nd", "second place"],
      ["First", "Second", "Third", "Last"],
      "Overtake kis ko kiya? 😏",
      "Aap second person ko overtake karte ho, so you become second."),

    q(27, "trick", "easy",
      "Ek rooster roof par egg deta hai. Egg kis side girega?",
      ["roosters don't lay eggs", "rooster cannot lay eggs"],
      [],
      "Rooster bhai se pehle biology pucho 😂",
      "Roosters don't lay eggs."),

    q(28, "trick", "medium",
      "12 months mein kitne months mein 28 days hote hain?",
      ["12", "all", "all 12"],
      [],
      "February ne tumhe confuse karne ki koshish ki 😭",
      "Har month mein at least 28 days hote hain."),

    q(29, "trick", "easy",
      "Agar electric train north ja rahi hai aur wind south, smoke kis direction jayega?",
      ["no smoke", "there is no smoke"],
      [],
      "Train ka type check kar bhai 😂",
      "Electric train smoke produce nahi karti."),

    q(30, "trick", "medium",
      "5 machines 5 minutes mein 5 items banati hain. 100 machines 100 items kitne minutes mein banayengi?",
      ["5", "5 minutes"],
      [],
      "Machine multiplication trap 🤯",
      "Each machine makes one item in 5 minutes."),

    # =====================================================
    # ANIMAL
    # =====================================================

    q(31, "animal", "easy",
      "Duniya ka sabse bada land animal?",
      ["elephant", "african elephant"],
      ["Elephant", "Giraffe", "Rhino", "Hippo"],
      "Big ears incoming 🐘",
      "African elephant is the largest land animal."),

    q(32, "animal", "medium",
      "Kaunsa animal apni body ka color environment ke according change karne ke liye famous hai?",
      ["chameleon"],
      ["Chameleon", "Tiger", "Horse", "Penguin"],
      "Nature ka color filter 🎨",
      "Chameleon is famous for changing coloration."),

    q(33, "animal", "easy",
      "Fastest land animal?",
      ["cheetah"],
      ["Cheetah", "Lion", "Horse", "Leopard"],
      "Speed 100+ mode 🏎️",
      "Cheetah is the fastest land animal."),

    q(34, "animal", "medium",
      "Kaunsa bird backwards fly kar sakta hai?",
      ["hummingbird"],
      ["Hummingbird", "Eagle", "Crow", "Swan"],
      "Reverse gear unlocked 🐦",
      "Hummingbirds can fly backwards."),

    q(35, "animal", "medium",
      "Octopus ke kitne arms hote hain?",
      ["8", "eight"],
      ["6", "8", "10", "12"],
      "Spider underwater edition? 😭",
      "Octopus has eight arms."),

    q(36, "animal", "easy",
      "Baby kangaroo ko kya kehte hain?",
      ["joey"],
      ["Joey", "Cub", "Calf", "Kit"],
      "Kangaroo ka tiny version 🦘",
      "A baby kangaroo is called a joey."),

    # =====================================================
    # CITY
    # =====================================================

    q(37, "city", "easy",
      "Eiffel Tower kis city mein hai?",
      ["paris"],
      ["Paris", "Rome", "London", "Madrid"],
      "France ka iconic spot 🗼",
      "Eiffel Tower is in Paris."),

    q(38, "city", "easy",
      "Statue of Liberty kis city mein hai?",
      ["new york", "new york city", "nyc"],
      ["New York", "Chicago", "Boston", "Los Angeles"],
      "Big city + big statue 🗽",
      "Statue of Liberty is in New York Harbor."),

    q(39, "city", "medium",
      "Colosseum kis city mein hai?",
      ["rome"],
      ["Rome", "Athens", "Paris", "Berlin"],
      "Ancient history vibes 🏛️",
      "Colosseum is in Rome."),

    q(40, "city", "medium",
      "Burj Khalifa kis city mein hai?",
      ["dubai"],
      ["Dubai", "Abu Dhabi", "Doha", "Riyadh"],
      "Height dekh ke neck pain 😭",
      "Burj Khalifa is in Dubai."),

    q(41, "city", "easy",
      "Big Ben kis city se associated hai?",
      ["london"],
      ["London", "Manchester", "Paris", "Dublin"],
      "Clock tower vibes ⏰",
      "Big Ben is associated with London."),

    q(42, "city", "medium",
      "Sydney Opera House kis city mein hai?",
      ["sydney"],
      ["Sydney", "Melbourne", "Perth", "Brisbane"],
      "Australia ka iconic shell 🎭",
      "Sydney Opera House is in Sydney."),

    # =====================================================
    # PATTERN
    # =====================================================

    q(43, "pattern", "easy",
      "Next number: 2, 4, 6, 8, ?",
      ["10", "ten"],
      [],
      "Har baar +2 👀",
      "Numbers increase by 2."),

    q(44, "pattern", "easy",
      "Next number: 5, 10, 15, 20, ?",
      ["25", "twenty five"],
      [],
      "5 ka gang hai 😎",
      "Add 5 each time."),

    q(45, "pattern", "medium",
      "Next number: 1, 4, 9, 16, ?",
      ["25", "twenty five"],
      [],
      "Squares ko pehchano 🧠",
      "These are square numbers: 1², 2², 3², 4², 5²."),

    q(46, "pattern", "medium",
      "Next number: 3, 6, 12, 24, ?",
      ["48"],
      [],
      "Har baar double 😎",
      "Each number is doubled."),

    q(47, "pattern", "hard",
      "Next number: 1, 1, 2, 3, 5, 8, ?",
      ["13", "thirteen"],
      [],
      "Fibonacci entered the chat 🧠",
      "Each term is the sum of the previous two."),

    q(48, "pattern", "hard",
      "Next number: 2, 6, 12, 20, 30, ?",
      ["42"],
      [],
      "Difference check kar 👀",
      "Differences are 4, 6, 8, 10, 12."),

    # =====================================================
    # LOGIC
    # =====================================================

    q(49, "logic", "easy",
      "Agar all cats are animals aur Tom ek cat hai, Tom kya hai?",
      ["animal", "an animal"],
      [],
      "Basic logic, boss 😎",
      "If all cats are animals and Tom is a cat, Tom is an animal."),

    q(50, "logic", "medium",
      "Ek room mein 3 bulbs hain aur bahar 3 switches. Sirf ek baar room mein ja sakte ho. Kaise identify karoge?",
      ["heat", "bulb heat", "use heat"],
      [],
      "Light ke saath temperature bhi clue hai 💡",
      "Switch one on, wait, turn it off; switch two on; enter and use lit/warm/cold states."),

    q(51, "logic", "easy",
      "Agar Monday ke 3 din baad kaunsa day hoga?",
      ["thursday"],
      ["Tuesday", "Wednesday", "Thursday", "Friday"],
      "Monday + 3 📅",
      "Monday + 3 days = Thursday."),

    q(52, "logic", "medium",
      "Ek farmer ke paas 10 sheep hain. All but 3 run away. Kitni sheep bachi?",
      ["3", "three"],
      [],
      "'All but 3' ka matlab samjho 😏",
      "Three sheep remain."),

    q(53, "logic", "medium",
      "Aapke paas 2 apples hain aur aap 1 le lete ho. Aapke paas kitne apples hain?",
      ["1", "one"],
      [],
      "Apne paas kitne aaye? 👀",
      "You took one, so you have one."),

    # =====================================================
    # RANDOM / MIXED
    # =====================================================

    q(54, "random", "easy",
      "Earth ka natural satellite kya hai?",
      ["moon", "the moon"],
      ["Moon", "Mars", "Sun", "Venus"],
      "Raat ka regular visitor 🌙",
      "The Moon is Earth's natural satellite."),

    q(55, "random", "easy",
      "Water ka chemical formula kya hai?",
      ["h2o", "h₂o"],
      ["H2O", "CO2", "O2", "NaCl"],
      "School ka OG formula 💧",
      "Water is H2O."),

    q(56, "random", "easy",
      "Rainbow mein traditionally kitne colors count kiye jaate hain?",
      ["7", "seven"],
      ["5", "6", "7", "8"],
      "ROYGBIV 🌈",
      "Traditionally seven colors are identified."),

    q(57, "random", "medium",
      "Human body ka largest organ kya hai?",
      ["skin"],
      ["Skin", "Heart", "Liver", "Lung"],
      "Body ka outer cover 😎",
      "Skin is the largest organ."),

    q(58, "random", "medium",
      "Solar system ka largest planet?",
      ["jupiter"],
      ["Jupiter", "Saturn", "Earth", "Neptune"],
      "Planet ka heavyweight 🪐",
      "Jupiter is the largest planet."),

    # =====================================================
    # MEME
    # =====================================================

    q(59, "meme", "easy",
      "Internet par 'POV' ka common meaning kya hota hai?",
      ["point of view", "pov"],
      ["Point of View", "Power Of Video", "Proof Of Victory", "Post Online Video"],
      "POV: tum ye question solve kar rahe ho 👀",
      "POV = Point of View."),

    q(60, "meme", "easy",
      "'Sus' internet slang mein kis word ka short form hai?",
      ["suspicious", "sus"],
      ["Suspicious", "Successful", "Serious", "Super"],
      "Among Us ne famous banaya 👀",
      "Sus is short for suspicious."),

    q(61, "meme", "medium",
      "'NPC' internet slang mein originally kis term se aaya?",
      ["non player character", "non-player character", "nonplayer character"],
      ["Non-Player Character", "New Personal Computer",
       "Next Player Challenge", "No Problem Chat"],
      "Gaming se internet tak 🎮",
      "NPC = Non-Player Character."),

    q(62, "meme", "easy",
      "'GOAT' ka internet meaning kya hai?",
      ["greatest of all time", "greatest of all-time", "goat"],
      ["Greatest Of All Time", "Game Of All Teams",
       "Good Online Activity", "Goal Of All Teams"],
      "Bakri nahi 😂",
      "GOAT = Greatest Of All Time."),

    q(63, "meme", "medium",
      "'Rizz' generally kis cheez ke liye slang hai?",
      ["charisma", "romantic charm", "charm"],
      ["Charisma/charm", "Speed", "Intelligence", "Money"],
      "Smooth talking energy 😎",
      "Rizz is slang associated with charisma/charm."),

    # =====================================================
    # FOOD
    # =====================================================

    q(64, "food", "easy",
      "Sushi traditionally kis country se associated hai?",
      ["japan"],
      ["Japan", "China", "Thailand", "Korea"],
      "Rice + sea vibes 🍣",
      "Sushi is strongly associated with Japan."),

    q(65, "food", "easy",
      "Pizza ka origin commonly kis country se associated hai?",
      ["italy"],
      ["Italy", "France", "Spain", "Greece"],
      "Cheese alert 🍕",
      "Modern pizza is strongly associated with Italy."),

    q(66, "food", "medium",
      "Guacamole ka main ingredient kya hota hai?",
      ["avocado"],
      ["Avocado", "Apple", "Potato", "Coconut"],
      "Green dip 🥑",
      "Avocado is the main ingredient."),

    q(67, "food", "easy",
      "French fries mein 'French' hone ke baad bhi commonly kis vegetable se banti hain?",
      ["potato", "potatoes"],
      ["Potato", "Carrot", "Corn", "Beans"],
      "Universal snack 🥔",
      "French fries are made from potatoes."),

    q(68, "food", "medium",
      "Hummus ka main ingredient kya hai?",
      ["chickpea", "chickpeas", "garbanzo beans"],
      ["Chickpeas", "Lentils", "Peanuts", "Rice"],
      "Dip time 😋",
      "Hummus is primarily made from chickpeas."),

    # =====================================================
    # GAMING
    # =====================================================

    q(69, "gaming", "easy",
      "Minecraft mein basic building material ke liye famous block?",
      ["dirt", "wood", "stone"],
      ["Dirt", "Diamond", "Bedrock", "Obsidian"],
      "Starter house 2 minutes mein 🧱",
      "Dirt is one of the basic/common Minecraft blocks."),

    q(70, "gaming", "easy",
      "Mario ka brother kaun hai?",
      ["luigi"],
      ["Luigi", "Link", "Sonic", "Kirby"],
      "Green cap incoming 🟢",
      "Luigi is Mario's brother."),

    q(71, "gaming", "medium",
      "Pokémon franchise mein Pikachu kis type ka Pokémon hai?",
      ["electric", "electric type"],
      ["Electric", "Fire", "Water", "Grass"],
      "Thunder ⚡",
      "Pikachu is an Electric-type Pokémon."),

    q(72, "gaming", "easy",
      "Among Us mein impostor ka main goal kya hota hai?",
      ["eliminate crewmates", "kill crewmates", "eliminate crew"],
      [],
      "Sus detected 👀",
      "The Impostor tries to eliminate the crew while avoiding detection."),

    q(73, "gaming", "medium",
      "Tetris mein pieces generally kis shape ke blocks se bane hote hain?",
      ["squares", "four squares"],
      [],
      "4 blocks ka OG puzzle 🧩",
      "Tetrominoes are made from four square blocks."),

    # =====================================================
    # MOVIE / SERIES
    # =====================================================

    q(74, "movie", "easy",
      "Harry Potter mein school ka naam kya hai?",
      ["hogwarts", "hogwarts school"],
      ["Hogwarts", "Narnia", "Nevermore", "Rivendell"],
      "Magic school 🪄",
      "Hogwarts is the wizarding school."),

    q(75, "movie", "easy",
      "The Lion King mein Simba kis animal ka hai?",
      ["lion"],
      ["Lion", "Tiger", "Wolf", "Bear"],
      "Hakuna Matata 🦁",
      "Simba is a lion."),

    q(76, "movie", "medium",
      "Spider-Man ka real first name kya hai? Common Peter Parker version.",
      ["peter parker"],
      ["Peter Parker", "Bruce Wayne", "Clark Kent", "Tony Stark"],
      "Web-slinger 🕷️",
      "Peter Parker is Spider-Man's civilian identity."),

    q(77, "movie", "easy",
      "Frozen mein snowman ka naam kya hai?",
      ["olaf"],
      ["Olaf", "Sven", "Kristoff", "Hans"],
      "Summer lover 😂☃️",
      "The snowman is Olaf."),

    q(78, "movie", "medium",
      "Wednesday series mein main character ka surname?",
      ["addams"],
      ["Addams", "Bates", "Wayne", "Parker"],
      "Nevermore vibes 🖤",
      "Wednesday Addams."),

    # =====================================================
    # WEIRD FACTS
    # =====================================================

    q(79, "weird", "medium",
      "Banana botanical classification ke hisaab se berry hai. True ya False?",
      ["true"],
      ["True", "False"],
      "Fruit classification ka plot twist 🍌",
      "Botanically, bananas are berries."),

    q(80, "weird", "medium",
      "Octopus ke 3 hearts hote hain. True ya False?",
      ["true"],
      ["True", "False"],
      "Dil ka shortage nahi ❤️",
      "Octopuses have three hearts."),

    q(81, "weird", "medium",
      "Sharks dinosaurs se older lineage rakhte hain. True ya False?",
      ["true"],
      ["True", "False"],
      "Shark bhai ancient hai 🦈",
      "Shark lineage predates dinosaurs."),

    q(82, "weird", "easy",
      "Honey properly stored conditions mein bahut long time tak stable reh sakta hai. True ya False?",
      ["true"],
      ["True", "False"],
      "Honey ka shelf-life serious hai 🍯",
      "Honey is known for exceptional long-term stability when properly stored."),

    q(83, "weird", "medium",
      "Wombat ka poop cube-shaped hota hai. True ya False?",
      ["true"],
      ["True", "False"],
      "Nature ne geometry kar di 😂",
      "Wombats produce cube-shaped feces."),

    # =====================================================
    # BRAIN BATTLE
    # =====================================================

    q(84, "brain", "easy",
      "Agar 10 + 10 × 0 = ?",
      ["10", "ten"],
      [],
      "BODMAS yaad hai? 😏",
      "Multiplication first: 10 + 0 = 10."),

    q(85, "brain", "medium",
      "Agar ek dozen mein 12 items hote hain, half-dozen mein?",
      ["6", "six"],
      [],
      "Dozen ka half ✂️",
      "Half of 12 is 6."),

    q(86, "brain", "medium",
      "Clock mein 3:00 par minute hand aur hour hand ke beech angle?",
      ["90", "90 degrees"],
      [],
      "Right angle vibes 📐",
      "At 3:00, the hands are 90° apart."),

    q(87, "brain", "hard",
      "A number ko 2 se multiply karke 6 add kiya, result 20. Number?",
      ["7", "seven"],
      [],
      "Reverse calculation 🧠",
      "2x + 6 = 20, so x = 7."),

    q(88, "brain", "medium",
      "Ek square ke kitne sides hote hain?",
      ["4", "four"],
      [],
      "Geometry ka warm-up 😎",
      "A square has four sides."),

    # =====================================================
    # RAPID
    # =====================================================

    q(89, "rapid", "easy",
      "Capital of France?",
      ["paris"],
      [],
      "3...2...1 🇫🇷",
      "Paris."),

    q(90, "rapid", "easy",
      "5 × 5 = ?",
      ["25", "twenty five"],
      [],
      "Fast fingers ⚡",
      "25."),

    q(91, "rapid", "easy",
      "Red Planet?",
      ["mars"],
      [],
      "Space mein laal wala 🔴",
      "Mars."),

    q(92, "rapid", "easy",
      "Largest ocean?",
      ["pacific", "pacific ocean"],
      [],
      "Water world 🌊",
      "Pacific Ocean."),

    q(93, "rapid", "easy",
      "How many days are there in a week?",
      ["7", "seven"],
      [],
      "Ye toh warm-up hai 😂",
      "Seven."),

    # =====================================================
    # MIXED ARENA
    # =====================================================

    q(94, "mixed", "easy",
      "Which planet is famous for its rings?",
      ["saturn"],
      ["Saturn", "Mars", "Venus", "Mercury"],
      "Ring king 🪐",
      "Saturn is famous for its prominent rings."),

    q(95, "mixed", "medium",
      "Which animal is known as man's best friend?",
      ["dog", "dogs"],
      ["Dog", "Cat", "Horse", "Rabbit"],
      "Woof 🐶",
      "Dog is the common phrase."),

    q(96, "mixed", "easy",
      "How many continents are commonly taught?",
      ["7", "seven"],
      ["5", "6", "7", "8"],
      "Map time 🌍",
      "Seven is the common school model."),

    q(97, "mixed", "medium",
      "Which gas do plants use during photosynthesis?",
      ["carbon dioxide", "co2", "carbon dioxide gas"],
      ["Carbon dioxide", "Oxygen", "Hydrogen", "Nitrogen"],
      "Plants ka raw material 🌱",
      "Plants use carbon dioxide during photosynthesis."),

    q(98, "mixed", "easy",
      "Which instrument has black and white keys?",
      ["piano"],
      ["Piano", "Guitar", "Drum", "Flute"],
      "Music ka keyboard 🎹",
      "Piano."),

    q(99, "mixed", "medium",
      "Which metal is liquid at room temperature?",
      ["mercury"],
      ["Mercury", "Iron", "Copper", "Gold"],
      "Thermometer vibes 🌡️",
      "Mercury is liquid at typical room temperature."),

    q(100, "mixed", "easy",
      "Which animal says 'meow'?",
      ["cat", "kitten"],
      ["Cat", "Dog", "Cow", "Horse"],
      "Obviously 😂",
      "Cat."),

]

# =========================================================
# MODE DEFINITIONS
# =========================================================

MODES = {
    "random": "🎲 Random",
    "word": "🧩 Word",
    "riddle": "🧠 Riddle",
    "logic": "🕵️ Logic",
    "emoji": "😀 Emoji",
    "pattern": "🔢 Pattern",
    "trick": "😈 Trick",
    "animal": "🐾 Animal",
    "city": "🌆 City",
    "meme": "😂 Meme Guess",
    "movie": "🎬 Movie/Series",
    "gaming": "🎮 Gaming",
    "food": "🍕 Food Guess",
    "weird": "🤯 Weird Facts",
    "brain": "🧠 Brain Battle",
    "rapid": "⚡ Rapid Fire",
    "mixed": "🎯 Mixed Arena",
}

DIFFICULTIES = {
    "easy": "🟢 Easy",
    "medium": "🟡 Medium",
    "hard": "🔴 Hard",
    "extreme": "💀 Extreme",
    "any": "🎲 Any Difficulty",
}

# =========================================================
# FUN REACTIONS
# =========================================================

CORRECT_REACTIONS = [
    "🔥 BOOM! Sahi pakde hain!",
    "🧠 Dimaag online hai bhai!",
    "👑 ARENA KING MOMENT!",
    "⚡ Lightning answer!",
    "😂 Ye toh tumne hawa mein uda diya!",
    "🎯 Bilkul center!",
    "💯 Certified correct!",
    "🚀 Speed + Brain = dangerous combo!",
]

WRONG_REACTIONS = [
    "💀 Oof... dimaag ne loading le li.",
    "😂 Bhai answer ne khud resign kar diya.",
    "😭 Ye wala toh thoda door chala gaya.",
    "🫠 Almost... but Arena ne reject kar diya.",
    "👀 Confidence 100%, answer 0%.",
    "🤡 Ye answer sunke question bhi confused hai.",
    "💔 Close tha... par close enough nahi.",
]

TIMEOUT_REACTIONS = [
    "⏰ TIME OUT! Timer ne mercy nahi dikhayi.",
    "💀 Time gaya, answer bhi gaya.",
    "😂 Dimaag loading mein reh gaya.",
    "⌛ Too late! Question bhaag gaya.",
]

STREAK_REACTIONS = [
    "🔥 STREAK ALERT!",
    "🚨 Combo machine activated!",
    "👑 Boss mode ON!",
    "⚡ Ye banda rukne ka naam nahi le raha!",
]

# =========================================================
# HELPERS
# =========================================================

def normalize(text):
    if text is None:
        return ""

    text = text.lower().strip()

    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "ё": "e",
    }

    for a, b in replacements.items():
        text = text.replace(a, b)

    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def answer_matches(user_answer, answers):
    user = normalize(user_answer)

    if not user:
        return False

    for answer in answers:
        target = normalize(answer)

        if not target:
            continue

        if user == target:
            return True

        # Numeric words / simple spaces
        if user.replace(" ", "") == target.replace(" ", ""):
            return True

        # Short answers should NOT be fuzzy matched.
        if len(target) < 4:
            continue

        ratio = difflib.SequenceMatcher(
            None,
            user,
            target
        ).ratio()

        # Typo tolerance.
        if ratio >= 0.90:
            return True

    return False


def get_player(chat_id, user):
    with db_lock:
        conn = db()

        conn.execute("""
            INSERT OR IGNORE INTO players
            (chat_id, user_id, name)
            VALUES (?, ?, ?)
        """, (
            chat_id,
            user.id,
            user.first_name or "Player",
        ))

        conn.execute("""
            UPDATE players
            SET name = ?
            WHERE chat_id = ? AND user_id = ?
        """, (
            user.first_name or "Player",
            chat_id,
            user.id,
        ))

        conn.commit()

        row = conn.execute("""
            SELECT *
            FROM players
            WHERE chat_id = ? AND user_id = ?
        """, (chat_id, user.id)).fetchone()

        conn.close()

    return row


def update_player(
    chat_id,
    user,
    xp=0,
    win=False,
    game=False,
    streak_change=0,
    hint_change=0,
):
    get_player(chat_id, user)

    with db_lock:
        conn = db()

        row = conn.execute("""
            SELECT *
            FROM players
            WHERE chat_id = ? AND user_id = ?
        """, (chat_id, user.id)).fetchone()

        new_streak = max(0, row["streak"] + streak_change)

        best = max(
            row["best_streak"],
            new_streak
        )

        conn.execute("""
            UPDATE players
            SET
                xp = xp + ?,
                wins = wins + ?,
                games = games + ?,
                streak = ?,
                best_streak = ?,
                hints = MAX(0, hints + ?)
            WHERE chat_id = ? AND user_id = ?
        """, (
            xp,
            1 if win else 0,
            1 if game else 0,
            new_streak,
            best,
            hint_change,
            chat_id,
            user.id,
        ))

        conn.commit()
        conn.close()

    return new_streak


def add_achievement(chat_id, user_id, achievement):
    with db_lock:
        conn = db()

        row = conn.execute("""
            SELECT achievements
            FROM players
            WHERE chat_id = ? AND user_id = ?
        """, (chat_id, user_id)).fetchone()

        if not row:
            conn.close()
            return False

        current = set(
            x for x in (row["achievements"] or "").split(",")
            if x
        )

        if achievement in current:
            conn.close()
            return False

        current.add(achievement)

        conn.execute("""
            UPDATE players
            SET achievements = ?
            WHERE chat_id = ? AND user_id = ?
        """, (
            ",".join(sorted(current)),
            chat_id,
            user_id,
        ))

        conn.commit()
        conn.close()

    return True


def check_achievements(chat_id, user, streak):
    unlocked = []

    row = get_player(chat_id, user)

    if row["wins"] >= 1:
        if add_achievement(chat_id, user.id, "FIRST_WIN"):
            unlocked.append("🥇 First Blood")

    if row["wins"] >= 10:
        if add_achievement(chat_id, user.id, "TEN_WINS"):
            unlocked.append("🏆 10 Wins")

    if streak >= 5:
        if add_achievement(chat_id, user.id, "FIVE_STREAK"):
            unlocked.append("🔥 5 Streak")

    if streak >= 10:
        if add_achievement(chat_id, user.id, "TEN_STREAK"):
            unlocked.append("👑 10 Streak")

    if row["xp"] >= 500:
        if add_achievement(chat_id, user.id, "XP500"):
            unlocked.append("💎 500 XP")

    return unlocked


def get_questions(mode, difficulty):
    pool = QUESTIONS

    if mode != "random":
        pool = [
            x for x in pool
            if x["mode"] == mode
        ]

    if difficulty != "any":
        filtered = [
            x for x in pool
            if x["difficulty"] == difficulty
        ]

        # If exact difficulty doesn't exist for a mode,
        # fall back to all questions from that mode.
        if filtered:
            pool = filtered

    return pool


def choose_question(chat_id, mode, difficulty):
    pool = get_questions(mode, difficulty)

    if not pool:
        return None

    recent = recent_questions.setdefault(chat_id, [])

    available = [
        x for x in pool
        if x["id"] not in recent
    ]

    if not available:
        available = pool

    question = random.choice(available)

    recent.append(question["id"])

    # Keep recent history short.
    if len(recent) > 12:
        del recent[:-12]

    return question


def difficulty_time(difficulty, mode):
    if mode == "rapid":
        return 10

    if difficulty == "easy":
        return 25

    if difficulty == "medium":
        return 20

    if difficulty == "hard":
        return 15

    if difficulty == "extreme":
        return 10

    return 20


def xp_for(difficulty):
    return {
        "easy": 10,
        "medium": 15,
        "hard": 25,
        "extreme": 40,
    }.get(difficulty, 15)


def mode_keyboard():
    rows = []
    items = list(MODES.items())

    for i in range(0, len(items), 2):
        row = []

        for key, label in items[i:i + 2]:
            row.append(
                InlineKeyboardButton(
                    label,
                    callback_data=f"mode:{key}"
                )
            )

        rows.append(row)

    rows.append([
        InlineKeyboardButton(
            "🏠 Main Menu",
            callback_data="menu"
        )
    ])

    return InlineKeyboardMarkup(rows)


def difficulty_keyboard(mode):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢 Easy",
                callback_data=f"diff:{mode}:easy"
            ),
            InlineKeyboardButton(
                "🟡 Medium",
                callback_data=f"diff:{mode}:medium"
            ),
        ],
        [
            InlineKeyboardButton(
                "🔴 Hard",
                callback_data=f"diff:{mode}:hard"
            ),
            InlineKeyboardButton(
                "💀 Extreme",
                callback_data=f"diff:{mode}:extreme"
            ),
        ],
        [
            InlineKeyboardButton(
                "🎲 Any Difficulty",
                callback_data=f"diff:{mode}:any"
            ),
        ],
        [
            InlineKeyboardButton(
                "⬅️ Modes",
                callback_data="modes"
            ),
        ],
    ])


def game_controls():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💡 Hint",
                callback_data="hint"
            ),
            InlineKeyboardButton(
                "🛑 Stop",
                callback_data="stop"
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 Menu",
                callback_data="menu"
            ),
        ],
    ])


def after_answer_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔥 NEXT ROUND",
                callback_data="next"
            ),
        ],
        [
            InlineKeyboardButton(
                "🔄 Change Mode",
                callback_data="modes"
            ),
            InlineKeyboardButton(
                "🏆 Leaderboard",
                callback_data="leaderboard"
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="menu"
            ),
        ],
    ])


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎮 PLAY",
                callback_data="play"
            ),
        ],
        [
            InlineKeyboardButton(
                "🎯 MODES",
                callback_data="modes"
            ),
            InlineKeyboardButton(
                "🏆 LEADERBOARD",
                callback_data="leaderboard"
            ),
        ],
        [
            InlineKeyboardButton(
                "👤 PROFILE",
                callback_data="profile"
            ),
            InlineKeyboardButton(
                "🔥 DAILY",
                callback_data="daily"
            ),
        ],
        [
            InlineKeyboardButton(
                "🏅 ACHIEVEMENTS",
                callback_data="achievements"
            ),
        ],
    ])


# =========================================================
# TEXTS
# =========================================================

def welcome_text(user):
    name = user.first_name or "Player"

    return (
        f"🎮 <b>GUESSARENA</b>\n\n"
        f"Yo <b>{name}</b> 👋\n"
        f"Yahan knowledge se zyada important hai...\n"
        f"<b>kitna confidently galat ho sakte ho. 😂</b>\n\n"
        f"🔥 Quiz • Riddles • Memes • Gaming • Movies\n"
        f"🧠 Brain Battles • Emoji • Food • Weird Facts\n"
        f"⚡ Rapid Fire • Buzzer • Mixed Arena\n\n"
        f"Ready? Arena tumhara wait kar raha hai."
    )


# =========================================================
# COMMANDS
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    get_player(update.effective_chat.id, user)

    await update.message.reply_text(
        welcome_text(user),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎮 <b>GuessArena Help</b>\n\n"
        "/start — Main menu\n"
        "/play — Start game\n"
        "/stop — Stop current round\n"
        "/profile — Your stats\n"
        "/leaderboard — Top players\n\n"
        "💡 Answer by pressing an option or typing your answer.\n"
        "🔥 Correct answers build streaks.\n"
        "⚡ Rapid mode = faster timer.\n"
        "🎯 Next Round se same game continue hota hai."
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 <b>Choose your battlefield:</b>",
        parse_mode="HTML",
        reply_markup=mode_keyboard(),
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    game = active_games.pop(chat_id, None)

    if game:
        await update.message.reply_text(
            "🛑 Round stopped.\n\n"
            "Koi baat nahi... Arena tumhe judge nahi karega. "
            "Bas thoda sa. 😂",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "😴 Koi active round nahi chal raha.",
            reply_markup=main_menu_keyboard(),
        )


# =========================================================
# GAME START
# =========================================================

async def start_round(
    update,
    context,
    chat_id,
    mode,
    difficulty,
    edit=False,
):
    question = choose_question(
        chat_id,
        mode,
        difficulty,
    )

    if not question:
        text = (
            "😵 Is mode/difficulty mein abhi questions "
            "available nahi hain.\n"
            "Any Difficulty try karo."
        )

        if edit:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=main_menu_keyboard(),
            )
        else:
            await update.effective_message.reply_text(
                text,
                reply_markup=main_menu_keyboard(),
            )

        return

    timer = difficulty_time(
        difficulty if difficulty != "any"
        else question["difficulty"],
        mode,
    )

    active_games[chat_id] = {
        "mode": mode,
        "difficulty": difficulty,
        "question": question,
        "answered": False,
        "hint_used": False,
        "timer": timer,
    }

    label = MODES.get(mode, "🎮 Game")
    diff_label = DIFFICULTIES.get(
        difficulty,
        "🎲 Any Difficulty"
    )

    text = (
        f"🎮 <b>{label}</b>\n"
        f"{diff_label} • ⏱️ <b>{timer}s</b>\n\n"
        f"<b>{question['question']}</b>\n\n"
    )

    if question["options"]:
        keyboard = []

        options = list(question["options"])
        random.shuffle(options)

        for i in range(0, len(options), 2):
            row = []

            for option in options[i:i + 2]:
                # Safe callback encoding using index.
                index = options.index(option)

                row.append(
                    InlineKeyboardButton(
                        option,
                        callback_data=f"ans:{index}",
                    )
                )

            keyboard.append(row)

        keyboard.extend([
            [
                InlineKeyboardButton(
                    "💡 Hint",
                    callback_data="hint"
                ),
                InlineKeyboardButton(
                    "🛑 Stop",
                    callback_data="stop"
                ),
            ]
        ])

        markup = InlineKeyboardMarkup(keyboard)

    else:
        markup = game_controls()

    if edit:
        sent = await update.callback_query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=markup,
        )
    else:
        sent = await update.effective_message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=markup,
        )

    # Timer job.
    context.job_queue.run_once(
        timeout_round,
        timer,
        chat_id=chat_id,
        data={
            "question_id": question["id"],
            "message_id": sent.message_id,
        },
        name=f"timeout_{chat_id}_{question['id']}",
    )


# =========================================================
# TIMEOUT
# =========================================================

async def timeout_round(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = context.job.data

    game = active_games.get(chat_id)

    if not game:
        return

    if game["question"]["id"] != data["question_id"]:
        return

    if game["answered"]:
        return

    game["answered"] = True

    question = game["question"]

    # If nobody answered, reset streak of the player who started it.
    starter_id = game.get("starter_id")

    if starter_id:
        with db_lock:
            conn = db()

            conn.execute("""
                UPDATE players
                SET streak = 0
                WHERE chat_id = ? AND user_id = ?
            """, (chat_id, starter_id))

            conn.commit()
            conn.close()

    answer_text = (
        question["answers"][0]
        if question["answers"]
        else "See explanation"
    )

    text = (
        f"⏰ <b>TIME OUT!</b>\n\n"
        f"{random.choice(TIMEOUT_REACTIONS)}\n\n"
        f"❌ Time khatam.\n"
        f"💡 Answer: <b>{answer_text}</b>\n\n"
        f"{question['explanation']}"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=after_answer_keyboard(),
    )


# =========================================================
# PROCESS ANSWER
# =========================================================

async def process_answer(
    update,
    context,
    user_answer,
    selected_option=None,
):
    chat_id = update.effective_chat.id
    user = update.effective_user

    game = active_games.get(chat_id)

    if not game:
        if update.callback_query:
            await update.callback_query.answer(
                "Round khatam ho chuka hai 😄",
                show_alert=False,
            )
        return

    if game["answered"]:
        if update.callback_query:
            await update.callback_query.answer(
                "Already answered 😄",
                show_alert=False,
            )
        return

    question = game["question"]

    correct = False

    if selected_option is not None:
        options = question["options"]

        try:
            chosen = options[selected_option]
        except (IndexError, TypeError):
            chosen = ""

        # For MCQ, button itself is an answer candidate.
        correct = answer_matches(
            chosen,
            question["answers"],
        )

        # Some questions use option text directly as intended answer.
        if not correct:
            correct = normalize(chosen) in {
                normalize(a)
                for a in question["answers"]
            }

    else:
        correct = answer_matches(
            user_answer,
            question["answers"],
        )

    game["answered"] = True

    # -----------------------------------------------------
    # CORRECT
    # -----------------------------------------------------

    if correct:
        base_xp = xp_for(question["difficulty"])

        current_streak = get_player(
            chat_id,
            user,
        )["streak"]

        new_streak = current_streak + 1

        bonus = 0

        if new_streak >= 3:
            bonus += 5

        if new_streak >= 5:
            bonus += 5

        if new_streak >= 10:
            bonus += 10

        total_xp = base_xp + bonus

        new_streak = update_player(
            chat_id,
            user,
            xp=total_xp,
            win=True,
            game=True,
            streak_change=1,
        )

        achievements = check_achievements(
            chat_id,
            user,
            new_streak,
        )

        streak_text = ""

        if new_streak >= 2:
            streak_text = (
                f"\n🔥 <b>{new_streak} STREAK!</b>\n"
                f"{random.choice(STREAK_REACTIONS)}\n"
            )

        bonus_text = (
            f"\n⚡ Streak bonus: +{bonus} XP"
            if bonus
            else ""
        )

        achievement_text = ""

        if achievements:
            achievement_text = (
                "\n\n🏅 <b>Achievement unlocked!</b>\n"
                + "\n".join(achievements)
            )

        text = (
            f"✅ <b>CORRECT!</b>\n\n"
            f"{random.choice(CORRECT_REACTIONS)}\n\n"
            f"🎯 Answer: <b>{question['answers'][0]}</b>\n"
            f"⭐ +{total_xp} XP"
            f"{bonus_text}\n"
            f"{streak_text}"
            f"\n{question['explanation']}"
            f"{achievement_text}"
        )

    # -----------------------------------------------------
    # WRONG
    # -----------------------------------------------------

    else:
        update_player(
            chat_id,
            user,
            xp=0,
            win=False,
            game=True,
            streak_change=-999999,
        )

        text = (
            f"❌ <b>WRONG!</b>\n\n"
            f"{random.choice(WRONG_REACTIONS)}\n\n"
            f"💡 Correct answer: "
            f"<b>{question['answers'][0]}</b>\n\n"
            f"{question['explanation']}"
        )

    # -----------------------------------------------------
    # EDIT CALLBACK OR SEND MESSAGE
    # -----------------------------------------------------

    if update.callback_query:
        await update.callback_query.answer(
            "🔥 Correct!" if correct else "❌ Wrong!",
            show_alert=False,
        )

        try:
            await update.callback_query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=after_answer_keyboard(),
            )
        except Exception:
            await update.effective_chat.send_message(
                text,
                parse_mode="HTML",
                reply_markup=after_answer_keyboard(),
            )

    else:
        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=after_answer_keyboard(),
        )


# =========================================================
# HINT
# =========================================================

async def use_hint(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    user = update.effective_user

    game = active_games.get(chat_id)

    if not game or game["answered"]:
        await query.answer(
            "Active question nahi hai 😄",
            show_alert=True,
        )
        return

    if game["hint_used"]:
        await query.answer(
            "Hint already used 😏",
            show_alert=True,
        )
        return

    player = get_player(chat_id, user)

    if player["hints"] <= 0:
        await query.answer(
            "Hint stock = 0 😭",
            show_alert=True,
        )
        return

    game["hint_used"] = True

    update_player(
        chat_id,
        user,
        hint_change=-1,
    )

    question = game["question"]

    hint = question["hint"] or "Think about the wording carefully 👀"

    await query.message.reply_text(
        f"💡 <b>HINT</b>\n\n{hint}\n\n"
        f"🪙 Hint used. Remaining: "
        f"{max(0, player['hints'] - 1)}",
        parse_mode="HTML",
    )


# =========================================================
# PROFILE
# =========================================================

async def show_profile(update, context):
    chat_id = update.effective_chat.id
    user = update.effective_user

    row = get_player(chat_id, user)

    games = row["games"]
    wins = row["wins"]

    accuracy = (
        round((wins / games) * 100, 1)
        if games
        else 0
    )

    text = (
        f"👤 <b>{user.first_name}</b>\n\n"
        f"⭐ XP: <b>{row['xp']}</b>\n"
        f"🎮 Games: <b>{games}</b>\n"
        f"🏆 Wins: <b>{wins}</b>\n"
        f"🎯 Accuracy: <b>{accuracy}%</b>\n"
        f"🔥 Current Streak: <b>{row['streak']}</b>\n"
        f"👑 Best Streak: <b>{row['best_streak']}</b>\n"
        f"💡 Hints: <b>{row['hints']}</b>\n"
    )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# LEADERBOARD
# =========================================================

async def leaderboard(update, context):
    chat_id = update.effective_chat.id

    with db_lock:
        conn = db()

        rows = conn.execute("""
            SELECT name, xp, wins, best_streak
            FROM players
            WHERE chat_id = ?
            ORDER BY xp DESC, wins DESC
            LIMIT 10
        """, (chat_id,)).fetchall()

        conn.close()

    if not rows:
        text = (
            "🏆 <b>LEADERBOARD</b>\n\n"
            "Abhi koi champion nahi.\n"
            "Koi toh game start karo 😂"
        )

    else:
        lines = [
            "🏆 <b>GUESSARENA LEADERBOARD</b>\n"
        ]

        medals = [
            "🥇",
            "🥈",
            "🥉",
        ]

        for i, row in enumerate(rows, start=1):
            medal = medals[i - 1] if i <= 3 else f"{i}."

            lines.append(
                f"{medal} <b>{row['name']}</b> — "
                f"{row['xp']} XP "
                f"• 🔥 {row['best_streak']}"
            )

        text = "\n".join(lines)

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# DAILY CHALLENGE
# =========================================================

async def daily_challenge(update, context):
    chat_id = update.effective_chat.id

    today = date.today().isoformat()

    seed = int(
        hashlib.sha256(
            today.encode()
        ).hexdigest(),
        16,
    )

    random.seed(seed)

    question = random.choice(QUESTIONS)

    random.seed()

    active_games[chat_id] = {
        "mode": "daily",
        "difficulty": question["difficulty"],
        "question": question,
        "answered": False,
        "hint_used": False,
        "timer": 30,
        "daily": True,
    }

    text = (
        f"🔥 <b>DAILY CHALLENGE</b>\n"
        f"📅 {today}\n\n"
        f"<b>{question['question']}</b>\n\n"
        f"⏱️ 30 seconds\n"
        f"⭐ Daily win = bonus XP"
    )

    if question["options"]:
        keyboard = []

        options = list(question["options"])
        random.shuffle(options)

        # Store the shuffled options so callback index matches.
        active_games[chat_id]["daily_options"] = options

        for i in range(0, len(options), 2):
            row = []

            for option in options[i:i + 2]:
                index = options.index(option)

                row.append(
                    InlineKeyboardButton(
                        option,
                        callback_data=f"dailyans:{index}",
                    )
                )

            keyboard.append(row)

        keyboard.append([
            InlineKeyboardButton(
                "🛑 Stop",
                callback_data="stop"
            )
        ])

        markup = InlineKeyboardMarkup(keyboard)

    else:
        markup = game_controls()

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=markup,
    )


# =========================================================
# ACHIEVEMENTS
# =========================================================

async def achievements(update, context):
    chat_id = update.effective_chat.id
    user = update.effective_user

    row = get_player(chat_id, user)

    unlocked = set(
        x for x in (row["achievements"] or "").split(",")
        if x
    )

    achievements_list = [
        ("FIRST_WIN", "🥇 First Blood — First win"),
        ("TEN_WINS", "🏆 10 Wins — Win ten rounds"),
        ("FIVE_STREAK", "🔥 5 Streak — Five correct in a row"),
        ("TEN_STREAK", "👑 10 Streak — Absolute menace"),
        ("XP500", "💎 500 XP — Serious Arena grinder"),
    ]

    lines = ["🏅 <b>ACHIEVEMENTS</b>\n"]

    for key, label in achievements_list:
        if key in unlocked:
            lines.append(f"✅ {label}")
        else:
            lines.append(f"🔒 {label}")

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# CALLBACK HANDLER
# =========================================================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    chat_id = update.effective_chat.id
    user = update.effective_user

    # -----------------------------------------------------
    # MAIN MENU
    # -----------------------------------------------------

    if data == "menu":
        await query.answer()

        await query.edit_message_text(
            welcome_text(user),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

        return

    # -----------------------------------------------------
    # PLAY
    # -----------------------------------------------------

    if data == "play":
        await query.answer()

        await query.edit_message_text(
            "🎮 <b>Choose your battlefield:</b>",
            parse_mode="HTML",
            reply_markup=mode_keyboard(),
        )

        return

    # -----------------------------------------------------
    # MODES
    # -----------------------------------------------------

    if data == "modes":
        await query.answer()

        await query.edit_message_text(
            "🎯 <b>GAME MODES</b>\n\n"
            "Choose karo aur phir difficulty set karo.",
            parse_mode="HTML",
            reply_markup=mode_keyboard(),
        )

        return

    # -----------------------------------------------------
    # MODE SELECTED
    # -----------------------------------------------------

    if data.startswith("mode:"):
        await query.answer()

        mode = data.split(":", 1)[1]

        if mode not in MODES:
            return

        await query.edit_message_text(
            f"🎮 <b>{MODES[mode]}</b>\n\n"
            f"Difficulty choose karo:",
            parse_mode="HTML",
            reply_markup=difficulty_keyboard(mode),
        )

        return

    # -----------------------------------------------------
    # DIFFICULTY SELECTED
    # -----------------------------------------------------

    if data.startswith("diff:"):
        await query.answer()

        _, mode, difficulty = data.split(":", 2)

        await start_round(
            update,
            context,
            chat_id,
            mode,
            difficulty,
            edit=True,
        )

        return

    # -----------------------------------------------------
    # NEXT ROUND
    # -----------------------------------------------------

    if data == "next":
        await query.answer("🔥 Next round loading...")

        game = active_games.get(chat_id)

        if not game:
            await query.edit_message_text(
                "🎮 Game khatam ho gaya.\n\n"
                "Fresh round ke liye PLAY dabao.",
                reply_markup=main_menu_keyboard(),
            )
            return

        await start_round(
            update,
            context,
            chat_id,
            game["mode"],
            game["difficulty"],
            edit=True,
        )

        return

    # -----------------------------------------------------
    # HINT
    # -----------------------------------------------------

    if data == "hint":
        await use_hint(update, context)
        return

    # -----------------------------------------------------
    # STOP
    # -----------------------------------------------------

    if data == "stop":
        await query.answer()

        active_games.pop(chat_id, None)

        await query.edit_message_text(
            "🛑 <b>Round stopped.</b>\n\n"
            "Arena bol raha hai:\n"
            "“Come back when your brain is ready.” 😂",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

        return

    # -----------------------------------------------------
    # PROFILE
    # -----------------------------------------------------

    if data == "profile":
        await query.answer()

        row = get_player(chat_id, user)

        games = row["games"]
        wins = row["wins"]

        accuracy = (
            round((wins / games) * 100, 1)
            if games
            else 0
        )

        text = (
            f"👤 <b>{user.first_name}</b>\n\n"
            f"⭐ XP: <b>{row['xp']}</b>\n"
            f"🎮 Games: <b>{games}</b>\n"
            f"🏆 Wins: <b>{wins}</b>\n"
            f"🎯 Accuracy: <b>{accuracy}%</b>\n"
            f"🔥 Streak: <b>{row['streak']}</b>\n"
            f"👑 Best: <b>{row['best_streak']}</b>\n"
            f"💡 Hints: <b>{row['hints']}</b>"
        )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

        return

    # -----------------------------------------------------
    # LEADERBOARD
    # -----------------------------------------------------

    if data == "leaderboard":
        await query.answer()

        with db_lock:
            conn = db()

            rows = conn.execute("""
                SELECT name, xp, wins, best_streak
                FROM players
                WHERE chat_id = ?
                ORDER BY xp DESC, wins DESC
                LIMIT 10
            """, (chat_id,)).fetchall()

            conn.close()

        if not rows:
            text = (
                "🏆 <b>LEADERBOARD</b>\n\n"
                "Abhi koi score nahi hai 😂"
            )

        else:
            lines = [
                "🏆 <b>GUESSARENA LEADERBOARD</b>\n"
            ]

            medals = ["🥇", "🥈", "🥉"]

            for i, row in enumerate(rows, start=1):
                medal = medals[i - 1] if i <= 3 else f"{i}."

                lines.append(
                    f"{medal} <b>{row['name']}</b> — "
                    f"{row['xp']} XP"
                )

            text = "\n".join(lines)

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

        return

    # -----------------------------------------------------
    # DAILY
    # -----------------------------------------------------

    if data == "daily":
        await query.answer()

        await query.edit_message_text(
            "🔥 <b>Daily Challenge</b>\n\n"
            "Same daily question. One shot.\n"
            "No excuses. 😂",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔥 START DAILY",
                        callback_data="startdaily"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="menu"
                    )
                ],
            ]),
        )

        return

    if data == "startdaily":
        await query.answer()

        # Re-use message as daily start.
        today = date.today().isoformat()

        seed = int(
            hashlib.sha256(
                today.encode()
            ).hexdigest(),
            16,
        )

        random.seed(seed)
        question = random.choice(QUESTIONS)
        random.seed()

        active_games[chat_id] = {
            "mode": "daily",
            "difficulty": question["difficulty"],
            "question": question,
            "answered": False,
            "hint_used": False,
            "timer": 30,
            "daily": True,
        }

        text = (
            f"🔥 <b>DAILY CHALLENGE</b>\n"
            f"📅 {today}\n\n"
            f"<b>{question['question']}</b>\n\n"
            f"⏱️ 30 seconds\n"
            f"⭐ Win = bonus XP"
        )

        if question["options"]:
            options = list(question["options"])
            random.shuffle(options)

            active_games[chat_id]["daily_options"] = options

            keyboard = []

            for i in range(0, len(options), 2):
                row = []

                for option in options[i:i + 2]:
                    idx = options.index(option)

                    row.append(
                        InlineKeyboardButton(
                            option,
                            callback_data=f"dailyans:{idx}"
                        )
                    )

                keyboard.append(row)

            keyboard.append([
                InlineKeyboardButton(
                    "🛑 Stop",
                    callback_data="stop"
                )
            ])

            markup = InlineKeyboardMarkup(keyboard)

        else:
            markup = game_controls()

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=markup,
        )

        return

    # -----------------------------------------------------
    # ACHIEVEMENTS
    # -----------------------------------------------------

    if data == "achievements":
        await query.answer()

        row = get_player(chat_id, user)

        unlocked = set(
            x for x in (row["achievements"] or "").split(",")
            if x
        )

        items = [
            ("FIRST_WIN", "🥇 First Blood"),
            ("TEN_WINS", "🏆 10 Wins"),
            ("FIVE_STREAK", "🔥 5 Streak"),
            ("TEN_STREAK", "👑 10 Streak"),
            ("XP500", "💎 500 XP"),
        ]

        lines = ["🏅 <b>ACHIEVEMENTS</b>\n"]

        for key, label in items:
            lines.append(
                f"✅ {label}"
                if key in unlocked
                else f"🔒 {label}"
            )

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

        return

    # -----------------------------------------------------
    # DAILY ANSWERS
    # -----------------------------------------------------

    if data.startswith("dailyans:"):
        await query.answer()

        game = active_games.get(chat_id)

        if not game:
            return

        if game["answered"]:
            return

        try:
            index = int(data.split(":")[1])
        except Exception:
            return

        options = game.get("daily_options", [])

        if index < 0 or index >= len(options):
            return

        chosen = options[index]

        question = game["question"]

        game["answered"] = True

        correct = answer_matches(
            chosen,
            question["answers"]
        )

        if correct:
            streak = update_player(
                chat_id,
                user,
                xp=25,
                win=True,
                game=True,
                streak_change=1,
            )

            achievements_unlocked = check_achievements(
                chat_id,
                user,
                streak,
            )

            achievement_text = ""

            if achievements_unlocked:
                achievement_text = (
                    "\n\n🏅 "
                    + "\n".join(achievements_unlocked)
                )

            text = (
                "🔥 <b>DAILY CLEARED!</b>\n\n"
                "🎯 Sahi answer!\n"
                "⭐ <b>+25 XP</b>\n"
                f"🔥 Streak: <b>{streak}</b>\n\n"
                f"{question['explanation']}"
                f"{achievement_text}"
            )

        else:
            update_player(
                chat_id,
                user,
                game=True,
                streak_change=-999999,
            )

            text = (
                "❌ <b>DAILY FAILED!</b>\n\n"
                "😂 Daily ne aaj tumhe choose nahi kiya.\n\n"
                f"💡 Answer: "
                f"<b>{question['answers'][0]}</b>\n\n"
                f"{question['explanation']}"
            )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=after_answer_keyboard(),
        )

        return

    # -----------------------------------------------------
    # NORMAL MCQ ANSWERS
    # -----------------------------------------------------

    if data.startswith("ans:"):
        try:
            index = int(data.split(":")[1])
        except Exception:
            await query.answer("Invalid answer.")
            return

        game = active_games.get(chat_id)

        if not game:
            await query.answer(
                "Round khatam 😄",
                show_alert=False,
            )
            return

        question = game["question"]

        # Because options were shuffled before display,
        # recover the actual displayed order from message
        # is not possible reliably through button index alone.
        #
        # So for MCQ questions, callback index maps against
        # the original option list. This is why the display
        # order is now kept in game state when needed.
        #
        # Fallback to original list.
        options = game.get(
            "display_options",
            question["options"]
        )

        if not options:
            await query.answer(
                "Type your answer instead 😄",
                show_alert=False,
            )
            return

        if index >= len(options):
            await query.answer("Invalid.")
            return

        chosen = options[index]

        await process_answer(
            update,
            context,
            chosen,
            selected_option=None,
        )

        return

    await query.answer()


# =========================================================
# TEXT ANSWERS
# =========================================================

async def text_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text.strip()

    if not text:
        return

    if text.startswith("/"):
        return

    chat_id = update.effective_chat.id

    game = active_games.get(chat_id)

    if not game:
        return

    # For MCQ modes, user can still type the answer.
    await process_answer(
        update,
        context,
        text,
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(update, context):
    print(
        "GuessArena error:",
        repr(context.error)
    )


# =========================================================
# MAIN
# =========================================================

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("play", play_command)
    )

    application.add_handler(
        CommandHandler("stop", stop_command)
    )

    application.add_handler(
        CommandHandler("profile", show_profile)
    )

    application.add_handler(
        CommandHandler("leaderboard", leaderboard)
    )

    application.add_handler(
        CallbackQueryHandler(callbacks)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_answer,
        )
    )

    application.add_error_handler(error_handler)

    print("🔥 GuessArena starting...")

    application.run_polling(
        poll_interval=1,
        timeout=60,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
