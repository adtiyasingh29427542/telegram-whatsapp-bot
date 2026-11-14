
from flask import Flask, request
import requests
import os

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")


def setup_webhook():
    if not TOKEN or not BASE_URL:
        print("Bot token or Render URL is missing")
        return

    webhook_url = BASE_URL.rstrip("/") + "/telegram"

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            json={"url": webhook_url},
            timeout=15
        )
        print("Webhook setup:", response.text)
    except Exception as error:
        print("Webhook error:", error)


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


setup_webhook()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
