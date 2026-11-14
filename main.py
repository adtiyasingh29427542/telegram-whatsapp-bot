
from flask import Flask, request
import requests
import os

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")

API = f"https://api.telegram.org/bot{TOKEN}"


def send_message(chat_id, text, keyboard=None):
    payload = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        payload["reply_markup"] = keyboard

    requests.post(
        f"{API}/sendMessage",
        json=payload,
        timeout=15
    )


def main_menu(chat_id):
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📱 WhatsApp Accounts", "callback_data": "accounts"},
                {"text": "👥 Add Contacts", "callback_data": "contacts"}
            ],
            [
                {"text": "📤 Excel Upload", "callback_data": "excel"},
                {"text": "🚀 Create Broadcast", "callback_data": "broadcast"}
            ],
            [
                {"text": "🤖 Auto Reply", "callback_data": "autoreply"},
                {"text": "💳 Credits & Plans", "callback_data": "credits"}
            ],
            [
                {"text": "📜 Campaign History", "callback_data": "history"},
                {"text": "❓ Help", "callback_data": "help"}
            ]
        ]
    }

    send_message(
        chat_id,
        "Welcome to My WP Broadcaster Bot! ❤️\n\nChoose an option:",
        keyboard
    )


@app.route("/")
def home():
    return "WhatsApp Telegram Bot is Running!"


@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json(silent=True) or {}

    message = data.get("message", {})
    callback = data.get("callback_query")

    if message:
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")

        if chat_id and text:
            if text == "/start":
                main_menu(chat_id)
            else:
                send_message(
                    chat_id,
                    "Please choose an option from the menu.",
                )

    if callback:
        callback_id = callback.get("id")
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        choice = callback.get("data", "")

        requests.post(
            f"{API}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=15
        )

        options = {
            "accounts": "WhatsApp Accounts: Account connection feature is coming soon.",
            "contacts": "Add Contacts: Contact management is coming soon.",
            "excel": "Excel Upload: Excel import is coming soon.",
            "broadcast": "Create Broadcast: Campaign feature is coming soon.",
            "autoreply": "Auto Reply: Auto reply feature is coming soon.",
            "credits": "Credits & Plans: Subscription feature is coming soon.",
            "history": "Campaign History: History feature is coming soon.",
            "help": "Help: Contact support for assistance."
        }

        if chat_id:
            send_message(
                chat_id,
                options.get(choice, "Please choose an option.")
            )

    return {"ok": True}


def setup_webhook():
    if TOKEN and BASE_URL:
        try:
            response = requests.post(
                f"{API}/setWebhook",
                json={"url": BASE_URL.rstrip("/") + "/telegram"},
                timeout=15
            )
            print("Webhook setup:", response.text)
        except Exception as error:
            print("Webhook error:", error)


setup_webhook()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
