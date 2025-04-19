import json
import random
from datetime import datetime, timedelta
import sys

import os

# Load vocab from file(s) or from HSK levels
def load_static_vocab(level=None, paths=None):
    vocab = {}

    if level is not None:
        for i in range(1, level + 1):
            filename = f"assets/ap_vocab_hsk{i}.json"
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    vocab.update(data)
            else:
                print(f"⚠️ File not found: {filename}")
    elif paths:
        if isinstance(paths, str):
            paths = [paths]
        for path in paths:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                vocab.update(data)
    else:
        raise ValueError("You must provide either `level` or `paths`.")

    return vocab

# Ensure terminal prints Chinese correctly
sys.stdout.reconfigure(encoding='utf-8')

# Load static vocab
#return json.load(f)

# Load user progress
def load_user_progress(path="storage/user_progress.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Save user progress
def save_user_progress(progress, path="storage/user_progress.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

# Daily word scheduler
NEW_WORDS_PER_DAY = 8
def get_new_words_today(static_vocab, start_date="2025-04-19"):
    vocab_list = list(static_vocab.keys())
    vocab_list.sort()
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    today = datetime.today().date()
    days_elapsed = (today - start).days
    start_index = days_elapsed * NEW_WORDS_PER_DAY
    end_index = start_index + NEW_WORDS_PER_DAY
    return vocab_list[start_index:end_index]

# Build flashcard
def build_flashcard(word, static_vocab, progress_data):
    static = static_vocab.get(word, {})
    progress = progress_data.get(word, {})
    return {
        "word": word,
        "simplified": static.get("simplified", word),
        "traditional": static.get("traditional", ""),
        "pinyin": static.get("pinyin", ""),
        "definitions": static.get("definitions", []),
        "frequency": static.get("frequency", None),
        "progress": progress,
    }

# Update SRS progress based on recall score
def update_progress(progress, word, score):
    data = progress[word]
    ef = data["ef"]
    interval = data["interval"]
    n = data["n"]

    if score < 3:
        interval = 1
        n = 0
    else:
        if n == 0:
            interval = 1
        elif n == 1:
            interval = 6
        else:
            interval = round(interval * ef)
        ef += (0.1 - (5 - score) * (0.08 + (5 - score) * 0.02))
        if ef < 1.3:
            ef = 1.3
        n += 1

    data["n"] = n
    data["ef"] = round(ef, 2)
    data["interval"] = interval
    data["due"] = (datetime.today() + timedelta(days=interval)).date().isoformat()

# =============================
# Runtime logic begins here
# =============================

static_vocab = load_static_vocab(level=3)
user_progress = load_user_progress()

# Add today's new words to progress
new_words_today = get_new_words_today(static_vocab)
for word in new_words_today:
    if word not in user_progress:
        user_progress[word] = {
            "n": 0,
            "ef": 2.5,
            "interval": 0,
            "due": datetime.today().date().isoformat()
        }

# Save immediately
save_user_progress(user_progress)

# Select due words
today = datetime.today().date().isoformat()
due_words = [w for w, d in user_progress.items() if d["due"] <= today]

if not due_words:
    print("No words to review today!")
    exit()

# Cycle through one word at a time
for word in due_words:
    card = build_flashcard(word, static_vocab, user_progress)
    print(f"Word: {card['simplified']}  ({card['traditional']})")
    input("Press ENTER when you're ready to see the definition...")

    print(f"Pinyin: {card['pinyin']}")
    print("Definition(s):")
    for i, definition in enumerate(card['definitions']):
        print(f"  {i+1}. {definition}")

    while True:
        try:
            score = int(input("Rate your recall (0-5): "))
            if 0 <= score <= 5:
                break
            else:
                print("Please enter a number between 0 and 5.")
        except ValueError:
            print("Invalid input. Please enter a number between 0 and 5.")

    update_progress(user_progress, word, score)
    save_user_progress(user_progress)
    print("-" * 40)

print("✅ Study session complete. Great job!")