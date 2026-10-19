/**
 * Hourly trigger for the ingestion workflow.
 *
 * GitHub's own scheduler is best effort: in this repository it started only 4 of
 * ~17 hourly runs on its first day. Cloudflare Cron Triggers fire on time, so this
 * Worker asks GitHub to start `hourly.yml` (workflow_dispatch) at minute 25 of every
 * hour. The workflow is idempotent, so an extra run from GitHub's own schedule is harmless.
 *
 * Secret: GITHUB_TOKEN — fine-grained token limited to this repository with
 * "Actions: Read and write". Free: Workers free plan includes Cron Triggers.
 */
export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },

  // Visiting the Worker's address only shows what it does; it never starts a run.
  async fetch() {
    return new Response('weather-warehouse trigger: starts the hourly ingestion at minute 25 (UTC).\n', {
      headers: { 'content-type': 'text/plain; charset=utf-8' },
    });
  },
};

async function dispatch(env) {
  const url = `https://api.github.com/repos/${env.REPO}/actions/workflows/${env.WORKFLOW}/dispatches`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: 'application/vnd.github+json',
      'x-github-api-version': '2022-11-28',
      'user-agent': 'weather-warehouse-trigger',
    },
    body: JSON.stringify({ ref: env.REF }),
  });
  // GitHub answers 204 No Content when the run is queued.
  if (!response.ok) {
    throw new Error(`GitHub dispatch failed: ${response.status} ${await response.text()}`);
  }
  console.log(`Dispatched ${env.WORKFLOW} on ${env.REF}`);
}
