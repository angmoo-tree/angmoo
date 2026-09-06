"""Real Git-AST retirement predicates; no old application module is loaded."""
import importlib.util
from pathlib import Path

_source = Path(__file__).resolve().parents[2] / "scripts/ci/compatibility_facade_retirement.py"
_spec = importlib.util.spec_from_file_location("compatibility_facade_retirement", _source)
proof = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proof)
export_matches = proof.export_matches
module_matches = proof.module_matches
alias_retired = proof.alias_retired
module_retired = proof.module_retired
historical_imports = proof.historical_imports
historical_function_names = proof.historical_function_names
