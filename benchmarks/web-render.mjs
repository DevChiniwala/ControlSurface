/** Measure actual browser route-to-render time for benchmark traces.
 *
 * Requires a disposable Benchmark project created by system.py and the same
 * CS_BENCH_OWNER_PASSWORD value used for that run. Results are measurements,
 * not capacity claims.
 */

import { chromium } from "../apps/web/node_modules/playwright/index.mjs";

function required(name) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function distribution(values) {
  const ordered = [...values].sort((a, b) => a - b);
  const at = (fraction) =>
    ordered[
      Math.max(
        0,
        Math.min(ordered.length - 1, Math.ceil(ordered.length * fraction) - 1),
      )
    ];
  return {
    p50_ms: Number(at(0.5).toFixed(3)),
    p95_ms: Number(at(0.95).toFixed(3)),
  };
}

const web = process.env.CS_BENCH_WEB_URL || "http://localhost:3000";
const password = required("CS_BENCH_OWNER_PASSWORD");
const traces = [
  { size: 1000, id: required("CS_BENCH_TRACE_1000") },
  { size: 10000, id: required("CS_BENCH_TRACE_10000") },
];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});

try {
  await page.goto(`${web}/overview`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Email").fill("benchmark@example.invalid");
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.locator(".shell").waitFor({ state: "visible" });
  // The initial unauthenticated identity probe is expected to return 401.
  browserErrors.length = 0;

  const results = [];
  for (const trace of traces) {
    const samples = [];
    let renderedRows = 0;
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const started = performance.now();
      await page.goto(`${web}/traces/${trace.id}`, {
        waitUntil: "domcontentloaded",
      });
      const expectedRows = Math.min(trace.size, 2000);
      await page.waitForFunction(
        (expected) =>
          document.querySelectorAll(".detail-panel .span-row").length ===
          expected,
        expectedRows,
        { timeout: 120000 },
      );
      samples.push(performance.now() - started);
      renderedRows = await page.locator(".detail-panel .span-row").count();
    }
    results.push({
      source_spans: trace.size,
      rendered_tree_rows: renderedRows,
      bounded_tree: renderedRows < trace.size,
      ...distribution(samples),
    });
  }
  if (browserErrors.length) {
    throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
  }
  console.log(
    JSON.stringify(
      {
        timestamp_utc: new Date().toISOString(),
        viewport: { width: 1440, height: 1000 },
        samples_per_trace: 5,
        route_to_render: results,
        note: "Warm local Chromium measurements on a single-node disposable stack.",
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
