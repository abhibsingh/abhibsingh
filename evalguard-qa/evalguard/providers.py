"""Offline replay and an optional Ollama chat adapter."""
import json
import math
import time
import urllib.request
from .core import ConfigurationError, read_json


class ReplayProvider:
    name = "replay (synthetic fixtures; not live model measurements)"

    def __init__(self, path):
        self.responses = read_json(path)
        if not isinstance(self.responses, dict):
            raise ConfigurationError("Response fixture must be an object keyed by case ID")

    def generate(self, case):
        value = self.responses[case["id"]]
        return value["text"], value["latency_ms"]


class OllamaProvider:
    def __init__(self, model, base_url="http://localhost:11434", timeout=120):
        if not model:
            raise ConfigurationError("Ollama requires --model")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ConfigurationError("Timeout must be a positive finite number")
        if not base_url.startswith(("http://", "https://")):
            raise ConfigurationError("Ollama URL must use HTTP or HTTPS")
        self.model, self.timeout = model, timeout
        self.url = base_url.rstrip("/") + "/api/chat"
        self.name = f"ollama:{model}"

    def generate(self, case):
        payload = json.dumps({
            "model": self.model, "messages": case["messages"], "stream": False,
            "options": {"temperature": 0},
        }).encode("utf-8")
        request = urllib.request.Request(
            self.url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        start = time.perf_counter()
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.load(response)
        latency = (time.perf_counter() - start) * 1000
        return data["message"]["content"], latency
