
from flask import Flask, request
import requests
import os
import psycopg2

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

API = f"https://api.telegram.org/bot{TOKEN}"


# DATABASE CONNECTION
def save_user(user):
    if not DATABASE_URL:
        print("DATABASE_URL is missing")
        return False

    try:
        db_url = DATABASE_URL.replace(
            "postgres://", "postgresql://", 1
        )

        conn = psycopg2.connect(
            db_url,
            connect_timeout=10
        )

        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                telegram_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_seen TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        cur.execute("""
            INSERT INTO customers
            (telegram_id, username, first_name, last_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_seen = NOW()
        """, (
            user.get("id"),
            user.get("username"),
            user.get("first_name"),
            user.get("last_name")
        ))

        conn.commit()
        cur.close()
        conn.close()

        print("Customer saved:", user.get("id"))
        return True

    except Exception as error:
        print("Database error:", error)
        return False


# SEND TELEGRAM MESSAGE
def send_message(chat_id, text, keyboard=None):
    if not TOKEN:
        return

    payload = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        payload["reply_markup"] = keyboard

    try:
        requests.post(
            f"{API}/sendMessage",
            json=payload,
            timeout=15
        )
    except Exception as error:
        print("Message error:", error)


def answer_callback(callback_id):
    try:
        requests.post(
            f"{API}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=15
        )
    except Exception as error:
        print("Callback error:", error)


# MAIN MENU
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
        "❤️ Welcome to My WP Broadcaster!\n\nChoose an option:",
        keyboard
    )


def submenu(chat_id, title, buttons):
    keyboard = {
        "inline_keyboard": buttons + [
            [{"text": "⬅️ Main Menu", "callback_data": "back_menu"}]
        ]
    }

    send_message(chat_id, title, keyboard)


# BUTTON ACTIONS
def handle_choice(chat_id, choice):

    if choice == "accounts":
        submenu(
            chat_id,
            "📱 WHATSAPP ACCOUNTS\n\nChoose your account type:",
            [
                [{"text": "WhatsApp Business App", "callback_data": "business_app"}],
                [{"text": "Normal WhatsApp", "callback_data": "personal_whatsapp"}]
            ]
        )

    elif choice == "business_app":
        send_message(
            chat_id,
            "📱 WhatsApp Business selected!\n\nOfficial Cloud API and eligible Coexistence connection setup will be added next. No account has been connected yet."
        )

    elif choice == "personal_whatsapp":
        send_message(
            chat_id,
            "💬 Normal WhatsApp selected!\n\nPersonal WhatsApp does not offer an official bulk messaging API. We can use personal WhatsApp numbers as contacts, but cannot promise official personal-account bulk sending."
        )

    elif choice == "contacts":
        submenu(
            chat_id,
            "👥 CONTACT MANAGEMENT\n\nChoose an option:",
            [
                [{"text": "➕ Add Contact", "callback_data": "add_contact"}],
                [{"text": "📋 View Contacts", "callback_data": "view_contacts"}]
            ]
        )

    elif choice == "add_contact":
        send_message(
            chat_id,
            "➕ Add Contact feature will be connected next."
        )

    elif choice == "view_contacts":
        send_message(
            chat_id,
            "📋 Contact database setup is coming next."
        )

    elif choice == "excel":
        send_message(
            chat_id,
            "📤 EXCEL UPLOAD\n\nExcel contact upload will be connected next."
        )

    elif choice == "broadcast":
        submenu(
            chat_id,
            "🚀 CREATE BROADCAST\n\nChoose an option:",
            [
                [{"text": "✍️ Create New Campaign", "callback_data": "new_campaign"}],
                [{"text": "📊 Campaign Status", "callback_data": "history"}]
            ]
        )

    elif choice == "new_campaign":
        send_message(
            chat_id,
            "🚀 Campaign creation will be connected after account and contact setup."
        )

    elif choice == "autoreply":
        submenu(
            chat_id,
            "🤖 AUTO REPLY\n\nChoose an option:",
            [
                [{"text": "➕ Add Auto Reply", "callback_data": "add_reply"}],
                [{"text": "📋 View Auto Replies", "callback_data": "view_replies"}]
            ]
        )

    elif choice == "add_reply":
        send_message(
            chat_id,
            "🤖 Auto Reply setup is coming next."
        )

    elif choice == "view_replies":
        send_message(
            chat_id,
            "📋 No auto replies configured yet."
        )

    elif choice == "credits":
        submenu(
            chat_id,
            "💳 CREDITS & PLANS\n\nChoose a plan:",
            [
                [{"text": "🥉 Basic Plan", "callback_data": "basic_plan"}],
                [{"text": "🥈 Pro Plan", "callback_data": "pro_plan"}],
                [{"text": "🥇 Business Plan", "callback_data": "business_plan"}]
            ]
        )

    elif choice in ["basic_plan", "pro_plan", "business_plan"]:
        send_message(
            chat_id,
            "💳 Selected: " + choice.replace("_", " ").title()
            + "\n\nPayment and credits will be connected later."
        )

    elif choice == "history":
        send_message(
            chat_id,
            "📜 Campaign history will be connected next."
        )

    elif choice == "help":
        send_message(
            chat_id,
            "❓ HELP & SUPPORT\n\nWelcome to My WP Broadcaster!\n\nUse the menu to explore the bot."
        )

    elif choice == "back_menu":
        main_menu(chat_id)

    else:
        send_message(chat_id, "Please choose an option from the menu.")


# HOME PAGE
@app.route("/")
def home():
    return "My WP Broadcaster Bot is Running!"


# TELEGRAM WEBHOOK
@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json(silent=True) or {}

    message = data.get("message", {})
    callback = data.get("callback_query")

    if message:
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        user = message.get("from", {})

        if chat_id and user:
            save_user(user)

        if chat_id and text:
            if text in ["/start", "/menu"]:
                main_menu(chat_id)
            else:
                send_message(
                    chat_id,
                    "Please use the menu buttons or type /menu."
                )

    if callback:
        callback_id = callback.get("id")
        user = callback.get("from", {})
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        choice = callback.get("data", "")

        if user:
            save_user(user)

        if callback_id:
            answer_callback(callback_id)

        if chat_id:
            handle_choice(chat_id, choice)

    return {"ok": True}


# REGISTER WEBHOOK
def setup_webhook():
    if not TOKEN or not BASE_URL:
        print("Telegram token or Render URL is missing")
        return

    try:
        response = requests.post(
            f"{API}/setWebhook",
            json={"url": BASE_URL.rstrip("/") + "/telegram"},
            timeout=15
        )
        print("Webhook setup:", response.text)

    except Exception as error:
        print("Webhook setup error:", error)


setup_webhook()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
