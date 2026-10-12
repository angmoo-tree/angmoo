"use client";
import {useEffect, useState, type ReactNode} from "react";
import {useAuthRuntimeIdentity} from "@/hooks/use-auth-runtime-identity";
import {useUiText} from "@/hooks/use-ui-text";
import {captureAuthRequestScope,isCurrentAuthRequestScope} from "@/lib/auth/browser-session";
import {getWorld,WorldApiError} from "../api/worlds";

export async function readWorldLiveness(worldId:string, signal:AbortSignal):Promise<boolean|null> {
  try { await getWorld(worldId,{signal});return true; }
  catch(reason) {
    return reason instanceof WorldApiError && ["world_deleting","world_deleted"].includes(reason.message)?false:null;
  }
}

export function useWorldDeletionWatch(worldId:string|undefined, enabled=true) {
  const identity=useAuthRuntimeIdentity(worldId??"no-world");
  const [closed,setClosed]=useState<string|null>(null);
  useEffect(()=>{
    if(!enabled||!worldId)return;
    const abort=new AbortController(),scope=captureAuthRequestScope();let reading=false;
    async function check() {
      if(reading||document.visibilityState==="hidden")return;
      reading=true;
      try { const available=await readWorldLiveness(worldId!,abort.signal);
        if(!abort.signal.aborted&&isCurrentAuthRequestScope(scope)&&available===false)setClosed(identity);
      } finally { reading=false; }
    }
    const focus=()=>void check();
    window.addEventListener("focus",focus);document.addEventListener("visibilitychange",focus);
    const timer=setInterval(focus,15_000);
    return()=>{abort.abort();clearInterval(timer);window.removeEventListener("focus",focus);document.removeEventListener("visibilitychange",focus);};
  },[identity,enabled,worldId]);
  return closed===identity;
}

export function WorldDeletionBoundary({worldId,enabled=true,children}:{worldId?:string;enabled?:boolean;children:ReactNode}) {
  const closed=useWorldDeletionWatch(worldId,enabled),text=useUiText("worlds");
  return closed?<p role="status">{text("이 World는 더 이상 사용할 수 없어요.")}</p>:children;
}
