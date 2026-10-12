"""Partner transport contracts: controlled HTTP, never a user's server or key."""
import asyncio
import json
from copy import deepcopy
import pytest
from app.domains.media.service.comfy_workflows import partner_submission_target,validate_partner_configuration,freeze_comfy_request
from app.domains.media.generation_contracts import ComfyOptions,GenerationRequest,EffectiveReference,ImagePreparationError
from app.integrations.comfy_images import ComfyImageClient
from image_integration.test_comfy_partner import WORKFLOW,transport
from image_integration.test_providers import png
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('url,target',[
 ('http://localhost:8188/base/','http://127.0.0.1:8188/base'),
 ('http://LOCALHOST/base','http://127.0.0.1/base'),
 ('http://127.0.0.2:8188','http://127.0.0.2:8188'),
 ('http://[::1]:8188/base','http://[::1]:8188/base'),
 ('https://example.test:9443/base','https://example.test:9443/base'),
])
def test_exact_allowed_target_keeps_port_base_path_and_saved_string(url,target):
 assert partner_submission_target(url,True)==target
 assert partner_submission_target(url,False)==url.rstrip('/')


@pytest.mark.parametrize('url',['http://example.test','http://192.168.0.3','http://10.0.0.2','http://host.docker.internal:8188','http://comfyui:8188','http://localhost.evil.test','http://localhost.:8188','http://127.0.0.1.evil.test','http://127.1:8188','http://[::ffff:127.0.0.1]:8188'])
def test_remote_alias_and_disguised_http_cannot_send_partner_key(url):
 with pytest.raises(ImagePreparationError,match='comfy_partner_https_required'):partner_submission_target(url,True)
 assert partner_submission_target(url,False)==url


@pytest.mark.parametrize('reference',[False,True])
def test_direct_rejection_precedes_reference_upload_submit_and_callback(reference):
 options=ComfyOptions(base_url='http://remote.example.test',partner_auth=True,workflow=WORKFLOW)
 request=GenerationRequest('comfyui','workflow','synthetic scene',None,options.model_dump(),EffectiveReference(False))
 http=transport();callbacks=[]
 async def called():callbacks.append('submit')
 with pytest.raises(ImagePreparationError,match='comfy_partner_https_required') as failure:
  asyncio.run(ComfyImageClient(options.base_url,http).generate(request,None,png() if reference else None,partner_key='synthetic-key-never-send',on_submit=called,on_receipt=None))
 assert http.calls==[] and callbacks==[]
 assert 'synthetic-key-never-send' not in str(failure.value)


def test_keyless_receipt_history_is_not_new_submission_or_endpoint_rewrite():
 options=ComfyOptions(base_url='http://remote.example.test',partner_auth=True,workflow=WORKFLOW)
 request=GenerationRequest('comfyui','workflow','old synthetic scene',None,options.model_dump(),EffectiveReference(False))
 http=transport()
 result=asyncio.run(ComfyImageClient(options.base_url,http).generate(request,None,None,receipt='partner-receipt',partner_key=None,on_receipt=None))
 assert result.content==png()
 assert all(method=='GET' and url.startswith(options.base_url) and not kwargs.get('key') for method,url,kwargs in http.calls)
 assert len(http.calls)==2


def test_localhost_new_submission_is_pinned_and_key_only_appears_in_prompt_body():
 options=ComfyOptions(base_url='http://localhost:8188/base',partner_auth=True,workflow=WORKFLOW)
 request=GenerationRequest('comfyui','workflow','scene',None,options.model_dump(),EffectiveReference(False))
 http=transport();receipts=[]
 async def receipt(value):receipts.append(value)
 asyncio.run(ComfyImageClient(options.base_url,http).generate(request,None,None,partner_key='synthetic-key',on_receipt=receipt))
 assert receipts==['partner-receipt']
 assert all(url.startswith('http://127.0.0.1:8188/base/') for _,url,_ in http.calls)
 prompt=next(kwargs for method,url,kwargs in http.calls if method=='POST' and url.endswith('/prompt'))
 assert json.loads(prompt['content'])['extra_data']=={'api_key_comfy_org':'synthetic-key'}
 assert options.base_url=='http://localhost:8188/base' and all(not kwargs.get('key') for _,_,kwargs in http.calls)


