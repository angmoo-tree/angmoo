"""Read-only public catalog capture; never accepts an API key or generates images."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
MODELS = {
    "nanogpt": ("krea-v2/turbo", "z-image-turbo", "nano-banana-2"),
    "openrouter": ("krea/krea-2-medium-turbo", "google/gemini-3.1-flash-image", "openai/gpt-image-2.5-flare"),
}


def read(url):
    with urlopen(url, timeout=20) as response:
        data = response.read(2*1024*1024+1)
    if len(data) > 2*1024*1024:
        raise ValueError("catalog_response_size_exceeded")
    return json.loads(data)


def main():
    evidence = {"captured_at": datetime.now(timezone.utc).isoformat(), "models": {}}
    for provider, models in MODELS.items():
        root = "https://api.nano-gpt.com" if provider == "nanogpt" else "https://openrouter.ai"
        for model in models:
            url = f"{root}/api/v1/images/models/{model}/endpoints"
            evidence["models"][f"{provider}:{model}"] = {"url": url, "payload": read(url)}
    novel = read("https://image.novelai.net/docs/doc.json")
    names = ("image.ImageGenerationRequest", "image.RequestParameters", "image.V4ConditionInput", "image.V4ExternalCaption", "image.ImageGenerationJsonResponse", "image.ImageJson", "user.SubscriptionResponse")
    evidence["novelai"] = {"url": "https://image.novelai.net/docs/doc.json", "definitions": {name: novel["definitions"][name] for name in names}}
    path = ROOT / "backend/app/integrations/image_catalog.json"
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print("Captured six public model endpoints and NovelAI wire definitions; no generation calls.")


if __name__ == "__main__":
    main()
