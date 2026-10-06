import { expect, test } from "@playwright/test";

for (const language of ["ko", "en"] as const) {
  for (const count of [1, 7, 20]) {
    test(`Relationship map retains every long name, direction and node (${language}, ${count})`, async ({page}, info) => {
      const owner = {id:"local-owner",email:null,display_name:"Local Owner",profile_setup_completed:true,is_admin:true,ui_language:language,ui_preference_revision:0,feed_content_filter:"all"};
      const nodes = Array.from({length:count}, (_, i) => ({world_character_id:`node-${i}`,character_id:`source-${i}`,display_name:`${i}·` + "긴이름 LongName 👨‍👩‍👦 ".repeat(7),is_center:i===0,avatar_url:null}));
      const edges = nodes.slice(1).flatMap((node,i) => [
        {relationship_state_id:`out-${i}`,actor_world_character_id:"node-0",target_world_character_id:node.world_character_id},
        {relationship_state_id:`in-${i}`,actor_world_character_id:node.world_character_id,target_world_character_id:"node-0"},
      ]).map(edge => ({...edge,relationship_label:"Original relationship ".repeat(10),perception:"Original perception",view_version:1,view_updated_at:null,reviewed_at:null,familiarity:1,affinity:2,trust:3,tension:0,interaction_count:5,relationship_version:1,last_event_id:null,last_event_at:null}));
      const writes: string[] = [];
      const graph = {world_id:"graph-world",center_world_character_id:"node-0",nodes,edges,evidence:[],meta:{template:"neighborhood",source:"ladybug",graph_status:"healthy",truncated:false,projection_lag_seconds:0,revalidated_node_count:count,revalidated_edge_count:edges.length,fallback_reason:null}};
      const isStatic=info.project.name === "static-export";
      if(isStatic) await page.addInitScript(() => Object.assign(window,{__ANGMOO_RUNTIME_CONFIG__:{profile:"tauri-static",apiBaseUrl:"http://127.0.0.1:8080",graphProvider:"ladybug",launchToken:"extra-fixture-token-0000000000000"}}));
      await page.route(isStatic ? "http://127.0.0.1:8080/api/v1/**" : "**/api/backend/**", async route => {
        const path=new URL(route.request().url()).pathname;
        if(route.request().method() !== "GET") writes.push(path);
        const data=path.endsWith("/auth/me") ? owner : path.endsWith("/relationship-graph") ? graph : path.endsWith("/relationship-review") ? {mode:"interpreted",configuration:{status:"scheduled",local_time:"02:00",timezone:"Asia/Seoul"},jobs:[],states:[],excluded_counts:{}} : {detail:"unexpected_fixture_request"};
        await route.fulfill({status:path.endsWith("/auth/me") || path.endsWith("/relationship-graph") || path.endsWith("/relationship-review") ? 200 : 404,json:data});
      });
      await page.goto("/characters/source-0/worlds/graph-world/relationship-graph");
      if(count === 1) {
        await expect(page.locator('[data-relationship-graph-state="empty"]')).toBeVisible();
        await expect(page.locator("[data-relationship-node]")).toHaveCount(0);
        expect(writes).toEqual([]);
        return;
      }
      const svg=page.locator("svg").filter({has:page.locator("[data-relationship-node]")});
      await expect(svg.locator("[data-relationship-node]")).toHaveCount(count);
      await expect(page.locator("[data-relationship-list-item]")).toHaveCount(edges.length);
      for(const width of [390,480,960,1440]) {
        await page.setViewportSize({width,height:1000});
        for(const zoom of [1,2]) {
          await page.evaluate(value => {document.documentElement.style.fontSize = `${value*16}px`;},zoom);
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
          const bounds=await svg.evaluate(element => {
            const svg=element as SVGSVGElement, view=svg.viewBox.baseVal;
            return Array.from(svg.querySelectorAll<SVGGElement>("[data-relationship-node]")).map(node => {
              const b=node.getBBox();return {name:node.querySelector("text")!.textContent,x:b.x,y:b.y,width:b.width,height:b.height,inBounds:b.x>=0 && b.y>=0 && b.x+b.width<=view.width && b.y+b.height<=view.height};
            });
          });
          expect(bounds.every(value=>value.inBounds)).toBe(true);
          for (let i=0;i<bounds.length;i++) for(let j=i+1;j<bounds.length;j++) {
            const a=bounds[i],b=bounds[j];
            expect(a.x+a.width<=b.x || b.x+b.width<=a.x || a.y+a.height<=b.y || b.y+b.height<=a.y).toBe(true);
          }
          expect(bounds.map(value=>value.name)).toEqual([...nodes].sort((a,b)=>Number(b.is_center)-Number(a.is_center)||a.world_character_id.localeCompare(b.world_character_id)).map(node=>node.display_name));
        }
      }
      for(const edge of edges) {
        await expect(svg.locator(`[data-relationship-edge="${edge.relationship_state_id}"]`)).toHaveAttribute("data-relationship-from",edge.actor_world_character_id);
        await expect(svg.locator(`[data-relationship-edge="${edge.relationship_state_id}"]`)).toHaveAttribute("data-relationship-to",edge.target_world_character_id);
      }
      expect(writes).toEqual([]);
      await page.screenshot({path:info.outputPath(`graph-${language}-${count}.png`),fullPage:true});
    });
  }
}
