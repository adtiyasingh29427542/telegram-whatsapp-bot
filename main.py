from flask import Flask, request
import requests
import os

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

@app.route("/")
def home():
    return "WhatsApp Telegram Bot is Running!"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json(silent=True) or {}
    message = data.get("message", {})

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if chat_id and text and TOKEN:
        if text == "/start":
            reply = "Welcome! Your bot is connected."
        else:
            reply = "Your message received: " + text

        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": reply},
            timeout=15
        )

    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
