from flask import Flask, request, jsonify
app = Flask(__name__)

latest_redirect = {"url": None}

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    latest_redirect['url'] = data.get('redirect_url')
    return '', 200

@app.route('/get-latest-redirect')
def get_redirect():
    return jsonify(latest_redirect)

@app.route('/')
def home():
    return 'Server running'
