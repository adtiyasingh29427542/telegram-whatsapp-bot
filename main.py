
from flask import Flask, request
import requests
import os
import re
import csv
import io
import psycopg2
from openpyxl import load_workbook

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

API = f"https://api.telegram.org/bot{TOKEN}"


# DATABASE
def get_db():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL is missing")

    db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(db_url, connect_timeout=10)


def setup_database():
    conn = get_db()
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
        CREATE TABLE IF NOT EXISTS contacts (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL REFERENCES customers(telegram_id)
                ON DELETE CASCADE,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (telegram_id, phone)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_states (
            telegram_id BIGINT PRIMARY KEY REFERENCES customers(telegram_id)
                ON DELETE CASCADE,
            state TEXT NOT NULL,
            contact_name TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Database tables are ready")


def save_user(user):
    try:
        conn = get_db()
        cur = conn.cursor()

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


# USER STATE
def set_state(telegram_id, state, contact_name=None):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO user_states (telegram_id, state, contact_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (telegram_id)
        DO UPDATE SET
            state = EXCLUDED.state,
            contact_name = EXCLUDED.contact_name,
            updated_at = NOW()
    """, (telegram_id, state, contact_name))

    conn.commit()
    cur.close()
    conn.close()


def get_state(telegram_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT state, contact_name
        FROM user_states
        WHERE telegram_id = %s
    """, (telegram_id,))

    result = cur.fetchone()
    cur.close()
    conn.close()
    return result


def clear_state(telegram_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM user_states WHERE telegram_id = %s",
        (telegram_id,)
    )

    conn.commit()
    cur.close()
    conn.close()


# PHONE NUMBER CLEANING
def clean_phone(value):
    if value is None:
        return None

    phone = str(value).strip()

    # Excel kabhi number ko 9.1987E+11 bana deta hai.
    if isinstance(value, float) and value.is_integer():
        phone = str(int(value))

    phone = re.sub(r"[\s()-]", "", phone)

    if phone.startswith("00"):
        phone = "+" + phone[2:]

    if phone.startswith("+"):
        digits = phone[1:]
    else:
        digits = phone
        phone = "+" + phone

    if not digits.isdigit() or not (8 <= len(digits) <= 15):
        return None

    return phone


# ADD ONE CONTACT
def add_contact(telegram_id, name, phone):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO contacts (telegram_id, name, phone)
        VALUES (%s, %s, %s)
        ON CONFLICT (telegram_id, phone) DO NOTHING
        RETURNING id
    """, (telegram_id, name, phone))

    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return result is not None


# BULK IMPORT CONTACTS
def import_contacts(telegram_id, rows):
    imported = 0
    duplicates = 0
    invalid = 0

    conn = get_db()
    cur = conn.cursor()

    try:
        for name, raw_phone in rows:
            name = str(name).strip() if name is not None else ""
            phone = clean_phone(raw_phone)

            if not name or len(name) > 80 or not phone:
                invalid += 1
                continue

            cur.execute("""
                INSERT INTO contacts (telegram_id, name, phone)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id, phone) DO NOTHING
                RETURNING id
            """, (telegram_id, name, phone))

            if cur.fetchone():
                imported += 1
            else:
                duplicates += 1

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()

    return imported, duplicates, invalid


# READ EXCEL / CSV
def read_contact_file(filename, file_bytes):
    extension = filename.lower().rsplit(".", 1)[-1]

    rows = []

    if extension == "xlsx":
        workbook = load_workbook(
            io.BytesIO(file_bytes),
            read_only=True,
            data_only=True
        )

        sheet = workbook.active

        for row in sheet.iter_rows(values_only=True):
            rows.append(row)

        workbook.close()

    elif extension == "csv":
        text = file_bytes.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

    else:
        raise ValueError("Only XLSX and CSV files are supported.")

    if not rows or len(rows) < 2:
        raise ValueError("File mein contacts nahi mile.")

    headers = [
        str(value).strip().lower() if value is not None else ""
        for value in rows[0]
    ]

    name_aliases = ["name", "contact name", "full name"]
    phone_aliases = ["phone", "number", "mobile", "whatsapp", "phone number"]

    name_index = next(
        (i for i, h in enumerate(headers) if h in name_aliases),
        None
    )

    phone_index = next(
        (i for i, h in enumerate(headers) if h in phone_aliases),
        None
    )

    if name_index is None or phone_index is None:
        raise ValueError(
            "File mein Name aur Phone columns zaroor hone chahiye."
        )

    for row in rows[1:]:
        if len(row) <= max(name_index, phone_index):
            continue

        rows_data = (row[name_index], row[phone_index])

        if any(value is not None for value in rows_data):
            # Limit one upload to 5000 data rows.
            if len(rows) > 5001:
                raise ValueError("Ek file mein maximum 5000 rows allowed hain.")

            yield rows_data


# TELEGRAM FILE DOWNLOAD
def download_telegram_file(file_id):
    if not TOKEN:
        raise Exception("Bot token missing.")

    response = requests.get(
        f"{API}/getFile",
        params={"file_id": file_id},
        timeout=20
    )
    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise Exception("Telegram file details nahi mil paaye.")

    file_path = result["result"]["file_path"]

    download_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

    file_response = requests.get(download_url, timeout=30)
    file_response.raise_for_status()

    if len(file_response.content) > 10 * 1024 * 1024:
        raise ValueError("File 10 MB se chhoti honi chahiye.")

    return file_response.content


# HANDLE EXCEL UPLOAD
def handle_document(chat_id, telegram_id, document):
    filename = document.get("file_name", "")
    extension = filename.lower().rsplit(".", 1)[-1]

    if extension not in ["xlsx", "csv"]:
        send_message(
            chat_id,
            "❌ Sirf .xlsx aur .csv files supported hain."
        )
        return

    file_size = document.get("file_size", 0)

    if file_size > 10 * 1024 * 1024:
        send_message(chat_id, "❌ File 10 MB se chhoti honi chahiye.")
        return

    send_message(chat_id, "⏳ File process ho rahi hai. Please wait...")

    try:
        file_bytes = download_telegram_file(document["file_id"])
        rows = list(read_contact_file(filename, file_bytes))

        if len(rows) > 5000:
            raise ValueError("Maximum 5000 contacts per file allowed hain.")

        if not rows:
            raise ValueError("File mein koi contact row nahi mili.")

        imported, duplicates, invalid = import_contacts(
            telegram_id,
            rows
        )

        send_message(
            chat_id,
            "✅ EXCEL IMPORT COMPLETE!\n\n"
            f"📥 Imported: {imported}\n"
            f"♻️ Duplicate skipped: {duplicates}\n"
            f"⚠️ Invalid skipped: {invalid}\n\n"
            "Apne contacts dekhne ke liye View Contacts dabao."
        )

    except Exception as error:
        print("Excel upload error:", error)
        send_message(
            chat_id,
            "❌ File process nahi ho paayi.\n\n"
            f"Reason: {str(error)[:300]}\n\n"
            "Please template ke according file dobara bhejo."
        )


# GET CONTACTS
def get_contacts(telegram_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT name, phone
        FROM contacts
        WHERE telegram_id = %s
        ORDER BY id DESC
        LIMIT 20
    """, (telegram_id,))

    contacts = cur.fetchall()
    cur.close()
    conn.close()

    return contacts


