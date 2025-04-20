from flask import Flask, request, render_template_string, redirect, url_for
import logging
from datetime import datetime
from quiz import (
    passively_review_words_from_sentence,
    load_static_vocab,
    load_user_progress,
    save_user_progress,
    get_new_words_today,
    build_flashcard,
    update_progress,
    fetch_mcq_from_openai,
)

app = Flask(__name__)
logging.basicConfig(filename="app.log", filemode="a", encoding="utf-8", level=logging.INFO)
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
          <tr><td>0:</td><td>Total blackout</td></tr>
          <tr><td>1:</td><td>Incorrect, but felt familiar after seeing the answer</td></tr>
          <tr><td>2:</td><td>Incorrect, but easy once you saw the answer</td></tr>
          <tr><td>3:</td><td>Correct, but hard recall</td></tr>
          <tr><td>4:</td><td>Correct with hesitation</td></tr>
          <tr><td>5:</td><td>Perfect recall</td></tr>
        </table>
        <br/>
        <input type="submit" value="Next">
      </form>
    {% endif %}
  </body>
</html>
"""

current_word = {"word": None, "mcq": None}

@app.route("/", methods=["GET", "POST"])
def quiz():
    try:
        static_vocab = load_static_vocab(level=3)
        global current_word

        if request.method == "POST":
            print("POST form data:", request.form)

            if "next" in request.form:
                score = int(request.form.get("recall", 0))
                if current_word["word"] not in user_progress:
                    today = datetime.today().date().isoformat()
                    user_progress[current_word["word"]] = {
                        "n": 0,
                        "ef": 2.5,
                        "interval": 0,
                        "due": today,
                        "date_added": today,
                    }
                print("Before update:", user_progress[current_word["word"]])
                update_progress(user_progress, current_word["word"], score)
                print("After update:", user_progress[current_word["word"]])

                passively_review_words_from_sentence(
                    current_word["mcq"]["sentence"], user_progress, static_vocab, score
                )
                save_user_progress(user_progress)
                current_word["word"] = None
                current_word["mcq"] = None

            elif "choice" in request.form:
                if not current_word.get("mcq"):
                    current_word["word"] = None
                    current_word["mcq"] = None
                    return redirect(url_for("quiz"))
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
                    card = build_flashcard(word, static_vocab, user_progress)
                    mcq = fetch_mcq_from_openai(card["simplified"], card["definitions"][0])
                    current_word["word"] = word
                    current_word["mcq"] = mcq
                    return render_template_string(TEMPLATE, mcq=mcq, result=None)

            due_words = [
                w for w, d in user_progress.items()
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

    except Exception as e:
        import traceback
        print("ERROR:", e)
        traceback.print_exc()
        return f"<pre>500 Error:\n{traceback.format_exc()}</pre>", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
