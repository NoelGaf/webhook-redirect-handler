from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow all origins by default

# Hardcoded product ID → redirect URL mapping
redirect_map = {
    "68498909ec6af1a2cb6f4fc2": "https://bits4bucks.com/home-care"
}

# Global store for latest redirect
latest_redirect = {"url": None}

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    try:
        # Extract product ID
        product_id = data.get("order", {}).get("line_items", [{}])[0].get("id")

        # Map product ID to redirect URL
        redirect_url = redirect_map.get(product_id)

        if redirect_url:
            latest_redirect["url"] = redirect_url
            print(f"[✓] Redirect set to: {redirect_url}")
            return '', 200
        else:
            print(f"[!] Unknown product ID: {product_id}")
            return '', 400
    except Exception as e:
        print(f"[!] Error processing webhook: {e}")
        return '', 400

@app.route('/get-latest-redirect')
def get_redirect():
    return jsonify(latest_redirect)

@app.route('/')
def home():
    return 'Server running'
