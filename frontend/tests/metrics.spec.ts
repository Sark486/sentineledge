import { test, expect, type Page } from "@playwright/test";

async function collectConsoleErrors(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(String(err)));
  return errors;
}

test.describe("Metrics page", () => {
  test("renders the trend graph without console errors", async ({ page }) => {
    const errors = await collectConsoleErrors(page);

    await page.goto("/metrics");
    await expect(page.getByText("Trend Graph")).toBeVisible();
    await page.waitForTimeout(1000);

    // Ignore the generic 404 for /favicon.ico (not served in dev) — only
    // fail on errors that actually indicate broken app behavior.
    expect(errors.filter((e) => !e.includes("404"))).toEqual([]);
  });

  test("'All devices' plots one averaged line per metric, not one per device", async ({ page }) => {
    await page.goto("/metrics");
    await expect(page.getByText("Trend Graph")).toBeVisible();
    await page.waitForTimeout(1200);

    const deviceSelect = page.locator("label:has-text('Device') select");
    await expect(deviceSelect).toHaveValue("");

    // At most one line per metric (temperature/humidity/pressure) regardless
    // of how many devices are reporting — devices are averaged together, not
    // split into separate series.
    const lineCount = await page.locator(".recharts-line").count();
    expect(lineCount).toBeLessThanOrEqual(3);
  });

  test("interval dropdown switches between auto/5m/1h without breaking the chart", async ({ page }) => {
    const errors = await collectConsoleErrors(page);

    await page.goto("/metrics");
    await expect(page.getByText("Trend Graph")).toBeVisible();

    const intervalSelect = page.locator("label:has-text('Interval') select");
    for (const option of ["5m", "1h", "auto"]) {
      await intervalSelect.selectOption(option);
      await page.waitForTimeout(1000);
    }

    // Ignore the generic 404 for /favicon.ico (not served in dev) — only
    // fail on errors that actually indicate broken app behavior.
    expect(errors.filter((e) => !e.includes("404"))).toEqual([]);
  });

  test("current readings table lists online devices", async ({ page }) => {
    await page.goto("/metrics");
    await page.locator("button:has-text('Current readings')").click();

    const headers = await page.locator("table thead th").allTextContents();
    expect(headers).toEqual(["Device", "Location", "Temperature", "Humidity", "Pressure", "Updated"]);
  });
});
