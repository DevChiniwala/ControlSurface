import { expect, test } from "@playwright/test";

test.skip(
  process.env.CONTROLSURFACE_BROWSER_E2E !== "1",
  "Requires the disposable stack after the Python hero test seeds it",
);

const api = process.env.CONTROLSURFACE_API_URL || "http://localhost:8000";

test("production health to incident evidence, run, dataset, and release decision", async ({
  page,
}) => {
  const login = await page.request.post(`${api}/api/login`, {
    data: {
      email: "ci-owner@example.invalid",
      password: "disposable-ci-password-only",
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
  await expect(page.getByText("refund-agent", { exact: true })).toBeVisible();

  await navigation
    .getByRole("button", { name: "Incidents", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Incidents", exact: true }),
  ).toBeVisible();
  await page.locator(".table-panel tbody button").first().click();
  await expect(
    page.getByText("Evidence-ranked change candidates"),
  ).toBeVisible();
  await expect(page.locator(".candidate").first()).toContainText(
    "payments.refund",
  );
  await page.locator(".representative-link").first().click();
  await expect(page.locator(".trace-tree")).toBeVisible();
  await page.getByRole("button", { name: "Create regression" }).click();
  const review = page.getByRole("dialog", { name: "Review regression case" });
  await expect(review).toBeVisible();
  await expect(review.getByLabel("Input JSON")).not.toBeEmpty();
  await review.getByRole("button", { name: "Close regression review" }).click();
  await page.getByRole("button", { name: "Close trace" }).click();

  await navigation
    .getByRole("button", { name: "Datasets", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Datasets", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Refund scenarios" }).click();
  const dataset = page.getByRole("dialog", { name: "Refund scenarios" });
  await expect(dataset.getByText("SCENARIO 1")).toBeVisible();
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

  await navigation.getByRole("button", { name: "Release evidence" }).click();
  await expect(
    page.getByRole("heading", { name: "Release evidence" }),
  ).toBeVisible();
  await page.locator(".table-panel tbody button").first().click();
  const evidence = page.getByRole("dialog", { name: /refund-agent@/ });
  await expect(evidence.getByText("CONTENT SHA-256")).toBeVisible();
  await expect(evidence.getByText("Regressed cases")).toBeVisible();
  await evidence
    .getByRole("button", { name: "Close release evidence" })
    .click();

  await page.setViewportSize({ width: 390, height: 844 });
  await navigation.getByRole("button", { name: "Health", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Production Health" }),
  ).toBeVisible();
  await expect(page.getByText("refund-agent", { exact: true })).toBeVisible();
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
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByLabel("Illustrative production health preview"),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.getByLabel("Email").fill("ci-owner@example.invalid");
  await page.getByLabel("Password").fill("disposable-ci-password-only");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(
    page.getByRole("heading", { name: "Production Health" }),
  ).toBeVisible();
});
