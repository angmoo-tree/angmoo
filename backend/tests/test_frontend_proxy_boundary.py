"""The framework Proxy is a narrow server adapter, never a product import seam."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("frontend_rules",ROOT/"scripts/ci/frontend_completed_boundaries.py")
import sys
sys.path.insert(0,str(ROOT/"scripts/ci"))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_proxy_can_only_use_server_security_helper(tmp_path):
    source=tmp_path/"frontend/src";source.mkdir(parents=True)
    proxy=source/"proxy.ts";proxy.write_text('import {NextResponse} from "next/server"; import {policy} from "@/lib/security/csp";',encoding="utf-8")
    assert not module.check_completed_frontend(source)
    proxy.write_text('import {render} from "@/features/media/components/comfy-editor";',encoding="utf-8")
    assert any("proxy_imports_product" in item for item in module.check_completed_frontend(source))
    proxy.write_text('"use client";',encoding="utf-8")
    assert any("proxy_must_be_server" in item for item in module.check_completed_frontend(source))
