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
import hashlib
import json

app = Flask(__name__)
CORS(app)

# ====== 🔁 Redirect Setup ======
redirect_map = {
    "685aa39f0b7a70008d57becb": "https://bits4bucks.com/dryer-sheets",
    "68540ce011cea80f6c114d17": "https://bits4bucks.com/care-bears-bag",
    "685aa42aaae705008b92c6af": "https://bits4bucks.com/baby-cover",
    "685aa474aae705f2a792c6fc": "https://bits4bucks.com/shower-caddy",
    "685aa4ab661af0792e6dcb4c": "https://bits4bucks.com/zoom-ball",
    "68541362bdcc26a5e383be10": "https://bits4bucks.com/nivea-orchid",
    "68541004449a2fa5a42b06ae": "https://bits4bucks.com/deep-waver"
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
    "685aa39f0b7a70008d57becb": "CZY-2585-447",
    "68514db465abfb3e79c59130": "CZY-5942-447",
    "685aa42aaae705008b92c6af": "CZY-3502-447",
    "6849870ffcd4bca78d49f61e": "CZY-5313-447",
    "685aa474aae705f2a792c6fc": "CZY-5284-447",
    "685407f2bdcc2683ad83b95c": "CZY-5988-447",
    "685aa4ab661af0792e6dcb4c": "CZY-3254-447",
    "68540b77449a2f5f252b0500": "CZY-3765-447",
    "68540ce011cea80f6c114d17": "CZY-7214-447",
    "68540dd9449a2f99ff2b05d2": "CZY-1380-447",
    "68541004449a2fa5a42b06ae": "CZY-7106-447",
    "6854112dbdcc26775483bd6b": "CZY-9847-447",
    "68541362bdcc26a5e383be10": "CZY-7703-447",
    "68541490449a2f564f2b083e": "CZY-8023-447"
}

# Product ID → Quantity Multiplier
quantity_multiplier_map = {
    "685aa39f0b7a70008d57becb": 2,  # Example: socks (bundle of 2 units per 1 ordered)
    "68514db465abfb3e79c59130": 1,  # Normal item (send exactly what was ordered)
    "685aa42aaae705008b92c6af": 2,
    "6849870ffcd4bca78d49f61e": 1,
    "685aa474aae705f2a792c6fc": 2,
    "685407f2bdcc2683ad83b95c": 1,
    "685aa4ab661af0792e6dcb4c": 1,
    "68540b77449a2f5f252b0500": 1,
    "68540ce011cea80f6c114d17": 1,
    "68540dd9449a2f99ff2b05d2": 1,
    "68541004449a2fa5a42b06ae": 3,
    "6854112dbdcc26775483bd6b": 1,
    "68541362bdcc26a5e383be10": 2,
    "68541490449a2f564f2b083e": 1
    # Add more as needed
}

# Background email timer
last_post_time = None
email_timer_thread = None
lock = threading.Lock()

def get_or_create_order_id(email, phone):
    """
    Consistently generate a pseudo-unique order ID per customer
    by hashing email + phone.
    """
    key = f"{email.lower()}-{phone}"
    return "INV-" + hashlib.md5(key.encode()).hexdigest()[:8].upper()


def write_order_to_csv(data):
    try:
        order = data.get("order")
        if not order:
            print("[!] Error processing webhook: 'order' key missing")
            return

        # Fallback if customer block is missing from order
        customer = order.get("customer") or {
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "full_name": data.get("full_name", ""),
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "full_address": data.get("full_address", ""),
            "city": data.get("city", ""),
            "state": data.get("state", ""),
            "postal_code": data.get("postal_code", ""),
            "country": data.get("country", "")
        }

        line_items = order.get("line_items", [])
        if not line_items:
            print("[!] No line items in order.")
            return

        order_id = get_or_create_order_id(customer["email"], customer["phone"])
        delivery_date = datetime.utcnow().strftime("%d/%m/%Y")
        company_name = (
            customer.get("full_name") or
            customer.get("name") or
            f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
        )

        # Ensure the file has headers if new
        file_exists = os.path.exists(CSV_FILE)
        with open(CSV_FILE, "a", newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "delivery_date", "customer_reference", "company_name",
                    "street", "suburb", "postcode", "state",
                    "value", "code", "description", "qty", "Instructions"
                ])

            for item in line_items:
                meta = item.get("meta", {})
                product_id = meta.get("product_id")
                if not product_id:
                    print("[!] Unknown product ID: None")
                    continue

                print("[DEBUG] product_code_map keys:", list(product_code_map.keys()))
                print("[DEBUG] Looking up product_id:", product_id)

                product_code = product_code_map.get(product_id, "UNKNOWN")
                if product_code == "UNKNOWN":
                    print(f"[!] Unknown product ID: {product_id}")

                row = [
                    delivery_date,                      # delivery_date
                    order_id,                           # customer_reference
                    company_name,                       # company_name
                    customer.get("full_address", ""),   # street
                    customer.get("city", ""),           # suburb
                    customer.get("postal_code", ""),    # postcode
                    customer.get("state", ""),          # state
                    f'${item["line_price"]:.2f}',       # value
                    product_code,                       # code
                    item.get("title", ""),              # description
                    item.get("quantity", 1) * quantity_multiplier_map.get(product_id, 1), # qty
                    "Deliver ASAP"                      # Instructions
                ]
                writer.writerow(row)

    except Exception as e:
        print(f"[!] Exception while writing order to CSV: {e}")
        print(f"[!] Payload: {json.dumps(data, indent=2)}")


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
