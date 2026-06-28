import uuid
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from database import init_db, log_submission, get_all_logs
from detector import detect_signal_llm

app = Flask(__name__)

# Initialize database tables
init_db()

# Setup rate limiting with in-memory storage
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)

@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json(silent=True)
    if not data or "text" not in data or "creator_id" not in data:
        return jsonify({"error": "Missing required fields: 'text' and 'creator_id' must be provided."}), 400
    
    text = data["text"]
    creator_id = data["creator_id"]
    
    if not text.strip() or not creator_id.strip():
        return jsonify({"error": "Fields 'text' and 'creator_id' cannot be empty."}), 400

    # 1. Run LLM signal analysis
    llm_result = detect_signal_llm(text)
    llm_score = llm_result["score"]
    
    # 2. Determine attribution based on first signal for Milestone 3
    # If llm_score is >= 0.5, we say likely_ai, else likely_human
    attribution = "likely_ai" if llm_score >= 0.5 else "likely_human"
    
    # 3. Generate placeholders for confidence and label as per M3 specs
    placeholder_confidence = 0.50
    placeholder_label = "Unverified: Stylometric evaluation pending."
    
    # 4. Generate unique content_id
    content_id = str(uuid.uuid4())
    
    # 5. Log the submission in the structured database
    log_submission(
        content_id=content_id,
        creator_id=creator_id,
        text=text,
        attribution=attribution,
        confidence=placeholder_confidence,
        llm_score=llm_score,
        stylometric_score=None
    )
    
    # 6. Return response
    return jsonify({
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "confidence": placeholder_confidence,
        "label": placeholder_label,
        "status": "classified"
    })

@app.route("/log", methods=["GET"])
def get_logs():
    entries = get_all_logs()
    return jsonify({"entries": entries})

if __name__ == "__main__":
    app.run(port=5000, debug=True)
