# Provenance Guard Planning Spec

This document details the system design, classification logic, user experience, and implementation plan for the **Provenance Guard** backend system.

---

## 1. System Architecture

### Architecture Diagram
```mermaid
graph TD
    %% Submission Flow
    subgraph Submission Flow (POST /submit)
        A[POST /submit] -->|1. Raw Text & Creator ID| B[Multi-Signal Detection Pipeline]
        B -->|2a. Raw Text| C[Signal 1: LLM Groq Classifier]
        B -->|2b. Raw Text| D[Signal 2: Stylometrics Analyzer]
        C -->|3a. LLM Score 0-1| E[Confidence Aggregator]
        D -->|3b. Heuristic Score 0-1| E
        E -->|4. Ensemble Confidence Score 0-1| F[Transparency Label Generator]
        F -->|5. Label & Verdict Text| G[Structured Audit Log]
        G -->|6. JSON Response: Verdict, Label, Content ID| H[Client Response]
    end

    %% Appeal Flow
    subgraph Appeal Flow (POST /appeal)
        I[POST /appeal] -->|1. Content ID & Reasoning| J[Appeal Handler]
        J -->|2. Query & Check Existence| K[(Log Storage / Database)]
        J -->|3. Update Status to 'under review' & Log Reasoning| K
        J -->|4. JSON Response: Status Confirmation| L[Client Response]
    end
```

### Architecture Narrative
1. **Submission Flow**: The client calls `POST /submit` with content and user metadata. The `Multi-Signal Detection Pipeline` runs semantic analysis via Groq and structural/statistical analysis via Python stylometrics concurrently. The `Confidence Aggregator` synthesizes these outputs using a weighted average. The `Transparency Label Generator` maps this ensemble confidence score to a pre-defined UX label. Finally, the system logs the full transaction (including individual signal scores) in the structured audit log and returns the JSON payload to the client.
2. **Appeal Flow**: If a classification is contested, `POST /appeal` is hit. The `Appeal Handler` retrieves the record by `content_id`, updates its status to `"under review"`, appends the reason to the audit log, and outputs a confirmation JSON response.

### API Surface Contract

#### 1. Content Submission Endpoint
* **Path**: `/submit`
* **Method**: `POST`
* **Content-Type**: `application/json`
* **Request Body**:
  ```json
  {
    "text": "The sun dipped below the horizon, painting the sky...",
    "creator_id": "test-user-1"
  }
  ```
* **Response Body (200 OK)**:
  ```json
  {
    "content_id": "3f7a2b1e-7b70-4d56-b072-46823c34ff0b",
    "creator_id": "test-user-1",
    "attribution": "likely_human",
    "confidence": 0.18,
    "label": "Verified Human: This content exhibits natural stylistic variations...",
    "status": "classified"
  }
  ```
* **Error Response (400 Bad Request)**:
  ```json
  {
    "error": "Missing required fields: 'text' and 'creator_id' must be provided."
  }
  ```

#### 2. Appeals Endpoint
* **Path**: `/appeal`
* **Method**: `POST`
* **Content-Type**: `application/json`
* **Request Body**:
  ```json
  {
    "content_id": "3f7a2b1e-7b70-4d56-b072-46823c34ff0b",
    "creator_id_or_reasoning": "I wrote this myself from personal experience."
  }
  ```
  *(Note: The PDF spec requires `content_id` and `creator_reasoning`)*
  ```json
  {
    "content_id": "3f7a2b1e-7b70-4d56-b072-46823c34ff0b",
    "creator_reasoning": "I wrote this myself from personal experience."
  }
  ```
* **Response Body (200 OK)**:
  ```json
  {
    "message": "Appeal successfully received and logged.",
    "content_id": "3f7a2b1e-7b70-4d56-b072-46823c34ff0b",
    "status": "under_review"
  }
  ```
* **Error Response (404 Not Found)**:
  ```json
  {
    "error": "Content submission with ID 3f7a2b1e-7b70-4d56-b072-46823c34ff0b not found."
  }
  ```

