def passively_update_progress(progress, word, recall_score, freq, today=None):
    if word not in progress:
        return

    today = today or datetime.today().date()
    data = progress[word]

    due_date = datetime.strptime(data["due"], "%Y-%m-%d").date()
    days_overdue = max(0, (today - due_date).days)

    freq_bonus = min(0.5, max(0.0, (0.001 / (freq + 1e-9))))
    decay_bonus = min(0.5, days_overdue / 10)

    recall_weight = recall_score / 5.0

    phantom_score = (recall_weight * 3.0) + freq_bonus + decay_bonus
    if recall_score <= 2:
        phantom_score = -1.0 if recall_score == 2 else -2.0

    ef = data["ef"]
    interval = data["interval"]
    n = data["n"]

    if phantom_score < 0:
        interval = max(1, int(interval * 0.5))
        ef = max(1.3, ef - 0.1)
    else:
        ef += 0.1 - (5 - recall_score) * (0.08 + (5 - recall_score) * 0.02)
        ef = max(1.3, ef)
        if n == 0:
            interval = 1
        elif n == 1:
            interval = 6
        else:
            interval = round(interval * ef)
        n += 1

    data.update(
        {
            "n": n,
            "ef": round(ef, 2),
            "interval": interval,
            "due": (today + timedelta(days=interval)).isoformat(),
            "phantom_last_score": round(phantom_score, 2),
        }
    )


def passively_review_words_from_sentence(
    sentence, progress, static_vocab, recall_score
):
    for word in progress:
        if word in sentence:
            freq = static_vocab.get(word, {}).get("frequency", 0.000001)
            passively_update_progress(progress, word, recall_score, freq)


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


def get_new_words_today(static_vocab, user_progress, limit=8):
    today = datetime.today().date().isoformat()

    # Count how many new words already added today
    already_added_today = [
        word for word, data in user_progress.items()
        if data.get("date_added") == today
    ]

    if len(already_added_today) >= limit:
        return []

    unseen = []
    seen = []

    for word, data in static_vocab.items():
        freq = data.get("frequency", 0.000001)
        if word in user_progress:
            seen.append((word, freq))
        else:
            unseen.append((word, freq))

    unseen_k = min(limit - len(already_added_today), 6)
    seen_k = (limit - len(already_added_today)) - unseen_k

    def weighted_sample(items, k):
        if not items or k <= 0:
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
    """
    Updates a word's spaced repetition schedule based on the user's recall score.

    This logic follows the SM-2 algorithm:
    - Recall scores < 3 are considered failures; repetition count is reset.
    - Scores ≥ 3 are passes; interval grows based on repetition count and ease factor (ef).
    - First and second successful reviews use fixed intervals: 1 day, then 6 days.
    - Later intervals scale by multiplying the previous interval by the ease factor.

    Parameters:
    - progress (dict): user's spaced repetition data
    - word (str): the vocab word being updated
    - score (int): recall rating, from 0 (total failure) to 5 (perfect recall)
    """
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


def fetch_mcq_from_openai(word, definition, review_words=None):
    prompt = f"""Generate a contextual sentence in natural Chinese that clearly demonstrates the meaning of the word '{word}' ({definition}).
"""
    if review_words:
        review_insert = "Also, if it can be done naturally and fluently, try to incorporate one or more of the following review words: "
        review_list = ", ".join(review_words)
        prompt += review_insert + review_list + "."

    prompt += """Then generate 4 English answer choices for what the word means, with only ONE correct answer and 3 plausible distractors.

Respond in this JSON format:
{
  "sentence": "...",
  "question": "What does the word '{word}' most likely mean in this sentence?",
  "options": ["...","...","...","..."],
  "answer_index": 0
}
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
