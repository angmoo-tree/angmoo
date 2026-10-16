"""Public HTTPX hooks on the existing SDK client; payloads never leave it."""
from importlib.util import find_spec
from uuid import uuid4
from app.core import work_observation as observation


class EmbeddingTransportObservation:
    def __init__(self, *, input_count, dimension):
        self.active = observation.enabled()
        self.context = observation.facts() if self.active else {}
        self.logical_id = uuid4().hex if self.active else None
        self.input_count, self.dimension = input_count, dimension
        self.attempts = {}
        self.supported = self.active and find_spec("aiohttp") is None

    def emit(self, **facts):
        if not self.active:
            return
        observation.emit("embedding_http", **{**self.context, "logical_id": self.logical_id,
            "input_count": self.input_count, **facts})

    def client_args(self):
        if not self.active:
            return None
        # SDK 2.17 selects aiohttp when installed. Its internally constructed
        # session has no public trace-config hook. Do not switch transports or
        # change client ownership to manufacture an observation.
        self.emit(boundary="logical_start", transport="httpx" if self.supported else "unsupported_aiohttp",
                  transport_observable=self.supported)
        if not self.supported:
            return None
        return {"event_hooks": {"request": [self.start], "response": [self.response]}}

    async def start(self, request):
        attempt = uuid4().hex
        self.attempts[id(request)] = attempt
        endpoint = "batchEmbedContents" if request.url.path.endswith(":batchEmbedContents") else "embedContent" if request.url.path.endswith(":embedContent") else "unknown"
        self.emit(boundary="attempt_start", attempt_id=attempt, endpoint=endpoint, transport="httpx")

    async def response(self, response):
        attempt = self.attempts.pop(id(response.request), None)
        self.emit(boundary="attempt_end", attempt_id=attempt, status_code=response.status_code, outcome="response_headers")

    def validated(self, count):
        self.emit(boundary="response_validated", response_count=count, dimension=self.dimension, outcome="valid")

    def finish(self):
        for attempt in self.attempts.values():
            self.emit(boundary="attempt_end", attempt_id=attempt, outcome="transport_incomplete")
        self.attempts.clear()
        self.emit(boundary="logical_end", transport_observable=self.supported)
