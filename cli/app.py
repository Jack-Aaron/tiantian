from flask import Flask, request, render_template_string
from datetime import datetime
from quiz import (
    load_static_vocab,
    load_user_progress,
    save_user_progress,
    get_new_words_today,
    build_flashcard,
    update_progress,
    fetch_mcq_from_openai,
)

app = Flask(__name__)

static_vocab = load_static_vocab(level=3)
user_progress = load_user_progress()

TEMPLATE = """
<!DOCTYPE html>
<html>
  <head><meta charset="utf-8"><title>词汇练习</title></head>
  <body>
    <h2>{{ mcq["sentence"] }}</h2>
    <p>{{ mcq["question"] }}</p>
    <form method="post">
      {% for opt in mcq["options"] %}
        <input type="radio" name="choice" value="{{ loop.index0 }}"> {{ opt }}<br>
      {% endfor %}
      <br/>
      <input type="submit" value="Submit Answer">
    </form>
    {% if result %}
      <p><strong>{{ result }}</strong></p>
      <form method="post">
        <input type="hidden" name="next" value="true">        
        <label>How well did you remember this word (0–5)?</label>
        <input type="number" name="recall" min="0" max="5">
        <br/><br/>
        <table>
          <tr>
            <td>0:</td><td>Total blackout</td>
          </tr>
          <tr>
            <td>1:</td><td>Incorrect, but felt familiar after seeing the answer</td>
          </tr>
          <tr>
            <td>2:</td><td>Incorrect, but easy once you saw the answer</td>
          </tr>
          <tr>
            <td>3:</td><td>Correct, but hard recall</td>
          </tr>
          <tr>
            <td>4:</td><td>Correct with hesitation</td>
          </tr>
          <tr>
            <td>5:</td><td>Perfect recall</td>
          </tr>
        </table>
        <br/>
        <input type="submit" value="Next">
      </form>
    {% endif %}
  </body>
</html>
"""

current_word = {"word": None, "mcq": None}


@app.before_request
def log_request_info():
    print(f"Incoming request: {request.method} {request.url}")


@app.route("/", methods=["GET", "POST"])
def quiz():
    global current_word

    if request.method == "POST":
        if "next" in request.form:
            score = int(request.form.get("recall", 0))
            update_progress(user_progress, current_word["word"], score)
            save_user_progress(user_progress)
            current_word["word"] = None
        else:
            chosen = int(request.form["choice"])
            correct = current_word["mcq"]["answer_index"]
            result = (
                "✅ Correct!"
                if chosen == correct
                else f"❌ Wrong. Correct answer: {current_word['mcq']['options'][correct]}"
            )
            return render_template_string(
                TEMPLATE, mcq=current_word["mcq"], result=result
            )

    if not current_word["word"]:
        today_words = get_new_words_today(static_vocab, user_progress)
        for word in today_words:
            if word not in user_progress:
                user_progress[word] = {
                    "n": 0,
                    "ef": 2.5,
                    "interval": 0,
                    "due": datetime.today().date().isoformat(),
                }
        due_words = [
            w
            for w, d in user_progress.items()
            if d["due"] <= datetime.today().date().isoformat()
        ]
        if not due_words:
            return "🎉 You're all done for today!"
        word = due_words[0]
        card = build_flashcard(word, static_vocab, user_progress)
        mcq = fetch_mcq_from_openai(card["simplified"], card["definitions"][0])
        current_word["word"] = word
        current_word["mcq"] = mcq

    return render_template_string(TEMPLATE, mcq=current_word["mcq"], result=None)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
