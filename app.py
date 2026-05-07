import os
import base64
import json
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import anthropic

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20 MB

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

CATEGORIES = [
    "Dining & Restaurants",
    "Groceries",
    "Transportation",
    "Travel",
    "Entertainment",
    "Shopping",
    "Healthcare",
    "Subscriptions",
    "Utilities & Bills",
    "Home & Services",
    "Personal Care",
    "Other",
]

EXTRACTION_PROMPT = f"""You are a financial data extraction assistant. Analyze this credit card statement and extract every transaction/expense line item.

For each transaction, return a JSON array of objects with these exact fields:
- date: transaction date as a string (keep original format)
- description: merchant/payee name (clean and readable)
- amount: numeric value (positive number, no currency symbols)
- category: one of {json.dumps(CATEGORIES)}

Rules:
- Only include actual purchases/charges (not payments, credits, or refunds unless they are negative amounts)
- For credits/refunds, use a negative amount
- Categorize intelligently based on merchant name and context
- If you cannot determine a field, use null
- Return ONLY the JSON array, no other text

Example output:
[
  {{"date": "01/15/2025", "description": "WHOLE FOODS MARKET", "amount": 87.43, "category": "Groceries"}},
  {{"date": "01/16/2025", "description": "UBER EATS", "amount": 34.21, "category": "Dining & Restaurants"}}
]"""


def encode_file(file_bytes, media_type):
    return base64.standard_b64encode(file_bytes).decode("utf-8")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = file.filename.lower()
    file_bytes = file.read()

    if filename.endswith(".pdf"):
        media_type = "application/pdf"
    elif filename.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif filename.endswith(".png"):
        media_type = "image/png"
    else:
        return jsonify({"error": "Unsupported file type. Please upload a PDF, JPG, or PNG."}), 400

    encoded = encode_file(file_bytes, media_type)

    if media_type == "application/pdf":
        content_block = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": encoded,
            },
        }
    else:
        content_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": encoded,
            },
        }

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        content_block,
                        {"type": "text", "text": EXTRACTION_PROMPT},
                    ],
                }
            ],
        )

        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        transactions = json.loads(raw)
        return jsonify({"transactions": transactions})

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Failed to parse extracted data: {str(e)}", "raw": raw}), 500
    except anthropic.APIError as e:
        return jsonify({"error": f"API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=8080)
