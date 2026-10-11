"""CPU-only QA contract agreed with the GLM integration owner, 2026-10-11.

No real transformers/torch, model downloads, GPU, .env, or backend database.
Strict xfails describe pending builder work; remove each when its fix lands.
"""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import ModuleType, SimpleNamespace

import pytest
from PIL import Image


@pytest.fixture
def runtime(monkeypatch):
    record = SimpleNamespace(cuda=False, processors=0, tokenizers=0, loads=[],
                             images=[], decoded=[], active=0, peak=0, moves=[])
    guard = threading.Lock()

    class Tokens(list):
        @property
        def shape(self):
            return (len(self), len(self[0]))

    class Batch(dict):
        def to(self, *args, **kwargs):
            record.moves.append((args, kwargs))
            return self

    def capture_images(value):
        if isinstance(value, Image.Image):
            record.images.append(value.copy())
        elif isinstance(value, dict):
            for item in value.values():
                capture_images(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                capture_images(item)

    class Processor:
        def apply_chat_template(self, messages, **kwargs):
            capture_images(messages)
            if not kwargs.get("tokenize", False):
                return "image prompt"
            return self()

        def __call__(self, *args, **kwargs):
            capture_images(args)
            capture_images(kwargs)
            return Batch(input_ids=Tokens([[11, 12, 13]]), pixel_values=object())

        def decode(self, tokens, **kwargs):
            record.decoded.append(list(tokens))
            return "  <think>private reasoning</think>\nMILK 3.48\nTOTAL 3.48  "

        def batch_decode(self, rows, **kwargs):
            return [self.decode(row, **kwargs) for row in rows]

    class AutoProcessor:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            record.processors += 1
            return Processor()

    class AutoTokenizer:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            record.tokenizers += 1
            return Processor()

    class Model:
        device = "cpu"

        @classmethod
        def from_pretrained(cls, model_id, **kwargs):
            with guard:
                record.loads.append((model_id, kwargs))
            # Release the GIL so simultaneous lazy initialization can be detected.
            time.sleep(0.03)
            return cls()

        def to(self, *args, **kwargs):
            record.moves.append((args, kwargs))
            if args:
                self.device = args[0]
            return self

        def eval(self):
            return self

        def generate(self, **kwargs):
            with guard:
                record.active += 1
                record.peak = max(record.peak, record.active)
            try:
                time.sleep(0.03)
                return Tokens([[11, 12, 13, 21, 22]])
            finally:
                with guard:
                    record.active -= 1

    transformers = ModuleType("transformers")
    transformers.AutoProcessor = AutoProcessor
    transformers.AutoTokenizer = AutoTokenizer
    transformers.AutoModelForMultimodalLM = Model
    transformers.GlmOcrForConditionalGeneration = Model
    torch = ModuleType("torch")
    torch.bfloat16 = "bfloat16"
    torch.float32 = "float32"
    torch.cuda = SimpleNamespace(is_available=lambda: record.cuda)
    torch.inference_mode = contextlib.nullcontext
    torch.no_grad = contextlib.nullcontext
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.delenv("GLM_OCR_MODEL", raising=False)
    # Let legacy temp-file code reach later assertions without Windows sharing
    # errors masking them. The in-memory-image case overrides this with a deny.
    class MemoryPng(io.BytesIO):
        name = "contract.png"
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", lambda **kw:
                        contextlib.nullcontext(SimpleNamespace(name=MemoryPng())))
    # Load an isolated module so concurrent QA cannot retain a patched engine.
    path = Path(__file__).parents[2] / "ocr" / "receipt_pipeline.py"
    spec = importlib.util.spec_from_file_location("glm_contract_receipt_pipeline", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    record.engine_class = module.GlmOcrEngine
    return record


def test_constructor_is_lazy_and_honors_model_override(runtime, monkeypatch):
    monkeypatch.setenv("GLM_OCR_MODEL", "local-test-model")
    assert runtime.engine_class().model_id == "local-test-model"
    assert runtime.engine_class(model_id="explicit-test-model").model_id == "explicit-test-model"
    assert not runtime.loads
    assert runtime.processors == runtime.tokenizers == 0


def test_sequential_load_is_cached(runtime):
    engine = runtime.engine_class(model_id="local-test-model")
    engine.load()
    engine.load()
    assert len(runtime.loads) == 1


@pytest.mark.xfail(strict=True, reason="GLM-1: pending engine fix")
def test_load_uses_processor_not_tokenizer(runtime):
    runtime.engine_class().load()
    assert runtime.processors == 1
    assert runtime.tokenizers == 0


@pytest.mark.xfail(strict=True, reason="GLM-2: pending engine fix")
def test_image_stays_in_memory(runtime, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("OCR must pass PIL pixels in memory, never create a temporary file")
    for name in ("NamedTemporaryFile", "mkstemp", "mktemp"):
        monkeypatch.setattr(tempfile, name, forbidden)
    original = Image.new("RGB", (37, 19), (21, 43, 65))
    runtime.engine_class().image_to_text(original)
    assert runtime.images, "No PIL image reached the processor"
    received = runtime.images[-1]
    assert received.size == original.size
    assert received.tobytes() == original.tobytes()


@pytest.mark.xfail(strict=True, reason="GLM-3: pending engine fix")
def test_large_image_is_capped_without_distortion(runtime):
    engine = runtime.engine_class()
    assert engine.MAX_PIXELS == 2_400_000
    assert engine.MAX_PIXELS <= 3_000_000
    original = Image.new("RGB", (4000, 3000))
    engine.image_to_text(original)
    assert runtime.images, "No PIL image reached the processor"
    width, height = runtime.images[-1].size
    assert 0 < width * height <= engine.MAX_PIXELS
    assert abs(height - width * 3000 / 4000) <= 1
    assert original.size == (4000, 3000), "Do not mutate the caller's image"


@pytest.mark.xfail(strict=True, reason="GLM-4: pending engine fix")
def test_small_image_is_not_upscaled(runtime):
    runtime.engine_class().image_to_text(Image.new("RGB", (64, 48)))
    assert runtime.images, "No PIL image reached the processor"
    assert runtime.images[-1].size == (64, 48)


@pytest.mark.xfail(strict=True, reason="GLM-5: pending engine fix")
def test_concurrent_calls_are_serialized_and_load_once(runtime):
    engine = runtime.engine_class()
    start = threading.Barrier(2)

    def recognize():
        start.wait(timeout=5)
        return engine.image_to_text(Image.new("RGB", (64, 48)))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(recognize) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]
    assert all(isinstance(result, str) for result in results)
    assert runtime.peak == 1
    assert len(runtime.loads) == 1
    assert runtime.processors == 1


def test_only_completion_is_decoded(runtime):
    runtime.engine_class().image_to_text(Image.new("RGB", (64, 48)))
    assert runtime.decoded == [[21, 22]], "Prompt tokens must not be decoded"


@pytest.mark.xfail(strict=True, reason="GLM-6: pending engine fix")
def test_thinking_is_stripped(runtime):
    result = runtime.engine_class().image_to_text(Image.new("RGB", (64, 48)))
    assert result == "MILK 3.48\nTOTAL 3.48"


@pytest.mark.parametrize("cuda,dtype,device", [
    pytest.param(True, "bfloat16", "cuda:0", marks=pytest.mark.xfail(
        strict=True, reason="GLM-7: pending engine fix")),
    pytest.param(False, "float32", "cpu", marks=pytest.mark.xfail(
        strict=True, reason="GLM-8: pending engine fix")),
])
def test_explicit_device_and_dtype(runtime, cuda, dtype, device):
    runtime.cuda = cuda
    runtime.engine_class().load()
    assert len(runtime.loads) == 1
    kwargs = runtime.loads[0][1]
    assert kwargs.get("dtype", kwargs.get("torch_dtype")) == dtype
    placement = kwargs.get("device_map")
    allowed = (device, 0) if cuda else (device,)
    mapped = placement in allowed if not isinstance(placement, dict) else placement.get("") in allowed
    moved = any(args and args[0] in allowed or kw.get("device") in allowed
                for args, kw in runtime.moves)
    assert mapped or moved, f"Expected explicit placement on {device}, got {placement!r}"