#### 3. Audit Log Retrieval Endpoint (for verification/grading)
* **Path**: `/log`
* **Method**: `GET`
* **Response Body (200 OK)**:
  ```json
  {
    "entries": [
      {
        "content_id": "3f7a2b1e-7b70-4d56-b072-46823c34ff0b",
        "creator_id": "test-user-1",
        "timestamp": "2026-06-28T14:32:10.123Z",
        "attribution": "likely_human",
        "confidence": 0.18,
        "llm_score": 0.22,
        "stylometric_score": 0.10,
        "status": "classified",
        "appeal_reasoning": null
      }
    ]
  }
  ```

---

## 2. False Positive Scenario Trace

To ensure production safety and user trust, we trace a scenario where a human writer's work is incorrectly flagged as AI-generated:

1. **Submission**: A human writer submits a formal academic-style essay or a highly formulaic blog post (e.g., standard tutorial) via `POST /submit`.
2. **Analysis & Pipeline Output**:
   - The Groq LLM model registers highly predictable phrasing and gives an LLM score of `0.78` (likely AI).
   - The stylometrics heuristic registers uniform sentence length and simple, common vocabulary, yielding a score of `0.65` (moderately likely AI).
   - The ensemble calculates $C = 0.70 \times 0.78 + 0.30 \times 0.65 = 0.741$.
3. **Verdict & Label**: Since $0.741 > 0.70$, the system issues the label `"AI-Generated"`.
4. **Creator Reaction & Appeal**: The writer sees the incorrect label, which hurts their professional reputation. They click "Appeal" (contesting the decision).
5. **Appeals Request**: The client issues:
   ```json
   {
     "content_id": "3f7a2b1e-7b70-4d56-b072-46823c34ff0b",
     "creator_reasoning": "I spent three days drafting this and used standard technical definitions which explain the formulaic structure."
   }
   ```
6. **System State Update**:
   - The status is updated to `"under review"`.
   - The creator reasoning is recorded.
   - Any external platform integrations (or a human moderation dashboard) are notified of the pending appeal.
   - The display label for the text is immediately replaced with the `"Unverified / Under Review"` label to protect the creator from penalty while manual inspection is pending.

---


## 3. Detection Signals

* **Signal 1: LLM-Based Classification (Groq)**
  * **What it measures**: Semantic coherence, stylistic patterns, clichés, and overall flow characteristic of generative LLMs.
  * **Output format**: A score between `0.0` (clearly human-written) and `1.0` (clearly AI-generated).
  * **Rationale**: Groq (using `llama-3.3-70b-versatile`) offers high semantic understanding to catch holistically synthesized text.
  * **Blind spots**: May misclassify highly structured, formal human academic writing, or extremely simple, short texts where semantic patterns are sparse.

* **Signal 2: Stylometric Heuristics**
  * **What it measures**: Structural properties of the text (e.g., sentence length variance, type-token ratio for vocabulary diversity, punctuation density).
  * **Output format**: A score between `0.0` (high variability, typical of humans) and `1.0` (highly uniform/uniform complexity, typical of AI).
  * **Rationale**: Pure Python implementation checking sentence complexity and structural variety. Genuinely independent from the semantic analysis of Signal 1.
  * **Blind spots**: May misclassify human poetry or listing-heavy documents that have unnatural structures, or AI text that has been deliberately randomized/edited for structural noise.

* **Signal Combination Approach**:
  * The combined confidence score $C \in [0, 1]$ will be computed using a weighted average:
    $$C = w_1 \cdot S_{\text{LLM}} + w_2 \cdot S_{\text{sty}}$$
    where $w_1 = 0.7$ and $w_2 = 0.3$, prioritizing the semantic accuracy of the LLM while using stylometrics as a correcting factor.

---

## 4. Uncertainty Representation

* **Mapping Raw Outputs to Calibrated Score**:
  * A combined score $C$ near `0.5` represents high uncertainty.
  * A combined score $C$ near `0.0` represents high confidence that the text is human-written.
  * A combined score $C$ near `1.0` represents high confidence that the text is AI-generated.
* **Calibrated Verdict Thresholds**:
  * **Likely Human**: $0.0 \le C < 0.40$
  * **Uncertain**: $0.40 \le C \le 0.70$
  * **Likely AI**: $0.70 < C \le 1.0$
