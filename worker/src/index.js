export default {
  async fetch(request, env) {
    if (request.method !== "POST")
      return new Response("POST /suggest", { status: 405 });

    const token = request.headers.get("Authorization")?.replace("Bearer ", "");
    if (token !== env.AUTH_TOKEN)
      return new Response("Unauthorized", { status: 401 });

    const body = await request.json();
    if (!body.idea)
      return new Response(JSON.stringify({ error: "missing 'idea' field" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });

    const key = `${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;
    await env.SUGGESTIONS.put(
      key,
      JSON.stringify({
        idea: body.idea,
        source: body.source || "api",
        tags: body.tags || [],
        timestamp: new Date().toISOString(),
      }),
    );

    return Response.json({ ok: true });
  },
};
