import logging
import os

from .app import create_app
from .backends import ocr_from_env

log = logging.getLogger("fwr.serve")

_ocr = ocr_from_env()
app = create_app(ocr=_ocr)

# Optional: load the OCR model at start instead of on the first /ocr call. Off unless OCR_WARMUP is exactly "1".
# A failed warmup must not stop the service: /detect and /health keep working and the first /ocr call retries
# the lazy load.
if os.environ.get("OCR_WARMUP") == "1" and callable(getattr(_ocr, "warmup", None)):
    try:
        _ocr.warmup()
        log.info("ocr warmup ok (%s)", type(_ocr).__name__)
    except Exception:
        log.warning("ocr warmup failed (%s); the first /ocr call will retry the load", type(_ocr).__name__,
                    exc_info=True)
