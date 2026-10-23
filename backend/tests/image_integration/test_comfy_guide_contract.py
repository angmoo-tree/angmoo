from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[3]

def test_english_guide_keeps_code_payloads_auth_routes_and_public_korean_policy():
    ko=(ROOT/"docs/agent_guide.ko.md").read_text("utf-8")
    en=(ROOT/"docs/agent_guide.md").read_text("utf-8")
    pattern=r"```([^\n]*)\n(.*?)```"
    original=[(kind,text) for kind,text in re.findall(pattern,ko,re.S) if kind.strip()!="text"]
    translated=[(kind,text) for kind,text in re.findall(pattern,en,re.S) if kind.strip()!="text"]
    assert original==translated
    assert en.count("Write all public posts and replies in Korean.")==1
    assert "Write public posts and replies in Korean." in en
    assert len(re.findall(r"^## [0-9]+",ko,re.M))==len(re.findall(r"^## [0-9]+",en,re.M))
    outside=re.sub(pattern,"",en,flags=re.S)
    assert not re.search(r"[가-힣]",outside)
