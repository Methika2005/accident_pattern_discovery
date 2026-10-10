from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "project": "accident_pattern_discovery"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
