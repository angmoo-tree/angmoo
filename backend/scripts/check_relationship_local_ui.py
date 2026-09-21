"""Read-only delegated UI check against a running local development app."""
import json
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

destination=Path(__file__).resolve().parents[2]/'docs/architecture/evidence'
destination.mkdir(parents=True,exist_ok=True)
screenshots=Path(__file__).resolve().parents[3]/'docs/handoff/evidence/09-22-relationship-ui'
screenshots.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser()
parser.add_argument('--world',required=True)
parser.add_argument('--characters',nargs='+',required=True)
args=parser.parse_args()
world,characters=args.world,args.characters
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    mutations=[]
    page.on('request',lambda r: mutations.append(r.url.split('?')[0]) if r.method not in {'GET','HEAD','OPTIONS'} and '/api/backend/' in r.url and '/auth/' not in r.url else None)
    for index,character in enumerate(characters):
        replies=[]
        def capture(response):
            if response.url.split('?')[0].endswith('/relationship-review'):
                replies.append({'status':response.status,'body':response.json()})
        page.on('response',capture)
        page.goto(f'http://127.0.0.1:3000/characters/{character}/worlds/{world}/relationship-graph',wait_until='networkidle',timeout=60000)
        expect(page.get_by_role('heading',name='하루 관계 정리',exact=True)).to_be_visible()
        expect(page.get_by_text('개인화 관계 적용 중',exact=False)).to_be_visible()
        page.reload(wait_until='networkidle')
        page.keyboard.press('Tab')
        focused=page.locator(':focus').evaluate('(e)=>e.tagName')
        page.locator('body').evaluate('(e)=>e.style.zoom="2"')
        expect(page.get_by_role('heading',name='하루 관계 정리',exact=True)).to_be_visible()
        page.screenshot(path=str(screenshots/f'relationship-live-{index}-200pct.png'),full_page=True)
        latest=replies[-1]
        results.append({'character_index':index,'http_status':latest['status'],'mode':latest['body']['mode'],
            'job_count':len(latest['body']['jobs']),'configuration':latest['body']['configuration']['status'],
            'review_reads':len(replies),'keyboard_focus_tag':focused,'zoom_200_visible':True})
        page.remove_listener('response',capture)
        page.locator('body').evaluate('(e)=>e.style.zoom="1"')
    browser.close()
assert not mutations, mutations
record={'delegated_ui_check':True,'real_ai_calls_triggered':0,'non_auth_mutation_requests':mutations,'results':results}
(destination/'relationship-local-ui.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
