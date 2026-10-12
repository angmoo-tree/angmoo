"""Author assets independently, keep historical configs, validate real raw input."""
import hashlib
import json
import importlib.util
from pathlib import Path
from image_integration.test_comfy_http_contracts import client
import pytest
from app.domains.media.service.comfy_workflows import analyze_source,render_workflow,freeze_comfy_request
from app.domains.media.generation_contracts import ComfyOptions,GenerationRequest,EffectiveReference,ImagePreparationError
from app.domains.media.setting_schemas import ComfyRetainedContract

ROOT=Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("kind",["text","reference"])
def test_authorized_format_contract_is_read_only_without_a_media_runtime(client,kind):
    # This app deliberately has no MediaRuntime/client/key store. Sample and
    # raw analysis must succeed without requesting any of those dependencies.
    old=client.get(f"/media/comfy-samples/{kind}")
    new=client.get(f"/media/comfy-samples/{kind}?format=api_json")
    assert old.status_code==new.status_code==200
    assert old.json()==json.loads((ROOT/f"backend/app/domains/media/samples/comfy-{kind}.json").read_text("utf-8"))
    assert new.json()==json.loads((ROOT/f"backend/app/domains/media/samples/comfy-api-{kind}.json").read_text("utf-8"))
    assert client.get(f"/media/comfy-samples/{kind}?format=unknown").status_code==404
    assert client.get("/media/comfy-samples/../secrets?format=api_json").status_code==404
    assert client.post("/media/comfy-workflows/analyze",json={"source_json":new.text,"input_mode":"placeholders"}).status_code==200
ASSETS=ROOT/'backend/app/domains/media/samples'
HISTORICAL={'text':{'953805b53bc6eb11b02fb977f430118cdda01901a7998323a9711d25cf1908c0','017e3b1b54e5cd740e9f0120ba4f523e45b4485e3276588f7bec2437a0e39b68'},'reference':{'81b7b1275065de9e3e624bf55eaae038410ef142302a3d49e8ebf1c877b4c602','dcfdaa4e65921c6fd96e363435ba5ed82ad55c72a9d966af60090e682547870a'}}


@pytest.mark.parametrize('kind',['text','reference'])
def test_api_assets_are_plain_deterministic_and_historical_hashes_are_unchanged(kind):
 spec=importlib.util.spec_from_file_location('sample_builder',ROOT/'scripts/diagnostics/author_comfy_image_samples.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
 encoded=(json.dumps(builder.make_api(kind=='reference'),ensure_ascii=False,indent=2)+'\n').encode('utf-8')
 assert encoded==(ASSETS/f'comfy-api-{kind}.json').read_bytes()
 assert hashlib.sha256((ASSETS/f'comfy-{kind}.json').read_bytes()).hexdigest() in HISTORICAL[kind]
 graph=json.loads(encoded);analysis=analyze_source(encoded.decode())
 assert graph==analysis['prompt'] and analysis['prompt_applied']
 assert set(graph)=={'1','2','3','4','5','6','7'}|({'8','9'} if kind=='reference' else set())
 assert not any(field in graph for field in ('workflow','bindings','values','options_schema_version','output_node'))
 assert 'choose-installed-model' not in encoded.decode()
 if kind=='reference':
  assert graph['8']=={'class_type':'ETN_LoadImageBase64','inputs':{'image':'%char_avatar%'}}
  assert graph['9']['inputs']['image']==['8',0] and graph['5']['inputs']['pixels']==['9',0]


def test_editor_preservation_uses_backend_binding_and_output_validation():
 raw=(ASSETS/'comfy-api-text.json').read_text(encoding='utf-8')
 for retained in (ComfyRetainedContract(output={'mode':'explicit_node','node_id':'old-output'}),ComfyRetainedContract(bindings={'positive':{'node_id':'gone','input_name':'text'}},output={'mode':'auto_first_image'})):
  with pytest.raises(ImagePreparationError):analyze_source(raw,'node_bindings',retained_contract=retained)
 assert analyze_source(raw,'placeholders',retained_contract=ComfyRetainedContract(output={'mode':'explicit_node','node_id':'7'}))['prompt']['7']['class_type']=='SaveImage'
