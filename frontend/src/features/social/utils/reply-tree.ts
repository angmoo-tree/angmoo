export type ThreadReply = {id: string; reply_to_post_id: string | null};
export type ReplyNode<T extends ThreadReply> = {reply: T; children: ReplyNode<T>[]};

/** Missing parents stay explicit on the value; never rewrite them to the selected root. */
export function buildReplyTree<T extends ThreadReply>(replies: T[], rootPostId: string): ReplyNode<T>[] {
  const nodes = new Map(replies.map(reply => [reply.id, {reply, children: [] as ReplyNode<T>[]} ]));
  if (nodes.size !== replies.length) throw new Error("manual_social_thread_scope_mismatch");
  const roots: ReplyNode<T>[] = [];
  for (const reply of replies) {
    let cursor: string | null = reply.id;
    const seen = new Set<string>();
    while (cursor && nodes.has(cursor)) {
      if (seen.has(cursor)) throw new Error("manual_social_thread_scope_mismatch");
      seen.add(cursor); cursor = nodes.get(cursor)!.reply.reply_to_post_id;
    }
    const node = nodes.get(reply.id)!;
    const parent = reply.reply_to_post_id !== rootPostId && reply.reply_to_post_id ? nodes.get(reply.reply_to_post_id) : null;
    if (parent) parent.children.push(node); else roots.push(node);
  }
  return roots;
}
