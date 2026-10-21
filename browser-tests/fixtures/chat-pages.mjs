/** Current read projection for small synthetic threads used by older UI cases.
 * Pagination behavior itself is exercised with an explicit server in runtime-pages.
 */
export function withChatPages(value) {
  if (!value || typeof value !== "object") return value;
  if (value.thread) return { ...value, thread: withChatPages(value.thread) };
  if (!value.requester || !value.responding || !Array.isArray(value.messages)) return value;
  if (value.message_page) return value;
  const items = value.messages.slice(-50);
  const evidence = (value.evidence_summaries ?? []).filter(summary => items.some(item => item.id === summary.assistant_message_id));
  return { ...value, messages: items, evidence_summaries: evidence, message_page: {
    schema_version: "world-chat-message-page.v1", world_id: value.world_id, thread_id: value.id,
    items, evidence_summaries: evidence, direction: "latest", has_more: value.messages.length > 50,
    oldest_cursor: items.length ? `fixture-${items[0].id}` : null,
    newest_cursor: `fixture-${items.at(-1)?.id ?? 0}`,
    next_cursor: value.messages.length > 50 ? `fixture-${items[0].id}` : null,
  } };
}