# SEND TELEGRAM MESSAGE
def send_message(chat_id, text, keyboard=None):
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN is missing")
        return

    payload = {"chat_id": chat_id, "text": text}

    if keyboard:
        payload["reply_markup"] = keyboard

    try:
        response = requests.post(
            f"{API}/sendMessage",
            json=payload,
            timeout=15
        )
        print("Telegram sendMessage:", response.status_code)
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


def contact_menu(chat_id):
    submenu(
        chat_id,
        "👥 CONTACT MANAGEMENT\n\nChoose an option:",
        [
            [{"text": "➕ Add Contact", "callback_data": "add_contact"}],
            [{"text": "📋 View Contacts", "callback_data": "view_contacts"}]
        ]
    )


def show_contacts(chat_id, telegram_id):
    try:
        contacts = get_contacts(telegram_id)

        if not contacts:
            send_message(
                chat_id,
                "📋 Abhi koi contact saved nahi hai."
            )
            return

        lines = ["📋 YOUR SAVED CONTACTS\n"]

        for number, contact in enumerate(contacts, start=1):
            name, phone = contact
            lines.append(f"{number}. {name}\n📱 {phone}")

        lines.append("\nYahan 20 recent contacts dikhaye ja rahe hain.")
        send_message(chat_id, "\n\n".join(lines))

    except Exception as error:
        print("View contacts error:", error)
        send_message(chat_id, "Contacts load nahi ho paaye.")


