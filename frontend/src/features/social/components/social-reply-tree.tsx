import { Fragment, type ReactNode } from "react";
import type { ReplyNode, ThreadReply } from "../utils/reply-tree";
import styles from "./social-presentation.module.css";

export function SocialReplyTree<T extends ThreadReply>({nodes, renderRow, depth = 0}: {nodes: ReplyNode<T>[]; renderRow: (reply: T) => ReactNode; depth?: number}) {
  return <>{nodes.map(node => <Fragment key={node.reply.id}>
    <div className={styles.replyBranch} data-reply-depth={depth} style={{marginInlineStart: `${Math.min(depth, 4) * 8}px`}}>{renderRow(node.reply)}</div>
    <SocialReplyTree nodes={node.children} renderRow={renderRow} depth={depth + 1} />
  </Fragment>)}</>;
}
