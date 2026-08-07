export default {
  async scheduled(event, env, ctx) {
    const workflowFile =
      event.cron === "45 14 * * 1-5" ? "daily_scan.yml" : "poll_commands.yml";

    const res = await fetch(
      `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${workflowFile}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "covercall-trigger-worker",
        },
        body: JSON.stringify({ ref: "main" }),
      }
    );

    if (!res.ok) {
      console.error(`dispatch of ${workflowFile} failed: ${res.status} ${await res.text()}`);
    }
  },
};
