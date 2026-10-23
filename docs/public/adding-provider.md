# Adding a provider adapter

The current shared text and embedding registry supports Google Gemini.
Supported model names and capabilities live in
[`registry.py`](../../backend/app/providers/registry.py),
[`generation_profiles.py`](../../backend/app/providers/generation_profiles.py)
and the relevant contracts. Image generation and recognition have their own
adapters and capability policies; a text registry entry does not enable them.

For a new adapter:

1. Define its supported request, output, usage and error behavior using the
   existing provider contracts. Reject unsupported capability/model pairs.
2. Keep external SDK and HTTP behavior in the adapter. Supply credentials only
   through the existing authorized resolution boundary.
3. Honor the caller's deadline, cancellation, call count and retry policy,
   including retries hidden by an SDK. Do not add an implicit provider fallback.
4. Validate returned schemas and convert failures into safe typed errors.
5. Test deterministic success, malformed results, denied credentials, usage,
   timeout, cancellation and retry exhaustion without network calls.
6. If the UI changes, update English and Korean labels and expose only capabilities
   the backend actually supports.

Adding an experimental adapter is separate from advertising official support.
Review dependency licenses, notices and the affected CI scope. A general plugin
framework is not required for a single concrete integration.
