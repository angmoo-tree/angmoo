import type { Page, Route } from "@playwright/test";
import { FEED_WORLD, ownerId, installWorldFeedFixture } from "./world-feed-fixture";
import { uiDManualPost } from "./continuity-next-fixture";

export const SYNTHETIC_ROOT = "synthetic-root";
export const SYNTHETIC_REPLY = "synthetic-reply";
export const SYNTHETIC_THREAD = "synthetic-chat";
export const detailRoute = (id = SYNTHETIC_REPLY) => `/worlds/${FEED_WORLD}/posts/${id}`;
export const chatRoute = (id = SYNTHETIC_THREAD) => `/worlds/${FEED_WORLD}/chat/${id}`;

export async function installSocialChatFixture(page: Page, isStatic: boolean, baseURL: string, language: "ko" | "en" = "ko") {
  const base = await installWorldFeedFixture(page, isStatic, baseURL, language);
  const post = (id: string, parent: string | null = null) => ({...uiDManualPost({id, replyToPostId: parent, title: parent ? "" : "Synthetic root title", body: `Synthetic content ${id}`, worldId: FEED_WORLD}),
    author_avatar_url: "/api/v1/media/assets/synthetic-avatar/content", thread_root_post_id: SYNTHETIC_ROOT,
    viewer_like_state: "not_liked" as "liked" | "not_liked" | "unavailable", can_owner_like: true,
    reaction_world_id: FEED_WORLD, reaction_owner_world_character_id: ownerId(), media: [] as Record<string, unknown>[]});
  const role = (id: string, controlled = false) => ({world_character_id: id, character_id: `character-${id}`, display_name: controlled ? "Synthetic World User" : "Synthetic Responder", handle: controlled ? "world_user" : "responder", avatar_url: "/api/v1/media/assets/synthetic-avatar/content", banner_url: null, role_key: null, control_mode: controlled ? "owner_controlled" : "autonomous", profile_capability: "available"});
  const message = (id: number, own = false) => ({id, thread_id: SYNTHETIC_THREAD, role: own ? "user" : "assistant", status: "ok", sender_user_id: own ? "local-owner" : null, sender_character_id: own ? null : "character-synthetic-responder", content: `Synthetic ${own ? "user" : "assistant"} message ${id}`, created_at: "2026-10-05T01:00:00Z", attachment: null});
  const thread = {id: SYNTHETIC_THREAD, world_id: FEED_WORLD, requester: role(ownerId(),true), responding: role("synthetic-responder"), selected_model: "gemini-3.1-flash-lite", selected_thinking_level: "medium", default_model: "gemini-3.1-flash-lite", default_thinking_level: "medium", model_binding_mode: "default", last_message_at: null, created_at: "2026-10-05T01:00:00Z", latest_message: null,
    messages: [message(1,true),message(2)], evidence_summaries: [{request_id:"synthetic-evidence",assistant_message_id:2,capability:"available",count:2}]};
  const state = {base, posts: [post(SYNTHETIC_ROOT),post(SYNTHETIC_REPLY,SYNTHETIC_ROOT),post("synthetic-leaf",SYNTHETIC_REPLY)],
    writes: [] as {path:string; method:string; key:string|undefined; data:Record<string,unknown>}[], reads: [] as string[], replyFailures:0, likeFailures:0, delay:0, corrupt:false, hiddenParent:false,
    thread, threadCount:20, maxThreads:null as number|null|undefined, chatFailure:false, modelFailure:false, chatEventDelay:0};
  const reply = (route:Route,data:unknown,status=200) => route.fulfill({status,json:data});
  const readPost = (value:ReturnType<typeof post>) => ({...value, reply_count: descendants(value.id).length});
  const descendants = (id:string):ReturnType<typeof post>[] => state.posts.filter(item => item.reply_to_post_id===id).flatMap(item=>[item,...descendants(item.id)]);
  let accepted: Record<string,unknown>|null = null;
  const handler = async(route:Route) => {
    const request=route.request(), url=new URL(request.url()), path=url.pathname.replace(/^\/api\/(backend|v1)/,""), method=request.method();
    if (method==="GET") state.reads.push(path);
    else if (path.includes("manual-social") || path.includes("/chat/")) state.writes.push({path,method,key:request.headers()["idempotency-key"],data:request.postData()?request.postDataJSON():{}});
    if (path===`/worlds/${FEED_WORLD}/manual-social/feed`) return reply(route,{schema_version:"owner-manual-social-v1",world_id:FEED_WORLD,owner_world_character_id:ownerId(),items:state.posts.map(readPost)});
    const like=path.match(/\/manual-social\/posts\/([^/]+)\/like$/);
    if(like){
      if(state.likeFailures-- >0)return reply(route,{detail:"sqlite_busy_retry_exhausted"},503);
      const value=state.posts.find(p=>p.id===like[1])!;
      if(state.delay)await new Promise(resolve=>setTimeout(resolve,state.delay));
      value.viewer_like_state=method==="PUT"?"liked":"not_liked"; value.like_count=method==="PUT"?1:0;
      return reply(route,{world_id:FEED_WORLD,post_id:value.id,owner_world_character_id:ownerId(),viewer_like_state:value.viewer_like_state,like_count:value.like_count,can_owner_like:true});
    }
    const detail=path.match(/\/manual-social\/posts\/([^/]+)$/);
    if(detail){
      const selected=state.posts.find(p=>p.id===detail[1]); if(!selected)return reply(route,{detail:"post_not_in_world"},404);
      const children=descendants(selected.id), offset=Number(url.searchParams.get("offset")??0);
      const parents=[...new Set([selected,...children.slice(offset,offset+50)].map(p=>p.reply_to_post_id).filter(Boolean))].map(id=>({post_id:id,state:state.hiddenParent&&id===SYNTHETIC_ROOT?"unavailable":"available"}));
      return reply(route,{schema_version:"owner-manual-social-thread-v2",world_id:state.corrupt?"forged-world":FEED_WORLD,owner_world_character_id:ownerId(),root_post_id:SYNTHETIC_ROOT,
        selected_post:readPost(selected),parent:parents.find(p=>p.post_id===selected.reply_to_post_id)??null,parent_references:parents,replies:children.slice(offset,offset+50).map(readPost),page_offset:offset,next_offset:offset+50<children.length?offset+50:null});
    }
    const nested=path.match(/\/manual-social\/posts\/([^/]+)\/replies$/);
    if(nested&&method==="POST"){
      if(state.replyFailures-- >0)return reply(route,{detail:"sqlite_busy_retry_exhausted"},503);
      const data=request.postDataJSON(), created={...post(`synthetic-created-${state.posts.length}`,nested[1]), body:data.body, author_world_character_id:ownerId(),author_name:"Synthetic World User",can_owner_reply:false,can_owner_like:false};
      state.posts.push(created);
      return reply(route,{schema_version:"owner-manual-social-v1",operation:"reply",post:created,replayed:false,delivery:{provider_call_count:0,public_reaction_required:false,inbox_candidate_id:"synthetic-inbox",inbox_status:"pending"}},201);
    }
    const profile=path.match(/\/world-characters\/([^/]+)\/social-profile$/);
    if(profile){ const tab=url.searchParams.get("tab"), rows=tab==="likes"?state.posts.filter(p=>p.viewer_like_state==="liked"):state.posts.filter(p=>p.author_world_character_id===profile[1]&&(tab==="replies"?Boolean(p.reply_to_post_id):!p.reply_to_post_id));
      return reply(route,{schema_version:"world-character-social-profile-v1",world_id:FEED_WORLD,world_character_id:profile[1],character_id:`character-${profile[1]}`,tab,counts:{post_count:1,reply_count:2,liked_post_count:state.posts.filter(p=>p.viewer_like_state==="liked").length,received_like_count:1},items:rows.map(p=>({...readPost(p),author_character_id:`character-${p.author_world_character_id}`,mentioned_characters:[],target_post_id:null,deleted_at:null})),next_cursor:null}); }
    if(path===`/worlds/${FEED_WORLD}/chat/threads`){ const payload={items:Array.from({length:state.threadCount},(_,i)=>({...thread,id:i?`synthetic-chat-${i}`:SYNTHETIC_THREAD,messages:[],evidence_summaries:[]})),ambiguous_legacy_count:0,max_threads:state.maxThreads};return reply(route,payload); }
    if(path===`/worlds/${FEED_WORLD}/chat/threads/${SYNTHETIC_THREAD}`)return reply(route,thread);
    if(path.endsWith("/requests/latest"))return reply(route,{response_request:null});
    if(path.endsWith("/messages")&&method==="POST"){
      if(state.chatFailure)return reply(route,{detail:"sqlite_busy_retry_exhausted"},503);
      const data=request.postDataJSON(), user={...message(thread.messages.length+1,true),content:data.content};thread.messages.push(user);
      accepted={protocol_version:"chat-generation-stream.v1",request_id:"synthetic-request",request_scope_hash:"a".repeat(64),generation_id:"synthetic-generation",attempt_number:1,response_slot_id:"synthetic-slot",state:"accepted",route:null,retryable:false,failure_class:null,last_accepted_sequence:-1,user_message:user,assistant_message:null,response_metadata:{}};
      return reply(route,{outcome:"accepted",user_message:user,response_request:accepted});
    }
    if(path.endsWith("/events")){
      if(state.chatEventDelay)await new Promise(resolve=>setTimeout(resolve,state.chatEventDelay));
      thread.messages.push({...message(thread.messages.length+1),content:"Synthetic complete answer"});
      const records=[{type:"accepted",payload:{}},{type:"delta",payload:{text:"Synthetic complete answer"}},{type:"completed",payload:{}}].map((event,i)=>({...accepted,...event,sequence:i}));
      return route.fulfill({contentType:"application/x-ndjson",body:records.map(r=>JSON.stringify(r)).join("\n")+"\n"});
    }
    if(path.endsWith("/model")&&method==="PATCH"){
      if(state.modelFailure)return reply(route,{detail:"model_update_failed"},503);
      const data=request.postDataJSON();thread.model_binding_mode=data.mode;
      thread.selected_model=data.mode==="default"?thread.default_model:data.selected_model;thread.selected_thinking_level=data.mode==="default"?thread.default_thinking_level:data.selected_thinking_level??"high";
      return reply(route,thread);
    }
    if(path.includes("diagnostics"))return reply(route,{schema_version:"chat-retrieval-diagnostics.v1",capability:"disabled",enabled:false,requests:[],count:0});
    if(path.match(/^\/media\/assets\/[^/]+\/preflight$/)&&method==="GET")return reply(route,{allowed:true,reason:null});
    return route.fallback();
  };
  await page.route("**/api/backend/**",handler);await page.route("http://127.0.0.1:8080/api/v1/**",handler);
  return state;
}
