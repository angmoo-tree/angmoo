# Adding a provider adapter

Gemini is the only official v0.2 text provider.

For an experimental adapter:

1. define capabilities in `app/providers/registry.py`;
2. use request/response contracts from `app/providers/contracts.py`;
3. keep the SDK import in the adapter;
4. normalize errors without credential material;
5. add network-free fake and adapter tests;
6. verify retry, usage, and LangGraph result shapes.

Official-support status or a general plugin framework requires a separate scope
decision. Provider changes require hosted validation.
