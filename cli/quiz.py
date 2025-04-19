import json
import random
from datetime import datetime, timedelta
import os
from openai import OpenAI

# Set up OpenAI client
client = OpenAI(
    api_key=""
)


# Load vocab from file(s) or from HSK levels
def load_static_vocab(level=None, paths=None):
    vocab = {}
    if level is not None:
        for i in range(3, level + 1):
            filename = f"assets/ap_vocab_hsk{i}.json"
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    vocab.update(data)
            else:
                print(f"File not found: {filename}")
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


def load_user_progress(path="storage/user_progress.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_user_progress(progress, path="storage/user_progress.json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def get_new_words_today(static_vocab, user_progress, start_date="2025-04-19"):
    NEW_WORDS_PER_DAY = 8

    unseen = []
    seen = []

    for word, data in static_vocab.items():
        freq = data.get("frequency", 0.000001)
        if word in user_progress:
            seen.append((word, freq))
        else:
            unseen.append((word, freq))

    unseen_k = min(NEW_WORDS_PER_DAY, 6)
    seen_k = NEW_WORDS_PER_DAY - unseen_k

    def weighted_sample(items, k):
        if not items:
            return []
        total = sum(f for _, f in items)
        weights = [f / total for _, f in items]
        return random.choices(
            [w for w, _ in items], weights=weights, k=min(k, len(items))
        )

    selected_unseen = weighted_sample(unseen, unseen_k)
    selected_seen = weighted_sample(seen, seen_k)

    return selected_unseen + selected_seen


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
        ef += 0.1 - (5 - score) * (0.08 + (5 - score) * 0.02)
        ef = max(1.3, ef)
        n += 1

    data["n"] = n
    data["ef"] = round(ef, 2)
    data["interval"] = interval
    data["due"] = (datetime.today() + timedelta(days=interval)).date().isoformat()


def fetch_mcq_from_openai(word, definition):
    prompt = f"""
Generate a contextual sentence in natural Chinese that clearly demonstrates the meaning of the word '{word}' ({definition}).
Then generate 4 English answer choices for what the word means, with only ONE correct answer and 3 plausible distractors.

Respond in this JSON format:
{{
  "sentence": "...",
  "question": "What does the word '{word}' most likely mean in this sentence?",
  "options": ["...","...","...","..."],
  "answer_index": 0
}}
"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo-0125",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return eval(response.choices[0].message.content)


def run_quiz(card, static_vocab):
    word = card["simplified"]
    definition = card["definitions"][0] if card["definitions"] else "unknown"
    mcq = fetch_mcq_from_openai(word, definition)
    if not mcq:
        print("Failed to generate question. Skipping this word.")
        return

    print("\nContextual sentence:")
    print(mcq["sentence"])
    print(f"\n{mcq['question']}\n")

    options = mcq["options"]
    correct_index = mcq["answer_index"]

    for idx, opt in enumerate(options):
        print(f"{idx + 1}. {opt}")

    while True:
        try:
            choice = int(input("Enter your choice (1-4): "))
            if 1 <= choice <= 4:
                break
            else:
                print("Please enter a number between 1 and 4.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    if choice - 1 == correct_index:
        print("Correct!")
    else:
        print(f"Incorrect. The correct answer was: '{options[correct_index]}'.")

    print(f"The word '{word}' means '{options[correct_index]}' in this context.")


def main():
    static_vocab = load_static_vocab()
    user_progress = load_user_progress()

    new_words_today = get_new_words_today(static_vocab, user_progress)
    for word in new_words_today:
        if word not in user_progress:
            user_progress[word] = {
                "n": 0,
                "ef": 2.5,
                "interval": 0,
                "due": datetime.today().date().isoformat(),
            }

    save_user_progress(user_progress)

    today = datetime.today().date().isoformat()
    due_words = [w for w, d in user_progress.items() if d["due"] <= today]

    if not due_words:
        print("No words to review today!")
        return

    for word in due_words:
        card = build_flashcard(word, static_vocab, user_progress)
        run_quiz(card, static_vocab)

        while True:
            try:
                score = int(input("Rate your recall (0–5): "))
                if 0 <= score <= 5:
                    break
                else:
                    print("Please enter a number between 0 and 5.")
            except ValueError:
                print("Invalid input. Please enter a number between 0 and 5.")

        update_progress(user_progress, word, score)
        save_user_progress(user_progress)
        print("-" * 40)

    print("Study session complete. Great job!")


if __name__ == "__main__":
    main()
