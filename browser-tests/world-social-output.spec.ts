import {expect,test} from "@playwright/test";
import {readFileSync,writeFileSync} from "node:fs";
import {FEED_WORLD, OTHER_FEED_WORLD, feedRoute, profileRoute} from "./world-feed-fixture";
import {installSocialChatFixture, detailRoute, chatRoute, SYNTHETIC_REPLY} from "./world-social-chat-fixture";

for(const language of ["ko","en"] as const){
  test(`selected reply composer and retry preserve direct parent/key (${language})`,async({page},info)=>{
    const state=await installSocialChatFixture(page,info.project.name==="static-export",String(info.project.use.baseURL),language);
    state.replyFailures=1;
    await page.goto(detailRoute());
    const form=page.locator('[data-world-social-surface="detail"] form');
    await expect(form).toBeVisible();
    const field=form.locator("textarea"),send=form.locator('button[type="submit"]');
    await expect(field).toHaveValue("");await expect(field).not.toHaveAttribute("placeholder",/./);
    await expect(field).toHaveAccessibleName(language==="ko"?"답글":"Reply");
    await expect(field).toHaveAttribute("maxlength","1000");await expect(send).toHaveText("");await expect(send).toBeDisabled();
    await expect(page.locator('[data-social-post-row="synthetic-root"]')).toHaveCount(0);
    await expect(page.locator('[data-social-post-row="synthetic-reply"]')).toBeVisible();
    await field.fill("Synthetic nested answer");await send.click();
    await expect(field).toHaveValue("Synthetic nested answer");
    await expect(page.locator('[data-world-social-surface="detail"] [role="alert"]')).toBeVisible();
    await send.click();await expect(field).toHaveValue("");
    const writes=state.writes.filter(w=>w.path.endsWith("/replies"));
    expect(writes).toHaveLength(2);expect(writes[0].path).toContain(`/${SYNTHETIC_REPLY}/replies`);expect(writes[0].key).toBe(writes[1].key);
    expect(state.posts.at(-1)!.reply_to_post_id).toBe(SYNTHETIC_REPLY);
    await page.reload();await expect(page.getByText("Synthetic nested answer",{exact:true})).toBeVisible();
    expect(state.base.providerCalls).toEqual([]);
  });

  test(`canonical heart and profile reload reflect viewer not aggregate (${language})`,async({page},info)=>{
    const state=await installSocialChatFixture(page,info.project.name==="static-export",String(info.project.use.baseURL),language);
    state.posts[1].like_count=7;state.delay=450;
    await page.goto(detailRoute());const row=page.locator('[data-social-post-row="synthetic-reply"]');
    const heart=row.getByRole("button",{name:language==="ko"?/좋아요/:/Like/});
    await expect(heart).toHaveAttribute("aria-pressed","false");await heart.click();
    await expect(heart).toBeDisabled();await expect.poll(()=>state.writes.filter(w=>w.path.endsWith("/like")).length).toBe(1);
    await expect(row.getByRole("button",{name:language==="ko"?/좋아요/:/Like/})).toHaveAttribute("aria-pressed","true");
    await expect(page).toHaveURL(new RegExp(`${SYNTHETIC_REPLY}/?$`));
    await page.reload();await expect(row.getByRole("button",{name:language==="ko"?/좋아요/:/Like/})).toHaveAttribute("aria-pressed","true");
    await page.goto(profileRoute());await expect(page.locator('[data-world-character-surface="profile"]')).toBeVisible();
    await page.getByRole("tab",{name:language==="ko"?"좋아요":"Like",exact:true}).click();
    await expect(page.locator('[data-social-post-row="synthetic-reply"]')).toBeVisible();
    expect(state.writes).toHaveLength(1);expect(state.base.providerCalls).toEqual([]);
  });

  test(`Chat compact surface keeps one message scroll and Dialog focus (${language})`,async({page},info)=>{
    const state=await installSocialChatFixture(page,info.project.name==="static-export",String(info.project.use.baseURL),language);
    state.thread.messages=Array.from({length:100},(_,i)=>({...state.thread.messages[i%2],id:i+1,content:`Synthetic long message ${i+1}`}));
    state.thread.evidence_summaries=[];
    await page.goto(chatRoute());const surface=page.locator('[data-world-chat-surface="thread"]');await expect(surface).toBeVisible();
    const trigger=surface.getByRole("button",{name:language==="ko"?"기억과 진단 보기":"Open memory and diagnostics"});
    await expect(trigger).toHaveAttribute("aria-expanded","false");
    const draft=surface.locator("form textarea");await draft.fill("Synthetic unsent draft");
    await trigger.click();const dialog=page.getByRole("dialog");await expect(dialog).toBeVisible();
    await page.keyboard.press("Escape");await expect(dialog).toHaveCount(0);await expect(trigger).toBeFocused();await expect(draft).toHaveValue("Synthetic unsent draft");
    expect(state.writes).toEqual([]);
    const layout=await surface.evaluate(element=>{
      const form=element.querySelector("form")!,list=element.querySelector("ol")!,pane=list.parentElement!;
      return {surface:element.getBoundingClientRect().toJSON(),form:form.getBoundingClientRect().toJSON(),pane:pane.getBoundingClientRect().toJSON(),paneOverflow:getComputedStyle(pane).overflowY,scroll:pane.scrollHeight,client:pane.clientHeight};
    });
    expect(layout.paneOverflow).toBe("auto");expect(layout.scroll).toBeGreaterThan(layout.client);expect(layout.form.bottom).toBeLessThanOrEqual(layout.surface.bottom+1);
    await surface.locator("form").getByRole("button",{name:language==="ko"?"메시지 보내기":"Send message",exact:true}).click();
    await expect(page.getByText("Synthetic complete answer",{exact:true})).toBeVisible();
    expect(state.writes.filter(w=>w.path.endsWith("/messages"))).toHaveLength(1);
    await expect(draft).toHaveValue("");
  });

  test(`Chat twenty and one hundred reads keep explicit null contract (${language})`,async({page},info)=>{
    const state=await installSocialChatFixture(page,info.project.name==="static-export",String(info.project.use.baseURL),language);
    await page.goto(`/worlds/${FEED_WORLD}/chat`);await expect(page.locator('[data-world-chat-surface="list"] ol li')).toHaveCount(20);
    await expect(page.getByText(/WORLD CHAT|20\/5/)).toHaveCount(0);
    state.threadCount=100;await page.reload();await expect(page.locator('[data-world-chat-surface="list"] ol li')).toHaveCount(100);
    state.maxThreads=undefined;await page.reload();await expect(page.locator('[data-product-surface="world-app"] [role="alert"]')).toBeVisible();
    state.maxThreads=5;await page.reload();await expect(page.getByText(language==="ko"?"대화 제한 정책 업데이트가 필요해요":"The conversation limit policy needs an update",{exact:true})).toBeVisible();
    expect(state.writes).toEqual([]);
  });

  for(const width of [360,390,436,480,768,960,1440]) test(`reply Chat geometry ${width}px (${language})`,async({page},info)=>{
    await installSocialChatFixture(page,info.project.name==="static-export",String(info.project.use.baseURL),language);
    await page.setViewportSize({width,height:900});const measurements=[];
    for(const route of [detailRoute(),chatRoute(),feedRoute(),profileRoute()]){
      await page.goto(route);await expect(page.locator('[data-world-social-surface], [data-world-chat-surface="thread"], [data-world-character-surface="profile"]').first()).toBeVisible();
      if(width===436) await page.screenshot({path:info.outputPath(`${route.split("/")[3]}-${language}-436.png`),animations:"disabled"});
      for(const zoom of [1,2]){
        await page.evaluate(z=>{document.documentElement.style.zoom=String(z);},zoom);
        const bounds=await page.evaluate(()=>({client:document.documentElement.clientWidth,width:document.documentElement.scrollWidth,buttons:[...document.querySelectorAll<HTMLButtonElement>('button[type="submit"]')].map(el=>({label:el.getAttribute("aria-label"),text:el.textContent,rect:el.getBoundingClientRect().toJSON()}))}));
        expect(bounds.width).toBeLessThanOrEqual(bounds.client+2);
        expect(bounds.buttons.every(button=>!button.text?.trim())).toBe(true);
        measurements.push({route,zoom,...bounds});
      }
      await page.evaluate(()=>{document.documentElement.style.zoom="1";});
    }
    writeFileSync(info.outputPath("geometry.json"),JSON.stringify(measurements,null,2));
  });
}

