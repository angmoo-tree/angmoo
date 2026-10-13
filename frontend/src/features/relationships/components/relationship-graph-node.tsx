"use client";

import { ProfileAvatar } from "@/components/ui/profile-avatar";
import type { RelationshipGraphNode as GraphNode } from "../types/relationship-graph";
import styles from "./relationship-graph-node.module.css";
import { relationshipGraphNameLines } from "../utils/graph-layout";

export function RelationshipGraphNode({ node, point }: { node: GraphNode; point: { x: number; y: number } }) {
  const radius = node.is_center ? 35 : 29;
  return <g data-relationship-node={node.world_character_id} data-relationship-center={node.is_center ? "true" : "false"}>
    <title>{node.display_name}</title>
    <foreignObject x={point.x - radius} y={point.y - radius} width={radius * 2} height={radius * 2}>
      <div className={`${styles.node} ${node.is_center ? styles.center : ""}`}>
        <ProfileAvatar name={node.display_name} avatarUrl={node.avatar_url} sizeClassName={styles.avatar} textClassName={node.is_center ? styles.centerInitial : styles.initial} />
      </div>
    </foreignObject>
    <text x={point.x} y={point.y + radius + 20} textAnchor="middle" className="fill-on-surface text-[13px] font-bold">{relationshipGraphNameLines(node.display_name).map((line, index) => <tspan key={index} x={point.x} dy={index ? 20 : 0}>{line}</tspan>)}</text>
  </g>;
}
