# ml/

Food detection, spoilage classification and receipt OCR. **Training and heavy inference run off-box**
(Colab / GPU). Full write-up: [`docs/ML.md`](../docs/ML.md).

| Dir | Owner | What |
|---|---|---|
| `yolo/` | ML builder | `taxonomy.py` (class -> backend category), `prepare_dataset.py`, `train.py`, `train_colab.ipynb`, `infer.py`, `export_predictions.py`, `requirements.txt` (GPU-side, `ultralytics==8.4.175`) |
| `ocr/` | ML builder | `receipt_pipeline.py`: GLM-OCR backend + deterministic `parse_receipt_text` + optional Gemini hook |
| `serve/` | ML builder | Flask inference service (`/detect`, `/ocr`, `/health`) with fake + real backends; `Dockerfile`, GPU `requirements.txt` |
| `eval/` | ML QA only | Held-out sets, eval scripts, results |

New datasets, the receipt inbox and lighting augmentation live in the root `pipeline/` (see `docs/PIPELINE.md`); it imports `yolo/` and `ocr/` rather than copying them.

Light tests (run from `ml/`, project venv, no torch/ultralytics needed):
`../.venv/bin/python -m pytest serve/tests ocr/tests yolo/tests -q`

Dev server with fake backends: `PORT=8000 python -m serve.app` (from `ml/`).