test("forged v2 and unavailable parent stay safe without writes",async({page},info)=>{
  const state=await installSocialChatFixture(page,info.project.name==="static-export",String(info.project.use.baseURL));state.hiddenParent=true;
  await page.goto(detailRoute());await expect(page.getByText("부모 게시글을 볼 수 없습니다.",{exact:true})).toBeVisible();
  state.corrupt=true;await page.reload();await expect(page.getByText("World 경계를 확인했어요",{exact:true})).toBeVisible();
  await expect(page.locator('[data-social-post-row="synthetic-reply"]')).toHaveCount(0);expect(state.writes).toEqual([]);
});

test("locale refresh preserves failed reply text, focus, and idempotency key",async({page},info)=>{
  const state=await installSocialChatFixture(page,info.project.name==="static-export",String(info.project.use.baseURL));state.replyFailures=1;
  await page.goto(detailRoute());const form=page.locator('[data-world-social-surface="detail"] form'),field=form.locator("textarea"),send=form.locator('button[type="submit"]');
  await field.fill("한글 원문을 그대로 보존합니다.");await send.click();await expect(form.locator("textarea")).toHaveValue("한글 원문을 그대로 보존합니다.");
  await expect(page.locator('[data-world-social-surface="detail"] [role="alert"]')).toBeVisible();await field.focus();
  state.base.language="en";await page.evaluate(()=>window.dispatchEvent(new Event("angmoo:auth-changed")));
  await expect(field).toHaveAccessibleName("Reply");await expect(field).toBeFocused();await expect(field).toHaveValue("한글 원문을 그대로 보존합니다.");
  await send.click();await expect(field).toHaveValue("");const writes=state.writes.filter(w=>w.path.endsWith("/replies"));expect(writes).toHaveLength(2);expect(writes[0].key).toBe(writes[1].key);
  expect(writes.every(w=>w.data.body==="한글 원문을 그대로 보존합니다.")).toBe(true);expect(state.base.providerCalls).toEqual([]);
});

