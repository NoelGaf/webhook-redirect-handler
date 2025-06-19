import csv
import os
import threading
import time
import uuid
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
from email.message import EmailMessage

app = Flask(__name__)
CORS(app)

# ====== 🔁 Redirect Setup ======
redirect_map = {
    "68498909ec6af1a2cb6f4fc2": "https://bits4bucks.com/home-care"
}
latest_redirect = {"url": None}

# ====== 📦 Fulfillment Setup ======
CSV_FILE = "/tmp/daily_orders.csv"
EMAIL_TO = os.environ.get("EMAIL_TO")
EMAIL_FROM = os.environ.get("EMAIL_FROM")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Memory store for customer → order_id mapping
customer_order_ids = {}

# Product ID → Fulfillment Code
product_code_map = {
    "68498909ec6af1a2cb6f4fc2": "CZY-2585-447",
    "68514db465abfb3e79c59130": "CZY-5942-447"
}

# Background email timer
last_post_time = None
email_timer_thread = None
lock = threading.Lock()

def get_or_create_order_id(email, phone):
    key = f"{email.lower()}|{phone}"
    if key not in customer_order_ids:
        customer_order_ids[key] = str(uuid.uuid4())[:8].upper()
    return customer_order_ids[key]

def write_order_to_csv(data):
    customer = data["customer"]
    line_items = data["order"]["line_items"]

    order_id = get_or_create_order_id(customer["email"], customer["phone"])

    with open(CSV_FILE, "a", newline='') as f:
        writer = csv.writer(f)
        for item in line_items:
            product_id = item["meta"]["product_id"]
            product_code = product_code_map.get(product_id, "UNKNOWN")
            row = [
                order_id,
                datetime.utcnow().strftime("%Y-%m-%d"),
                item["title"],
                item["quantity"],
                item["price"],
                customer["first_name"],
                customer["last_name"],
                customer["email"],
                customer["phone"],
                customer["full_address"],
                customer["city"],
                customer["state"],
                customer["postal_code"],
                customer["country"],
                product_code
            ]
            writer.writerow(row)

def email_csv_file():
    if not os.path.exists(CSV_FILE):
        print("[!] CSV not found, skipping email.")
        return

    msg = EmailMessage()
    msg["Subject"] = "Daily Orders Export"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.set_content("Attached is the daily CSV export of orders.")

    with open(CSV_FILE, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype="csv", filename="daily_orders.csv")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
        print("[✓] Email sent successfully.")
        os.remove(CSV_FILE)
    except Exception as e:
        print(f"[!] Failed to send email: {e}")

def start_email_timer():
    global email_timer_thread
    def delayed_email():
        time.sleep(60)  # temporary 1-minute delay for testing - change afterwards
        with lock:
            email_csv_file()
    if email_timer_thread and email_timer_thread.is_alive():
        return  # already counting down
    email_timer_thread = threading.Thread(target=delayed_email)
    email_timer_thread.start()

# ====== 🔗 Webhook Route ======
@app.route('/webhook', methods=['POST'])
def webhook():
    global last_post_time
    data = request.json

    try:
        # 🔁 Redirection logic
        product_id = data.get("order", {}).get("line_items", [{}])[0].get("meta", {}).get("product_id")
        redirect_url = redirect_map.get(product_id)
        if redirect_url:
            latest_redirect["url"] = redirect_url
            print(f"[✓] Redirect set to: {redirect_url}")
        else:
            print(f"[!] Unknown product ID: {product_id}")

        # 📦 Fulfillment logic
        write_order_to_csv(data)
        with lock:
            last_post_time = time.time()
            start_email_timer()

        return '', 200

    except Exception as e:
        print(f"[!] Error processing webhook: {e}")
        return '', 400

# ====== 🌐 Other Routes ======
@app.route('/get-latest-redirect')
def get_redirect():
    return jsonify(latest_redirect)

@app.route('/')
def home():
    return 'Server running'
