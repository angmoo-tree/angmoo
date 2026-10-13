type LayoutNode = { world_character_id: string; display_name: string; is_center: boolean };
/** Keep every grapheme, including spaces, while bounding the visual label width. */
export function relationshipGraphNameLines(name: string): string[] {
  const graphemes = Array.from(new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(name), part => part.segment);
  const lines = [];
  for (let offset = 0; offset < graphemes.length; offset += 24) lines.push(graphemes.slice(offset, offset + 24).join(""));
  return lines.length ? lines : [""];
}
export function relationshipGraphLayout(nodes: readonly LayoutNode[]) {
  const ordered = [...nodes].sort((a, b) => Number(b.is_center) - Number(a.is_center) || a.world_character_id.localeCompare(b.world_character_id));
  const names = ordered.map(node => relationshipGraphNameLines(node.display_name));
  const lineCount = Math.max(1, ...names.map(lines => lines.length));
  const labelHeight = lineCount * 20;
  const labelWidth = Math.max(100, ...names.flatMap(lines => lines.map(line => Array.from(line).length * 14 + 24)));
  const cellWidth = labelWidth + 48;
  const cellHeight = Math.max(160, labelHeight + 95);
  const odd = (value: number) => value % 2 ? value : value + 1;
  const columns = Math.max(3, odd(Math.ceil(Math.sqrt(ordered.length))));
  const rows = Math.max(3, odd(Math.ceil(ordered.length / columns)));
  const width = Math.max(480, columns * cellWidth), height = Math.max(340, rows * cellHeight);
  const cells = Array.from({ length: rows * columns }, (_, i) => ({ x: (i % columns + .5) * width / columns, y: (Math.floor(i / columns) + .5) * height / rows - labelHeight / 2 }));
  const center = { x: width / 2, y: height / 2 - labelHeight / 2 };
  const candidates = cells.filter(p => Math.hypot(p.x - center.x, p.y - center.y) > 1).sort((a, b) => Math.hypot(a.x - center.x, a.y - center.y) - Math.hypot(b.x - center.x, b.y - center.y) || a.y - b.y || a.x - b.x);
  return { width, height, positions: new Map(ordered.map((node, index) => [node.world_character_id, index === 0 && node.is_center ? center : candidates[index - (ordered[0]?.is_center ? 1 : 0)] ?? cells[index]])) };
}
