// Test-only HTTP transport: chunked NDJSON shares the page origin. Unhandled
// API requests return 404; no request is forwarded to the user's real backend.
import { createServer, request as proxyRequest } from "node:http";
const WORLD = "019f0000-0000-7000-8000-000000000001";
const SECOND = "019f0000-0000-7000-8000-000000000002";
const DEFAULT = "019f0000-0000-7000-8000-000000000003";
let language = "ko", state = "accepted", sequence = -1, receipt = null, requestCount = 0, deletes = 0;
let receiptUnavailable=false, loseNextDelete=false, retryCount=0, deleteKeys=[],idle=false,fastNext=false,worldUnavailable=false;
let catalogVariants=false;
const listeners = new Set();
const role = {world_character_id:"wc-bram",character_id:"bram",display_name:"Bram",handle:"bram",avatar_url:null,banner_url:null,role_key:null,control_mode:"autonomous",profile_capability:"available"};
const user = {id:41,thread_id:"thread-phase",role:"user",content:"Look at this photo.",attachment:{asset_id:"photo",url:"/api/v1/media/assets/photo/content",analysis_state:"pending"},model:null,status:"ok",error_code:null,created_at:"2026-10-12T00:00:00Z"};
const reply = {id:42,thread_id:"thread-phase",role:"assistant",content:"Fixture reply.",attachment:null,model:"gemini-3.1-flash-lite",status:"ok",error_code:null,created_at:user.created_at};
const generation = () => ({protocol_version:"chat-generation-stream.v1",request_id:"phase-request",request_scope_hash:"a".repeat(64),generation_id:"phase-generation",attempt_number:1,response_slot_id:"phase-slot",state,route:null,retryable:state==="failed",failure_class:state==="failed"?"image_interpretation_unavailable":null,last_accepted_sequence:sequence,user_message:user,assistant_message:state==="committed"?reply:null,response_metadata:{},image_analysis_state:state==="accepted"?"waiting":state==="failed"?"failed":"recognized",can_retry_without_image:state==="failed"});
const thread = () => ({id:user.thread_id,world_id:WORLD,requester:{...role,world_character_id:"wc-user",display_name:"User",handle:"user",control_mode:"owner_controlled"},responding:role,selected_model:"gemini-3.1-flash-lite",selected_thinking_level:"high",default_model:"gemini-3.1-flash-lite",default_thinking_level:"high",model_binding_mode:"default",last_message_at:user.created_at,created_at:user.created_at,latest_message:idle?null:state==="committed"?reply:user,messages:idle?[]:state==="committed"?[user,reply]:[user],evidence_summaries:[]});
const worlds = [WORLD,SECOND,DEFAULT].map((world_id,index)=>({world_id,name:index===2?"SNS":`Fixture ${index+1}`,tagline:"Lifecycle test",status:index===1?"draft":"published",visibility:"private",readiness_status:index===1?"not_ready":"publish_ready",membership_role:"owner",launchable:index!==1,launch_block_reason:index===1?"world_not_published":null,updated_at:user.created_at,banner_media_id:null,icon_media_id:null,banner_alt_text:"",can_delete:index!==2,is_default_space:index===2}));
function json(response,value,status=200) { response.writeHead(status,{"Content-Type":"application/json","Cache-Control":"no-store"}); response.end(JSON.stringify(value)); }
async function handle(request,response, upstream) {
  const url=new URL(request.url,"http://test"); const path=url.pathname.replace(/^\/api\/(backend|v1)/,"");
  if(url.pathname.startsWith("/__phase/")) {
    const action=url.pathname.slice(9);
    if(action==="reset") { for(const stream of listeners) stream.end(); listeners.clear(); language=url.searchParams.get("language")??"ko";state="accepted";sequence=-1;receipt=null;requestCount=deletes=retryCount=0;receiptUnavailable=loseNextDelete=idle=fastNext=worldUnavailable=catalogVariants=false;deleteKeys=[];user.content="Look at this photo.";user.attachment={asset_id:"photo",url:"/api/v1/media/assets/photo/content",analysis_state:"pending"};return json(response,{}); }
    if(action==="catalog"){catalogVariants=true;return json(response,{});}
    if(action==="world-unavailable"){worldUnavailable=true;return json(response,{});}
    if(action==="idle"){idle=fastNext=true;return json(response,{});}
    if(action==="audit") return json(response,{requestCount,deletes,retryCount,deleteKeys,streams:listeners.size});
    if(action==="lose-delete") {loseNextDelete=true;return json(response,{});}
    if(action==="receipt-unavailable") {receiptUnavailable=url.searchParams.get("enabled")!=="false";return json(response,{});}
    if(action==="delete-failed") {receipt={...receipt,state:"failed",can_retry:true};return json(response,{});}
    if(action==="world-delete") {receipt={request_id:"deletion-one",world_id:WORLD,state:"accepted",accepted_at:user.created_at,completed_at:null,can_retry:false};for(const stream of listeners)stream.end();listeners.clear();return json(response,{});}
    if(action==="delete-complete") { receipt={...receipt,state:"completed",completed_at:user.created_at};return json(response,{}); }
    if(action==="accepted"||action==="delta"||action==="completed"||action==="failed") {
      sequence++; if(action==="completed") state="committed";if(action==="failed") state="failed";
      const event={protocol_version:"chat-generation-stream.v1",request_id:"phase-request",request_scope_hash:"a".repeat(64),generation_id:"phase-generation",attempt_number:1,sequence,type:action,payload:action==="delta"?{text:reply.content}:action==="failed"?{failure_class:"image_interpretation_unavailable",retryable:true}:{}};
      for(const stream of listeners) { stream.write(JSON.stringify(event)+"\n");if(action==="completed"||action==="failed") stream.end(); }
      if(action==="completed"||action==="failed") listeners.clear();return json(response,{});
    }
    if(action==="disconnect") { for(const stream of listeners) stream.end();listeners.clear();return json(response,{}); }
    return json(response,{},404);
  }
  if(url.pathname.startsWith("/api/backend/")||url.pathname.startsWith("/api/v1/")) {
    if(path==="/auth/me") return json(response,{id:"local-owner",email:null,display_name:"Local Owner",profile_setup_completed:true,ui_language:language,ui_preference_revision:0,feed_content_filter:"all",is_admin:true});
    if(path==="/runtime/status") return json(response,{schema_version:"local-runtime-status-v1",installation_state:"ready"});
    if(path==="/auth/local/environment") return json(response,{installation_id:"phase-installation",preferred_language:language==="ko"?"ko-KR":"en-US",memory_search_locale:language==="ko"?"ko-KR":"en-US",timezone:"Asia/Seoul",environment_revision:1,timezone_revision:1,confirmed_at:user.created_at,synchronization:"active_owner",lease_expires_at:"2099-01-01T00:00:00Z",lease_token:"phase-test-only"});
    if(path===`/worlds/${WORLD}`&&request.method==="GET")return receipt?json(response,{detail:"world_deleting"},409):json(response,{detail:"synthetic_unavailable"},worldUnavailable?503:404);
    if(receipt&&path.startsWith(`/worlds/${WORLD}/chat`))return json(response,{detail:receipt.state==="completed"?"world_deleted":"world_deleting"},receipt.state==="completed"?410:409);
    if(path.endsWith("/events")) { requestCount++;response.writeHead(200,{"Content-Type":"application/x-ndjson","Cache-Control":"no-store"});response.flushHeaders();listeners.add(response);response.on("close",()=>listeners.delete(response));if(fastNext){fastNext=false;for(const [sequence,type]of[[0,"accepted"],[1,"delta"],[2,"completed"]])response.write(JSON.stringify({...generation(),sequence,type,payload:type==="delta"?{text:reply.content}:{}})+"\n");state="committed";response.end();listeners.delete(response);}return; }
    if(path.endsWith("/requests/latest")) return json(response,{response_request:idle?null:generation()});
    if(path.endsWith("/requests/phase-request")) return json(response,generation());
    if(path.endsWith("/threads/thread-phase")) return json(response,thread());
    if(path.endsWith("/threads/thread-phase/messages")&&request.method==="POST"){let body="";for await(const part of request)body+=part;user.content=JSON.parse(body).content;user.attachment=null;idle=false;return json(response,{outcome:"accepted",user_message:user,response_request:generation()},202);}
    if(path==="/worlds/mine") {
      const variants=catalogVariants?[{...worlds[0],visibility:"public"},worlds[1],worlds[2],
        {...worlds[0],world_id:"019f0000-0000-7000-8000-000000000004",name:"Editor World",membership_role:"editor",can_delete:false},
        {...worlds[0],world_id:"019f0000-0000-7000-8000-000000000005",name:"Unknown capability",can_delete:undefined},
        {...worlds[0],world_id:"019f0000-0000-7000-8000-000000000006",name:"Stale World",readiness_status:"stale",launchable:false},
        {...worlds[0],world_id:"019f0000-0000-7000-8000-000000000007",name:"Archived World",status:"archived",launchable:false}]:worlds;
      return json(response,{schema_version:"local-world-surface-v1",surface:url.searchParams.get("surface"),items:variants.filter(world=>!receipt||world.world_id!==receipt.world_id),next_cursor:null});
    }
    if(path===`/worlds/mine/${WORLD}`||path===`/worlds/${WORLD}/app`) return json(response,{schema_version:"local-world-app-v1",surface:"world_app",world:worlds[0]});
    if(path===`/worlds/${WORLD}/owner-character`) return json(response,{schema_version:"owner-controlled-world-character-v1",world_id:WORLD,world_character_id:"wc-user",character_id:"user",control_mode:"owner_controlled",status:"active",autonomous_enabled:false,version:1,profile:{display_name:"User",avatar_url:"",intro:"",background:"",interests:[],role_key:null}});
    if(path.endsWith("/deletion-preview")) return json(response,{world_id:WORLD,stored_name:"Fixture 1",row_version:7,can_delete:true,is_default_space:false,export_available:catalogVariants});
    if(path===`/worlds/${WORLD}`&&request.method==="DELETE") {let body="";for await(const part of request) body+=part; const value=JSON.parse(body);if(value.confirmed_name!=="Fixture 1"||value.expected_row_version!==7||value.consent!==true)return json(response,{detail:"confirmation_name_mismatch"},422);deleteKeys.push(value.idempotency_key);if(!receipt)deletes++;receipt??={request_id:"deletion-one",world_id:WORLD,state:"accepted",accepted_at:user.created_at,completed_at:null,can_retry:false};if(loseNextDelete){loseNextDelete=false;return json(response,{detail:"synthetic_acknowledgement_lost"},503);}return json(response,receipt,202);}
    if(path==="/world-deletions") return json(response,receipt&&receipt.state!=="completed"?[receipt]:[]);
    if(path==="/world-deletions/deletion-one") return receiptUnavailable?json(response,{detail:"synthetic_unavailable"},503):json(response,receipt);
    if(path==="/world-deletions/deletion-one/retry"&&request.method==="POST"){retryCount++;receipt={...receipt,state:"accepted",can_retry:false};return json(response,receipt,202);}
    if(path==="/media/assets/photo/content") {response.writeHead(200,{"Content-Type":"image/png"});response.end(Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=","base64"));return;}
    if(path==="/agents") return json(response,[]);
    return json(response,{detail:"test_fixture_unavailable"},404);
  }
  const forwarded=proxyRequest(`http://127.0.0.1:${upstream}${request.url}`,{method:request.method,headers:request.headers}, result=>{response.writeHead(result.statusCode,result.headers);result.pipe(response);});
  forwarded.on("error",()=>json(response,{detail:"test_frontend_not_ready"},503));request.pipe(forwarded);
}
createServer((req,res)=>void handle(req,res,3415)).listen(3417,"127.0.0.1");
createServer((req,res)=>void handle(req,res,3416)).listen(3418,"127.0.0.1");