test("profile tab change clears the completed reaction lock in its new scope",async({page},info)=>{
  const state=await installSocialChatFixture(page,info.project.name==="static-export",String(info.project.use.baseURL));
  state.posts[0].author_world_character_id="synthetic-responder";state.delay=600;
  await page.goto(`/worlds/${FEED_WORLD}/characters/synthetic-responder`);
  const row=page.locator('[data-social-post-row="synthetic-root"]');
  await row.getByRole("button",{name:/좋아요/}).click();
  await page.getByRole("tab",{name:"좋아요",exact:true}).click();
  await expect.poll(()=>state.posts[0].viewer_like_state).toBe("liked");
  await expect(row).toBeVisible();
  await expect(row.getByRole("button",{name:/좋아요/})).toBeEnabled();
  await expect(row.getByRole("button",{name:/좋아요/})).toHaveAttribute("aria-pressed","true");
  expect(state.writes).toHaveLength(1);
  await row.getByRole("button",{name:/좋아요/}).click();
  await expect.poll(()=>state.posts[0].viewer_like_state).toBe("not_liked");
  await expect(row).toHaveCount(0);
  expect(state.writes).toHaveLength(2);expect(state.base.providerCalls).toEqual([]);
});

test("late reaction response cannot replace the newly selected parent",async({page},info)=>{
  const state=await installSocialChatFixture(page,info.project.name==="static-export",String(info.project.use.baseURL));state.delay=800;
  await page.goto(detailRoute());await page.locator('[data-social-post-row="synthetic-reply"]').getByRole("button",{name:/좋아요/}).click();
  await page.getByRole("link",{name:"부모 게시글 보기",exact:true}).first().click();
  const parent=page.locator('[data-social-post-row="synthetic-root"]');await expect(parent).toBeVisible();
  await expect(parent.getByRole("button",{name:/좋아요/})).toHaveAttribute("aria-pressed","false");
  await expect.poll(()=>state.posts[1].viewer_like_state).toBe("liked");
  await expect(parent.getByRole("button",{name:/좋아요/})).toHaveAttribute("aria-pressed","false");expect(state.writes).toHaveLength(1);
});

