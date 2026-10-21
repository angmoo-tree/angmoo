import { expect, test, type Page } from "@playwright/test";
import { installSocialChatFixture, chatRoute } from "./world-social-chat-fixture";
import { installWorldFeedFixture, feedRoute } from "./world-feed-fixture";
import { uiDManualPost } from "./continuity-next-fixture";

function pane(page: Page) { return page.locator('[data-message-id]').first().locator('xpath=../..'); }
async function chat(page: Page, baseURL: string) {
  const state = await installSocialChatFixture(page, new URL(baseURL).port === "3331", baseURL, "en");
  const sample = state.thread.messages[0];
  state.thread.messages = Array.from({length:180}, (_,i) => ({...sample,id:i+1,content:`Synthetic message ${i+1} ` + 'body '.repeat(16)}));
  await page.goto(chatRoute());
  await expect(page.locator('[data-message-id="180"]')).toBeVisible();
  return state;
}

test('Chat latest 50, delayed prepend preserves the response-time reading anchor', async ({page}, info) => {
  await chat(page, String(info.project.use.baseURL));
  await expect(page.locator('[data-message-id]')).toHaveCount(50);
  await page.screenshot({path:info.outputPath("chat-latest.png"),animations:"disabled"});
  let reads=0;
  await page.route('**/messages?**', async route => {
    if (new URL(route.request().url()).searchParams.has('before')) { ++reads; await new Promise(resolve=>setTimeout(resolve,800)); }
    await route.fallback();
  });
  await pane(page).evaluate(node => {node.scrollTop=0;});
  await expect.poll(()=>reads).toBe(1);
  await page.locator('[data-message-id="150"]').scrollIntoViewIfNeeded();
  const before = (await page.locator('[data-message-id="150"]').boundingBox())!.y;
  await expect(page.locator('[data-message-id]')).toHaveCount(100);
  const after = (await page.locator('[data-message-id="150"]').boundingBox())!.y;
  expect(Math.abs(after-before)).toBeLessThan(4);
  expect(reads).toBe(1);
});

test('Chat failed page keeps draft; catch-up is bounded and fills intermediate gaps', async ({page}, info) => {
  const state=await chat(page,String(info.project.use.baseURL));
  const input=page.locator('textarea').first(); await input.fill('Retained draft');
  let afterReads=0;
  await page.route('**/messages?**',async route=>{
    const params=new URL(route.request().url()).searchParams;
    if(params.has('before')) return route.fulfill({status:503,json:{detail:'fixture_read_unavailable'}});
    if(params.has('after')) ++afterReads;
    return route.fallback();
  });
  await pane(page).evaluate(node=>{node.scrollTop=0;});
  await expect(page.getByRole('button',{name:'Retry loading'})).toBeVisible();
  await expect(input).toHaveValue('Retained draft');
  const sample=state.thread.messages[0];
  state.thread.messages.push(...Array.from({length:140},(_,i)=>({...sample,id:181+i,content:`Remote ${181+i}`})));
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await expect.poll(()=>afterReads).toBe(2);
  await expect(page.getByRole('button',{name:'Load more missing messages'})).toBeVisible();
  await page.getByRole('button',{name:'Load more missing messages'}).click();
  await expect(page.locator('[data-message-id="320"]')).toHaveCount(1);
  const ids=await page.locator('[data-message-id]').evaluateAll(nodes=>nodes.map(node=>Number((node as HTMLElement).dataset.messageId)));
  expect(ids).toEqual(Array.from({length:190},(_,i)=>131+i));
  await expect(input).toHaveValue('Retained draft');
  expect(state.writes.filter(w=>w.path.endsWith('/messages'))).toHaveLength(0);
});

test('World Feed reads 30 roots, appends on demand and preserves composer on read failure', async ({page},info)=>{
  const state=await installWorldFeedFixture(page,info.project.name === "static-export",String(info.project.use.baseURL),'en');
  state.posts=Array.from({length:70},(_,i)=>uiDManualPost({id:`root-${i}`,title:`Root ${i}`,body:'synthetic body '.repeat(25)}));
  await page.goto(feedRoute());
  await expect(page.locator('[data-social-post-row]')).toHaveCount(30);
  await page.screenshot({path:info.outputPath("feed-first-page.png"),animations:"disabled"});
  const input=page.locator('#world-owner-post-title'); await input.fill('Keep this draft');
  let fails=true;
  await page.route('**/manual-social/feed?**',route=>new URL(route.request().url()).searchParams.has('cursor')&&fails
    ? route.fulfill({status:503,json:{detail:'fixture_page_unavailable'}}) : route.fallback());
  await page.getByRole('button',{name:'Load more posts'}).scrollIntoViewIfNeeded();
  await expect(page.getByRole('button',{name:'Retry loading'})).toBeVisible();
  await expect(page.locator('[data-social-post-row]')).toHaveCount(30);
  await expect(input).toHaveValue('Keep this draft');
  fails=false; await page.getByRole('button',{name:'Retry loading'}).click();
  await expect(page.locator('[data-social-post-row]')).toHaveCount(60);
  expect(state.writes.filter(w=>w.path.includes('manual-social'))).toHaveLength(0);
});

test('Saved post plus failed summary is read-only retry, not duplicate publish',async({page},info)=>{
  const state=await installWorldFeedFixture(page,info.project.name === "static-export",String(info.project.use.baseURL),'en');
  await page.goto(feedRoute());
  let fail=true;
  await page.route('**/manual-social/posts/*/summary',route=>fail?route.fulfill({status:503,json:{detail:'fixture_summary_unavailable'}}):route.fallback());
  await page.locator('#world-owner-post-title').fill('Saved root');
  await page.locator('#world-owner-post-body').fill('Saved body');
  await page.getByRole('button',{name:'Publish post',exact:true}).click();
  await expect(page.getByText('Post saved.',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Retry loading'})).toBeVisible();
  fail=false; await page.getByRole('button',{name:'Retry loading'}).click();
  await expect(page.locator('[data-social-post-row]')).toHaveCount(1);
  expect(state.writes.filter(w=>w.path.endsWith('/manual-social/posts'))).toHaveLength(1);
});

test('Offscreen authenticated feed images do not download until near viewport',async({page},info)=>{
  const state=await installWorldFeedFixture(page,info.project.name === "static-export",String(info.project.use.baseURL),'en');
  state.posts=Array.from({length:30},(_,i)=>({...uiDManualPost({id:`image-${i}`,title:`Image ${i}`,body:'Image body'}),
    media:[{id:i,media_type:'image',source_kind:'upload',url:`/api/v1/media/assets/page-${i}/content`,alt_text:`Image ${i}`,width:400,height:600}]}));
  const downloaded:string[]=[];
  await page.route('**/media/assets/page-*/content',route=>{
    downloaded.push(route.request().url());
    return route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jwZkAAAAASUVORK5CYII=','base64')});
  });
  await page.goto(feedRoute());
  await expect(page.locator('[data-social-post-row]')).toHaveCount(30);
  expect(downloaded.some(u=>u.includes('page-29/'))).toBe(false);
  await page.locator('[data-social-post-row="image-29"]').scrollIntoViewIfNeeded();
  await expect.poll(()=>downloaded.some(u=>u.includes('page-29/'))).toBe(true);
  expect(state.providerCalls).toHaveLength(0);
});
