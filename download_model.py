import os, sys, requests, pathlib

MODEL_URL = os.getenv("MODEL_URL")  # ضعه في بيئة Render
MODEL_DIR = pathlib.Path("models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "model.gguf"

if not MODEL_URL:
    print("MODEL_URL env var is missing.", file=sys.stderr)
    sys.exit(1)

if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 100_000_000:
    print("Model already exists, skipping download.")
    sys.exit(0)

print("Downloading model from:", MODEL_URL)
with requests.get(MODEL_URL, stream=True) as r:
    r.raise_for_status()
    with open(MODEL_PATH, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

print("Saved to", MODEL_PATH)
