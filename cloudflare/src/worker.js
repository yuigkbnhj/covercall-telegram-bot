async function dispatchWorkflow(env, workflowFile, inputs = {}) {
  const res = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${workflowFile}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "covercall-trigger-worker",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    }
  );

  if (!res.ok) {
    console.error(`dispatch of ${workflowFile} failed: ${res.status} ${await res.text()}`);
  }
}

export default {
  async scheduled(event, env, ctx) {
    // Only one cron is registered now (see wrangler.toml) - the daily scan.
    // Command handling moved to the webhook below.
    await dispatchWorkflow(env, "daily_scan.yml");
  },

  async fetch(request, env, ctx) {
    if (request.method !== "POST") {
      return new Response("not found", { status: 404 });
    }

    // Telegram sets this header to the secret_token configured when the
    // webhook was registered (setWebhook) - rejects anyone else who finds
    // this URL and tries to POST fake updates to trigger our workflow.
    const token = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (token !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response("unauthorized", { status: 401 });
    }

    const update = await request.json();
    await dispatchWorkflow(env, "handle_command.yml", {
      update_json: JSON.stringify(update),
    });

    return new Response("ok");
  },
};
