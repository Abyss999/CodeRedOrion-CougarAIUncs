# ml/

Experiments for food detection, spoilage classification and receipt OCR.
**Training and heavy inference run off-box** (Colab or a teammate's GPU), never on the VPS.

| Dir | Owner | What |
|---|---|---|
| `yolo/` | ML builder | Dataset prep, training notebook, exported weights (weights are gitignored; link them in `docs/ML.md`) |
| `ocr/` | ML builder | Receipt pipeline: `zai-org/GLM-OCR` text → Gemini structuring → line items |
| `serve/` | ML builder | Small inference service the backend calls via `ML_SERVICE_URL` (contract in `docs/API.md`, `POST /items/from-photo`) |
| `eval/` | ML QA only | Held-out sets, eval scripts, results — thresholds in `docs/QA.md` |

Confirm the exact YOLO version (Ultralytics release) before training and record it in `docs/DECISIONS.md`.
