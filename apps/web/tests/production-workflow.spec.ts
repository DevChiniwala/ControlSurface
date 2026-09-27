import { expect, test } from "@playwright/test";

test.skip(
  process.env.CONTROLSURFACE_BROWSER_E2E !== "1",
  "Requires the disposable stack after the Python hero test seeds it",
);

const api = process.env.CONTROLSURFACE_API_URL || "http://localhost:8000";
const ownerEmail =
  process.env.CONTROLSURFACE_BROWSER_OWNER_EMAIL || "ci-owner@example.invalid";
const ownerPassword =
  process.env.CONTROLSURFACE_BROWSER_OWNER_PASSWORD ||
  "disposable-ci-password-only";

test("production health to incident evidence, run, dataset, and release decision", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  const login = await page.request.post(`${api}/api/login`, {
    data: {
      email: ownerEmail,
      password: ownerPassword,
    },
  });
  expect(login.status()).toBe(200);

  await page.goto("/");
  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await expect(
    page.getByRole("heading", { name: "Production Health" }),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "Project" }).selectOption({
    label: "Refund reliability",
  });
  await expect(
    page.getByRole("cell", { name: "refund-agent" }).first(),
  ).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("production-health.png") });

  await navigation
    .getByRole("button", { name: "Incidents", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Incidents", exact: true }),
  ).toBeVisible();
  await page.locator(".table-panel tbody button").first().click();
  await expect(page).toHaveURL(/\/incidents\/[0-9a-f-]+$/);
  await expect(
    page.getByText("Evidence-ranked change candidates"),
  ).toBeVisible();
  await expect(page.locator(".candidate").first()).toContainText(
    "payments.refund",
  );
  await page.screenshot({ path: testInfo.outputPath("incident-evidence.png") });
  await page.getByRole("button", { name: "Create regression case" }).click();
  const review = page.getByRole("dialog", { name: "Review regression case" });
  await expect(review).toBeVisible();
  await expect(review.getByLabel("Input JSON")).not.toBeEmpty();
  await review.getByRole("button", { name: "Close regression review" }).click();
  await expect(page.locator(".trace-tree")).toBeVisible();
  await expect(page).toHaveURL(/\/traces\/[0-9a-f]{32}$/);
  const execution = page.getByRole("region", { name: "Agent execution flow" });
  await expect(execution).toBeVisible();
  await execution.getByRole("button", { name: "Timeline" }).click();
  await expect(execution.locator(".trace-waterfall").first()).toBeVisible();
  await execution.getByRole("button", { name: "Transcript" }).click();
  await page.screenshot({ path: testInfo.outputPath("agent-execution.png") });
  await page.getByRole("button", { name: "Close trace" }).click();
  await expect(page).toHaveURL(/\/traces$/);

  await navigation
    .getByRole("button", { name: "Datasets", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Datasets", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("view-datasets.png") });
  await page.getByRole("button", { name: "Refund scenarios" }).click();
  const dataset = page.getByRole("dialog", { name: "Refund scenarios" });
  await expect(dataset.getByText("SCENARIO 1", { exact: true })).toBeVisible();
  await dataset.getByLabel("Input JSON").fill('{"message":"ui-browser-check"}');
  await dataset
    .getByLabel("Expected behavior JSON")
    .fill('{"completion":true}');
  await dataset.getByRole("button", { name: "Add item" }).click();
  await expect(
    dataset
      .locator(".inspector-item pre.json-block")
      .filter({
        hasText: "ui-browser-check",
      })
      .first(),
  ).toBeVisible();
  await dataset.getByRole("button", { name: "Close dataset" }).click();

  await navigation.getByRole("button", { name: "Release Gates" }).click();
  await expect(
    page.getByRole("heading", { name: "Release Gates" }),
  ).toBeVisible();
  await page.locator(".release-list-panel tbody .run-cell").first().click();
  await expect(page).toHaveURL(/\/releases\/[0-9a-f-]+$/);
  const evidence = page.getByRole("region", { name: /refund-agent@/ });
  await expect(evidence.locator(".gate-decision")).toBeVisible();
  await expect(evidence.getByText("CONTENT SHA-256")).toBeVisible();
  await expect(evidence.getByText("Regressed cases")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("release-decision.png") });
  await evidence
    .getByRole("button", { name: "Close release evidence" })
    .click();
  await expect(page).toHaveURL(/\/releases$/);

  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await navigation
    .getByRole("button", { name: "Overview", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Production Health" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "refund-agent" }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("production-health-mobile.png"),
  });
  const documentWidth = await page.evaluate(
    () => document.documentElement.scrollWidth,
  );
  expect(documentWidth).toBeLessThanOrEqual(390);
  await page.setViewportSize({ width: 1280, height: 720 });

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
  await expect(page.getByText("Illustrative product preview")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("auth-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByLabel("Illustrative production health preview"),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.getByLabel("Email").fill(ownerEmail);
  await page.getByLabel("Password").fill(ownerPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(
    page.getByRole("heading", { name: "Production Health" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 720 });
  for (const [navigationLabel, heading] of [
    ["Traces", "Traces"],
    ["Sessions", "Sessions"],
    ["Failure Clusters", "Failure Clusters"],
    ["Change Ledger", "Change ledger"],
    ["Regression Cases", "Regression cases"],
    ["SLOs", "SLOs"],
    ["API Keys", "API keys"],
  ]) {
    await navigation
      .getByRole("button", { name: navigationLabel, exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
    await expect(page.locator(".skeleton-row")).toHaveCount(0);
    await page.screenshot({
      path: testInfo.outputPath(
        `view-${navigationLabel.toLowerCase().replaceAll(" ", "-")}.png`,
      ),
    });
    if (navigationLabel === "Sessions") {
      await page.locator(".table-panel tbody .row-link").first().click();
      const session = page.getByRole("dialog", { name: /^Session / });
      await expect(session.locator("tbody tr").first()).toBeVisible();
      await session.getByRole("button", { name: "Close session" }).click();
    }
    if (navigationLabel === "Failure Clusters") {
      await expect(page.locator(".cluster-summary-grid")).toContainText(
        "Sampled failed runs",
      );
    }
    if (navigationLabel === "SLOs") {
      await expect(page.locator(".slo-measure").first()).toContainText(
        "Target",
      );
    }
    if (navigationLabel === "API Keys") {
      await page.getByRole("button", { name: "Create key" }).click();
      const keyDialog = page.getByRole("dialog", { name: "Create key" });
      await expect(
        keyDialog.getByRole("button", { name: "Close" }),
      ).toBeFocused();
      await keyDialog.getByLabel("Key label").fill("Browser workflow key");
      await keyDialog.getByRole("button", { name: "Close" }).click();
      await expect(keyDialog).toBeHidden();
    }
  }
  await page.evaluate(() => {
    document.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "k",
        code: "KeyK",
        ctrlKey: true,
        bubbles: true,
      }),
    );
  });
  const palette = page.getByRole("dialog", { name: "Navigate ControlSurface" });
  await expect(palette).toBeVisible();
  await palette.getByRole("textbox", { name: "Find a view" }).fill("SLOs");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "SLOs" })).toBeVisible();
});
