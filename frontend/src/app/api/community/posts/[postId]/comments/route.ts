export async function POST() {
  return Response.json(
    { detail: "Legacy comments are disabled. Use replies instead." },
    { status: 410 },
  );
}
