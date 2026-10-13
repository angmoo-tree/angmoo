import "server-only";
import {readAgentGuide,readOpenApiSpec} from "../api/documents-server";
import {AngmooApiContent} from "./angmoo-api-content";

export async function AngmooApiServerContent(){
  const [ko,en,openApiSpec]=await Promise.all([readAgentGuide("ko"),readAgentGuide("en"),readOpenApiSpec()]);
  return <AngmooApiContent guides={{ko,en}} openApiSpec={openApiSpec}/>;
}
