// Keepalive-воркер Feris Shop.
// Каждую минуту (cron: Dashboard -> Triggers или [triggers] crons
// в wrangler.toml, например "*/1 * * * *") дергает URL бота/сайта, чтобы
// бесплатный инстанс Render/Koyeb не уснул — бот поллингует 24/7.
//
// URL для пинга задаётся секретом HEALTH_URL
// (например: https://feri-shop.onrender.com/healthz).
// Без него — fallback из TARGET ниже.
const TARGET = "https://feri-shop.onrender.com/healthz";

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(ping(env));
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/") {
      return new Response("Feris Shop keepalive worker is up", {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    if (url.pathname === "/ping") {
      const res = await ping(env);
      return new Response(`ping -> ${res}`, {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    return new Response("Not found", { status: 404 });
  },
};

async function ping(env) {
  const target = (env && env.HEALTH_URL ? env.HEALTH_URL : TARGET).replace(/\/+$/, "");
  const started = Date.now();
  let ok = false;
  let status = "n/a";
  try {
    const res = await fetch(target, {
      method: "GET",
      headers: { "user-agent": "CloudflareWorker-Cron/1.0" },
    });
    status = res.status;
    ok = res.ok;
  } catch (e) {
    status = "ERR: " + (e && e.message ? e.message : e);
  }
  const label = ok ? "OK" : "FAIL";
  console.log(
    `[${new Date().toISOString()}] ping ${target} -> ${label} (${status}, ${Date.now() - started}ms)`
  );
  return label + " (" + status + ")";
}
