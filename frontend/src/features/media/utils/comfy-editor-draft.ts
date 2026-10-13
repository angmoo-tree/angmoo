import type {ApiGraph,WorkflowInput,WorkflowAnalysis,RetainedComfyContract} from "../types/media";

export const serializeComfyGraph=(graph:ApiGraph)=>JSON.stringify(graph,null,2)+"\n";

export function retainedComfyContract(workflow?:WorkflowInput):RetainedComfyContract|undefined {
  if(!workflow)return;
  if(!("input_mode" in workflow))return {bindings:workflow.bindings,legacy_output_node:workflow.output_node,reference_required:workflow.reference_required};
  return {output:workflow.output,...("bindings" in workflow?{bindings:workflow.bindings}:{})};
}

export function replaceComfyGraph(options:Record<string,unknown>,path:"workflow"|"text_workflow",analysis:WorkflowAnalysis) {
  const next={...options};
  const legacy=options.options_schema_version!==2&&Boolean(options.workflow);
  if(legacy){
    for(const item of ["workflow","text_workflow"] as const){
      const graph=options[item] as WorkflowInput|undefined;
      if(graph&&!("input_mode"in graph))next[item]={input_mode:"node_bindings",prompt:graph.prompt,bindings:graph.bindings,output:{mode:"explicit_node",node_id:graph.output_node}};
    }
  }
  next.options_schema_version=2;
  next.clip_skip_value_mode=legacy?"node_value":options.clip_skip_value_mode??"skip_count";
  next[path]={input_mode:"placeholders",prompt:analysis.prompt,output:{mode:"auto_first_image"}};
  const values={...(options.values as Record<string,unknown>|undefined)};
  const defaults:Record<string,unknown>={width:512,height:512,steps:20,cfg:7,sampler:"euler",scheduler:"normal",seed:-1,
    denoise:analysis.reference_required?0.65:1,clip_skip:next.clip_skip_value_mode==="node_value"?-1:1};
  for(const role of analysis.used_roles)if(!Object.hasOwn(values,role)&&Object.hasOwn(defaults,role))values[role]=defaults[role];
  next.values=values;
  return next;
}