for(const language of ["ko","en"] as const) test(`Chat IME, newline and selected photo survive locale refresh (${language})`,async({page},info)=>{
  const state=await installSocialChatFixture(page,info.project.name==="static-export",String(info.project.use.baseURL),language);
  await page.goto(chatRoute());const surface=page.locator('[data-world-chat-surface="thread"]'),form=surface.locator("form"),field=form.locator("textarea");
  await field.fill("한글 원문");await field.press("Shift+Enter");await expect(field).toHaveValue("한글 원문\n");
  await field.dispatchEvent("keydown",{key:"Enter",code:"Enter",isComposing:true,bubbles:true});
  expect(state.writes.filter(w=>w.path.endsWith("/messages"))).toHaveLength(0);
  const photo=form.getByRole("button",{name:language==="ko"?"사진 첨부":"Attach photo",exact:true});
  const chooser=page.waitForEvent("filechooser");await photo.click();
  await (await chooser).setFiles({name:"synthetic-chat.webp",mimeType:"image/webp",buffer:readFileSync("../backend/tests/image_integration/fixtures/pixels.webp")});
  await expect(form.locator("img")).toBeVisible();await field.focus();
  const selectedModel=await form.locator("select").inputValue();
  const opposite=language==="ko"?"en":"ko";state.base.language=opposite;
  await page.evaluate(()=>window.dispatchEvent(new Event("angmoo:auth-changed")));
  const send=form.getByRole("button",{name:opposite==="ko"?"메시지 보내기":"Send message",exact:true});
  await expect(send).toBeEnabled();await expect(field).toBeFocused();await expect(field).toHaveValue("한글 원문\n");
  await expect(form.locator("img")).toBeVisible();await expect(form.locator("select")).toHaveValue(selectedModel);
  // Compare the same neutral pointer state. The shared secondary button's
  // intentional hover transform must not be compared with an idle Send button.
  await page.mouse.move(0,0);
  await expect.poll(async()=>{
    const photoBox=await form.getByRole("button",{name:opposite==="ko"?"사진 첨부":"Attach photo",exact:true}).boundingBox(),sendBox=await send.boundingBox();
    return photoBox!.y===sendBox!.y;
  }).toBe(true);
  const left=await form.getByRole("button",{name:opposite==="ko"?"사진 첨부":"Attach photo",exact:true}).boundingBox(),right=await send.boundingBox();
  expect(left!.width).toBe(48);expect(right!.width).toBe(48);expect(left!.y).toBe(right!.y);expect(left!.x+left!.width).toBeLessThan(right!.x);
  await field.press("Enter");await expect(page.getByText("Synthetic complete answer",{exact:true})).toBeVisible();
  const writes=state.writes.filter(w=>w.path.endsWith("/messages"));expect(writes).toHaveLength(1);expect(writes[0].data.content).toBe("한글 원문");expect(writes[0].data.attachment_asset_id).toBe("draft-1");
  expect(state.base.providerCalls).toEqual([]);
});

for(const language of ["ko","en"] as const) test(`only Home retains World shell across both World routes (${language})`,async({page},info)=>{
  const state=await installSocialChatFixture(page,info.project.name==="static-export",String(info.project.use.baseURL),language);
  for(const world of [FEED_WORLD,OTHER_FEED_WORLD]){
    await page.goto(`/worlds/${world}`);const app=page.locator('[data-product-surface="world-app"]');await expect(app).toBeVisible();
    await expect(app.getByText("World App",{exact:true})).toBeVisible();
    for(const section of ["feed","chat","characters","relationships"]){
      await page.goto(`/worlds/${world}/${section}`);await expect(app).toBeVisible();
      await expect(app.getByText("World App",{exact:true})).toHaveCount(0);
      await expect(app.getByText("WORLD CHARACTERS",{exact:true})).toHaveCount(0);
      await expect(app.locator(`a[href="/worlds/${world}"]`).first()).toBeVisible();
      if(section==="characters") await expect(app.locator('[data-world-character-surface="list"]')).toBeVisible();
    }
    await app.locator(`a[href="/worlds/${world}"]`).first().click();
    await expect(page).toHaveURL(new RegExp(`/worlds/${world}/?$`));await expect(app.getByText("World App",{exact:true})).toBeVisible();
  }
  expect(state.writes).toEqual([]);expect(state.base.providerCalls).toEqual([]);
});