def test_unchanged_off_history_can_be_cleared_but_cannot_be_activated_or_rekeyed():
 options=ComfyOptions(base_url='http://old.example.test',partner_auth=True,workflow=WORKFLOW)
 previous={'active':True,'options':options.model_dump(exclude_none=True)}
 validate_partner_configuration(options,previous=previous,auto_enabled=False)
 sparse={"active":True,"options":{"base_url":options.base_url,"partner_auth":True,"workflow":WORKFLOW}}
 validate_partner_configuration(options,previous=sparse,auto_enabled=False)
 for active,new_key in ((True,False),(False,True)):
  with pytest.raises(ImagePreparationError,match='comfy_partner_https_required'):
   validate_partner_configuration(options,previous=previous,auto_enabled=active,new_key=new_key)
 changed=options.model_copy(update={'base_url':'http://other.example.test'})
 with pytest.raises(ImagePreparationError):validate_partner_configuration(changed,previous=previous,auto_enabled=False)
 with pytest.raises(ImagePreparationError):validate_partner_configuration(options,previous=None,auto_enabled=False)
 off=options.model_copy(update={'partner_auth':False})
 validate_partner_configuration(off,previous=previous,auto_enabled=False)
 with pytest.raises(ImagePreparationError):freeze_comfy_request(GenerationRequest('comfyui','workflow','scene',None,options.model_dump(),EffectiveReference(False)))


@pytest.mark.parametrize('path',['legacy_reference','placeholder_reference','text_fallback'])
def test_guard_is_before_every_reference_mode_and_selected_fallback(path):
 def sample(name):return json.loads((ROOT/f'backend/app/domains/media/samples/{name}.json').read_text('utf-8'))
 if path=='legacy_reference':
  data=sample('comfy-reference');options=ComfyOptions(base_url='http://comfyui:8188',partner_auth=True,workflow=data['workflow'],values=data['values'])
 else:
  data={'input_mode':'placeholders','prompt':sample('comfy-api-reference')}
  options=ComfyOptions(options_schema_version=2,base_url='http://comfyui:8188',partner_auth=True,workflow=data,
   text_workflow={'input_mode':'placeholders','prompt':sample('comfy-api-text')} if path=='text_fallback' else None)
 request=GenerationRequest('comfyui','workflow','scene',None,options.model_dump(),EffectiveReference(path!='text_fallback'))
 http=transport();callbacks=[]
 async def submitted():callbacks.append(True)
 with pytest.raises(ImagePreparationError,match='https_required'):
  asyncio.run(ComfyImageClient(options.base_url,http).generate(request,None,None if path=='text_fallback' else png(),
   partner_key='synthetic-only',on_receipt=None,on_submit=submitted))
 assert http.calls==[] and callbacks==[]


def test_same_remote_http_is_supported_keyless_when_partner_is_off():
 options=ComfyOptions(base_url='http://remote.example.test',partner_auth=False,workflow=WORKFLOW)
 request=GenerationRequest('comfyui','workflow','scene',None,options.model_dump(),EffectiveReference(False))
 http=transport()
 async def received(_):pass
 result=asyncio.run(ComfyImageClient(options.base_url,http).generate(request,None,None,
  partner_key='must-not-send-when-off',on_receipt=received))
 assert result.receipt=='partner-receipt'
 sent=next(kwargs for method,url,kwargs in http.calls if method=='POST' and url.endswith('/prompt'))
 assert set(json.loads(sent['content']))=={'prompt'} and all(not kwargs.get('key') for _,_,kwargs in http.calls)
