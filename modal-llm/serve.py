"""Modal deployment: Qwen 2.5 32B Instruct AWQ via vLLM on H100.

Adapted from synix-vllm (proven working pattern). Uses cls + asgi_app
so vLLM can fully start before accepting traffic.

Deploy:
    modal run modal-llm/serve.py::download_model   # pre-cache weights (once)
    modal deploy modal-llm/serve.py                # deploy the server

Test:
    curl https://synix--blah-llm-inference-serve.modal.run/v1/chat/completions \
      -H "Content-Type: application/json" \
      -d '{"model":"llm","messages":[{"role":"user","content":"hi"}]}'
"""

import subprocess
import time

import fastapi
import modal

MODEL_ID = "Qwen/Qwen2.5-32B-Instruct-AWQ"
VOLUME_NAME = "blah-model-cache"
VLLM_PORT = 8000
CACHE_DIR = "/root/.cache/huggingface"

vllm_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12"
    )
    .pip_install(
        "vllm==0.13.0",
        "huggingface_hub[hf_transfer]",
    )
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "HF_XET_HIGH_PERFORMANCE": "1",
    })
)

app = modal.App("blah-llm")
model_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

# --- FastAPI proxy (runs in front of vLLM) ---

web_app = fastapi.FastAPI()


@web_app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_ID}


@web_app.post("/v1/chat/completions")
async def chat_completions(request: dict):
    """OpenAI-compatible chat completions — proxy to vLLM."""
    import json
    import urllib.request

    body = json.dumps(request).encode()
    req = urllib.request.Request(
        f"http://localhost:{VLLM_PORT}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=280) as resp:
        return json.loads(resp.read())


@web_app.post("/v1/batch")
async def batch_completions(request: dict):
    """Process multiple chat completions concurrently against localhost vLLM."""
    import asyncio
    import json
    import urllib.request

    requests = request["requests"]  # [{messages, max_tokens, model?}, ...]

    async def do_one(payload):
        """Run a single completion in a thread (urllib is blocking)."""
        body = json.dumps({
            "model": payload.get("model", "llm"),
            "messages": payload["messages"],
            "max_tokens": payload.get("max_tokens", 4096),
        }).encode()
        req = urllib.request.Request(
            f"http://localhost:{VLLM_PORT}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        loop = asyncio.get_event_loop()
        resp_bytes = await loop.run_in_executor(
            None,
            lambda: urllib.request.urlopen(req, timeout=280).read(),
        )
        return json.loads(resp_bytes)

    results = await asyncio.gather(
        *(do_one(r) for r in requests),
        return_exceptions=True,
    )

    responses = []
    for r in results:
        if isinstance(r, Exception):
            responses.append({"error": str(r)})
        else:
            responses.append(r)

    return {"responses": responses}


# --- Pre-download model weights (run once) ---


@app.function(
    image=vllm_image,
    volumes={CACHE_DIR: model_volume},
    timeout=900,
)
def download_model():
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL_ID, cache_dir=CACHE_DIR)
    model_volume.commit()


# --- Inference server ---


@app.cls(
    image=vllm_image,
    gpu="L40S",
    volumes={CACHE_DIR: model_volume},
    timeout=600,
    scaledown_window=600,
)
@modal.concurrent(max_inputs=32)
class Inference:
    @modal.enter()
    def start_engine(self):
        cmd = [
            "vllm", "serve", MODEL_ID,
            "--host", "0.0.0.0",
            "--port", str(VLLM_PORT),
            "--served-model-name", MODEL_ID, "llm",
            "--max-model-len", "8192",
            "--gpu-memory-utilization", "0.90",
            "--enforce-eager",
            "--disable-log-requests",
        ]
        self.proc = subprocess.Popen(
            " ".join(cmd),
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self._wait_for_server()

    def _wait_for_server(self, timeout: int = 300):
        import urllib.error
        import urllib.request

        start = time.monotonic()
        while time.monotonic() - start < timeout:
            try:
                req = urllib.request.Request(f"http://localhost:{VLLM_PORT}/health")
                urllib.request.urlopen(req, timeout=2)
                print(f"vLLM ready after {time.monotonic() - start:.0f}s")
                return
            except (urllib.error.URLError, ConnectionError, OSError):
                if self.proc.poll() is not None:
                    output = self.proc.stdout.read().decode() if self.proc.stdout else ""
                    raise RuntimeError(
                        f"vLLM exited with code {self.proc.returncode}:\n{output}"
                    )
                time.sleep(1)
        raise TimeoutError(f"vLLM did not start within {timeout}s")

    @modal.exit()
    def stop_engine(self):
        if hasattr(self, "proc") and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=10)

    @modal.asgi_app()
    def serve(self):
        return web_app