# BUTTON ACTIONS
def handle_choice(chat_id, telegram_id, choice):

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
            "📱 WhatsApp Business selected!\n\n"
            "Official Cloud API setup will be added next."
        )

    elif choice == "personal_whatsapp":
        send_message(
            chat_id,
            "💬 Personal WhatsApp does not offer an official bulk messaging API. "
            "Contacts can be stored, but personal-account bulk sending is not supported."
        )

    elif choice == "contacts":
        contact_menu(chat_id)

    elif choice == "add_contact":
        set_state(telegram_id, "waiting_name")
        send_message(
            chat_id,
            "➕ ADD NEW CONTACT\n\n"
            "Contact ka naam bhejo.\n"
            "Example: Rahul Sharma\n\n"
            "Cancel karne ke liye /cancel bhejo."
        )

    elif choice == "view_contacts":
        show_contacts(chat_id, telegram_id)

    elif choice == "excel":
        send_message(
            chat_id,
            "📤 EXCEL CONTACT UPLOAD\n\n"
            "Apni .xlsx ya .csv file yahan bhejo.\n\n"
            "File mein ye 2 columns hone chahiye:\n"
            "Name | Phone\n\n"
            "Example:\n"
            "Name: Rahul Sharma\n"
            "Phone: +919876543210\n\n"
            "Maximum 5000 rows aur 10 MB file size."
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
            "🚀 Campaign creation will be connected after account setup."
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
        send_message(chat_id, "🤖 Auto Reply setup is coming next.")

    elif choice == "view_replies":
        send_message(chat_id, "📋 No auto replies configured yet.")

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
        send_message(chat_id, "📜 Campaign history will be connected next.")

    elif choice == "help":
        send_message(
            chat_id,
            "❓ HELP & SUPPORT\n\n"
            "Use the menu to explore the bot.\n"
            "Type /cancel to stop contact entry."
        )

    elif choice == "back_menu":
        clear_state(telegram_id)
        main_menu(chat_id)

    else:
        send_message(chat_id, "Please choose an option from the menu.")


# MANUAL CONTACT ENTRY
def handle_contact_message(chat_id, telegram_id, message_text):
    state_data = get_state(telegram_id)

    if not state_data:
        return False

    state, contact_name = state_data

    if state == "waiting_name":
        name = message_text.strip()

        if len(name) < 2 or len(name) > 80:
            send_message(chat_id, "Naam 2 se 80 characters ke beech hona chahiye.")
            return True

        set_state(telegram_id, "waiting_phone", name)

        send_message(
            chat_id,
            f"Name: {name}\n\n"
            "Ab WhatsApp number country code ke saath bhejo.\n"
            "Example: +919876543210"
        )
        return True

    if state == "waiting_phone":
        phone = clean_phone(message_text)

        if not phone:
            send_message(
                chat_id,
                "❌ Number sahi nahi hai. Example: +919876543210"
            )
            return True

        try:
            saved = add_contact(telegram_id, contact_name, phone)
            clear_state(telegram_id)

            if saved:
                send_message(
                    chat_id,
                    "✅ CONTACT SAVED SUCCESSFULLY!\n\n"
                    f"👤 Name: {contact_name}\n"
                    f"📱 Number: {phone}"
                )
            else:
                send_message(chat_id, "⚠️ Ye number pehle se saved hai.")

        except Exception as error:
            print("Add contact error:", error)
            clear_state(telegram_id)
            send_message(chat_id, "Contact save nahi ho paaya.")

        return True

    return False


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
        user = message.get("from", {})
        telegram_id = user.get("id")
        message_text = message.get("text", "")

        if telegram_id:
            save_user(user)

        if chat_id and message.get("document") and telegram_id:
            handle_document(
                chat_id,
                telegram_id,
                message["document"]
            )

        elif chat_id and message_text:
            if message_text in ["/start", "/menu"]:
                if telegram_id:
                    clear_state(telegram_id)
                main_menu(chat_id)

            elif message_text == "/cancel":
                if telegram_id:
                    clear_state(telegram_id)
                send_message(chat_id, "❌ Contact entry cancelled.")

            elif telegram_id and handle_contact_message(
                chat_id, telegram_id, message_text
            ):
                pass

            else:
                send_message(
                    chat_id,
                    "Please use the menu buttons or type /menu."
                )

    if callback:
        callback_id = callback.get("id")
        user = callback.get("from", {})
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        telegram_id = user.get("id")
        choice = callback.get("data", "")

        if telegram_id:
            save_user(user)

        if callback_id:
            answer_callback(callback_id)

        if chat_id and telegram_id:
            handle_choice(chat_id, telegram_id, choice)

    return {"ok": True}


# WEBHOOK SETUP
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


# STARTUP
try:
    setup_database()
except Exception as error:
    print("Database setup error:", error)

setup_webhook()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
