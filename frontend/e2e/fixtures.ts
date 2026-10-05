import { expect, test as base, type Page } from "@playwright/test";

export const ADMIN = { username: "admin", password: "e2e-password-1" };
export const CSRF = { "X-Requested-With": "TubeVault" };

/** Every test fails on uncaught errors in the page and on server errors (5xx). */
export const test = base.extend<{ problems: string[] }>({
  problems: [
    async ({ page }, use) => {
      const problems: string[] = [];
      page.on("pageerror", (error) => problems.push(`page error: ${error.message}`));
      page.on("response", (response) => {
        if (response.status() >= 500) problems.push(`${response.status()} ${response.url()}`);
      });
      await use(problems);
      expect(problems).toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/** Signs in through the API – quicker than the form when that isn't what is tested. */
export async function signIn(page: Page, user = ADMIN): Promise<void> {
  const response = await page.request.post("/api/auth/login", { data: user, headers: CSRF });
  expect(response.ok()).toBe(true);
}
