import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AuthContext } from "../../src/lib/auth/auth-context";
import { cacheUser, type UserRead } from "../../src/lib/auth/browser-session";
import { usePrivateMediaResource } from "../../src/hooks/use-private-media-url";
// Test alias points to the exact file read from the explicitly selected baseline ref.
import { usePrivateMediaUrl as useBaseline } from "baseline-private-media";

const user: UserRead = {id:"fixture-owner",display_name:"Fixture",email:null,is_admin:false,profile_setup_completed:true,feed_content_filter:"all",display_name_updated_at:null,display_name_change_available_at:null};
cacheUser(user);
type Options = {source:string;revision:number;show:boolean;identity:string};
const fixture = {set: (value:Partial<Options>) => {void value;},retry: () => {},urls:[] as string[],revoked:[] as string[]};
Object.assign(window,{fixture});
const create = URL.createObjectURL, revoke = URL.revokeObjectURL;
URL.createObjectURL = blob => {const url=create(blob);fixture.urls.push(url);return url;};
URL.revokeObjectURL = url => {fixture.revoked.push(url);revoke(url);};
function Probe({source,revision}:Options) {
  const result = usePrivateMediaResource(source,revision), baseline = useBaseline(source);
  useEffect(() => {fixture.retry = result.retry;},[result.retry]);
  // eslint-disable-next-line @next/next/no-img-element
  return <><img id="current" alt="Current preview" src={result.url ?? undefined} /><img id="baseline" alt="Baseline preview" src={baseline ?? undefined} /><output id="status">{result.error ? "error" : result.loading ? "loading" : "ready"}</output></>;
}
function App() {
  const [options,setOptions] = useState<Options>({source:"/api/v1/agents/drafts/fixture/media/avatar",revision:0,show:true,identity:user.id});
  useEffect(() => {fixture.set = next => setOptions(previous => ({...previous,...next}));},[]);
  const currentUser={...user,id:options.identity};cacheUser(currentUser);
  return <AuthContext.Provider value={{user:currentUser,status:"authenticated",refresh:async()=>{},sessionRevision:options.identity === user.id ? 0 : 1}}>{options.show ? <Probe {...options} /> : null}</AuthContext.Provider>;
}
createRoot(document.getElementById("root")!).render(<App />);