* **Asymmetry/Bias Handling**: Because false positives (labeling human work as AI) are extremely damaging to creators, we require a higher threshold ($C > 0.70$) to classify something as "Likely AI". If a score is borderline, it defaults to "Uncertain".

---

## 5. Transparency Label Design

Verbatim text for the three label variants:

| Verdict | Range | Verbatim Label Text |
| :--- | :--- | :--- |
| **Likely Human** | $C < 0.40$ | `"Verified Human: This content exhibits natural stylistic variations and structural characteristics consistent with original human writing."` |
| **Uncertain** | $0.40 \le C \le 0.70$ | `"Unverified: The stylistic evaluation of this content is inconclusive. It may contain a blend of human and assisted writing."` |
| **Likely AI** | $C > 0.70$ | `"AI-Generated: This content matches patterns and structural markers highly characteristic of text generated by artificial intelligence."` |

---

## 6. Appeals Workflow

* **Who can submit an appeal?** Any creator who submitted text and received a classification can appeal using the unique `content_id` returned from their submission.
* **Information provided**:
  * `content_id` (string, UUID)
  * `creator_reasoning` (string, explanation of why they are appealing)
* **System actions upon receiving appeal**:
  1. Look up the record by `content_id` in the SQLite database or log storage.
  2. Verify if the record exists and if it is not already under review or resolved.
  3. Update the record's status from `"classified"` to `"under review"`.
  4. Log the appeal event including the creator's reasoning to the structured audit log.
* **Human Reviewer Interface Queue View**:
  * A reviewer would see a list of active appeals showing:
    * Timestamp of original submission and appeal.
    * Submission details (Original text snippet, creator ID, content ID).
    * Original scores (Combined confidence, LLM score, Stylometric score).
    * Creator's reasoning for appeal.
    * Status (`under review`).

---

## 7. Anticipated Edge Cases

1. **Short, Formulaic Forms (e.g., Recipe Steps or Technical Logs)**:
   * *Problem*: Heuristics and LLMs may both identify highly structured, simple, repetitious language as AI-generated because it lacks stylistic flair.
   * *Mitigation*: Fall back to "Uncertain" for texts under a minimum word count (e.g., 50 words).
2. **Non-English / Multilingual Text**:
   * *Problem*: Stylometric heuristics tuned for English sentence structures will produce anomalous values, and Groq's classification might be less calibrated.
   * *Mitigation*: Detect language or restrict classification to English-only, flagging non-English text as "Uncertain".

---

## 8. AI Tool Plan

### M3: Submission Endpoint & First Signal
* **Spec Section provided**: Architecture Diagram/Narrative + Detection Signals (Groq signal details).
* **Code request**: Create a Flask skeleton with `POST /submit` (accepting `text` and `creator_id`) and a helper function `detect_signal_llm(text)` that queries Groq API and returns a float score `0.0 - 1.0`. Set up a simple structured JSON audit log writer.
* **Verification**: Run `curl` to submit a test paragraph, check that the output has `content_id`, `attribution`, `confidence`, and `label` (using placeholder values for confidence and label for now), and verify the JSON log records the entry.

### M4: Second Signal & Confidence Scoring
* **Spec Section provided**: Detection Signals (Stylometrics) + Uncertainty Representation + Combined Logic.
* **Code request**: Write `detect_signal_stylometrics(text)` in pure Python (measuring sentence length variance and type-token ratio) and the integration function `calculate_confidence(score_llm, score_sty)`.
* **Verification**: Submit the 4 recommended test inputs (AI-generated, Human-written, formal human writing, lightly edited AI output) and verify that confidence scores vary meaningfully. Ensure the audit log now writes both individual scores.

### M5: Production Layer
* **Spec Section provided**: Transparency Label Design + Appeals Workflow + Rate Limiting.
* **Code request**: Build transparency label selection based on thresholds, write the `POST /appeal` endpoint updating record status, integrate `Flask-Limiter` with configured rate limits, and finalize the structured SQLite/JSON audit log backend.
* **Verification**: Verify rate limiting triggers 429 after 10 requests, and test that calling `/appeal` updates status to `"under review"` in `/log`.

