import { ADMIN, CSRF, expect, signIn, test } from "./fixtures";

test("signing in, with a wrong password first", async ({ page }) => {
  // Signed out, every address shows the login.
  await page.goto("/");
  await page.getByLabel("Benutzername").fill(ADMIN.username);
  await page.getByLabel("Passwort").fill("not-the-password");
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByText("Benutzername oder Passwort ist falsch.")).toBeVisible();

  await page.getByLabel("Passwort").fill(ADMIN.password);
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Start" })).toBeAttached();
  await expect(page.getByText("Weiterschauen").first()).toBeVisible();
});

test("every main page opens", async ({ page }) => {
  await signIn(page);
  const pages: [string, string | RegExp][] = [
    ["/library", "Bibliothek"],
    ["/channels", "Kanäle"],
    ["/playlists", "Playlists"],
    ["/folders", "Ordner"],
    ["/later", /Später/],
    ["/history", /Verlauf/],
    ["/search", /Suche/],
    ["/subscriptions", "Abos"],
    ["/downloads", "Downloads"],
    ["/settings", "Einstellungen"],
    ["/admin", "Verwaltung"],
    ["/admin/import", "Import"],
    ["/remote", "Fernbedienung"],
    ["/device", /Gerät/],
  ];
  for (const [path, name] of pages) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name }), path).toBeVisible();
  }
});

test("search finds a video and opens it", async ({ page }) => {
  await signIn(page);
  await page.goto("/search?q=Pasta");
  const result = page.getByRole("link", { name: /Pasta wie in Rom/ }).first();
  await expect(result).toBeVisible();
  await result.click();
  await expect(page.getByRole("heading", { level: 1, name: /Pasta wie in Rom/ })).toBeVisible();
  await expect(page.locator(".video-js")).toBeVisible();
});

test("marking as watched and adding to a playlist stick", async ({ page }) => {
  await signIn(page);
  await page.goto("/search?q=Tiramisu");
  await page
    .getByRole("link", { name: /Tiramisu ohne Ei/ })
    .first()
    .click();

  const watched = page.getByRole("button", { name: /Als gesehen markieren|Gesehen/ });
  const before = await watched.getAttribute("aria-pressed");
  await watched.click();
  await expect(watched).toHaveAttribute("aria-pressed", before === "true" ? "false" : "true");
  await page.reload();
  await expect(watched).toHaveAttribute("aria-pressed", before === "true" ? "false" : "true");

  await page.getByRole("button", { name: "Zur Playlist" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Neue Playlist" }).click();
  const naming = page.getByRole("dialog", { name: "Neue Playlist" });
  await naming.getByLabel("Name").fill("Browser-Test");
  await naming.getByRole("button", { name: "Erstellen" }).click();
  await expect(naming).toBeHidden();
  await page.goto("/playlists");
  await expect(page.getByText("Browser-Test").first()).toBeVisible();
});

test("sorting a video into a folder inside a folder", async ({ page }) => {
  await signIn(page);
  await page.goto("/folders");
  await page.getByRole("button", { name: "Neuer Ordner" }).first().click();
  const naming = page.getByRole("dialog", { name: "Neuer Ordner" });
  await naming.getByLabel("Name").fill("Kochen");
  await naming.getByRole("button", { name: "Erstellen" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Kochen" })).toBeVisible();

  await page.getByRole("button", { name: "Neuer Ordner" }).click();
  const inside = page.getByRole("dialog", { name: /Neuer Ordner in/ });
  await inside.getByLabel("Name").fill("Italienisch");
  await inside.getByRole("button", { name: "Erstellen" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Italienisch" })).toBeVisible();
  const path = page.getByRole("navigation", { name: "Pfad" });
  await expect(path.getByRole("link", { name: "Kochen" })).toBeVisible();

  await page.goto("/search?q=Pasta");
  await page
    .getByRole("link", { name: /Pasta wie in Rom/ })
    .first()
    .click();
  await page.getByRole("button", { name: "In Ordner" }).click();
  const dialog = page.getByRole("dialog", { name: "In Ordner ablegen" });
  const box = dialog.getByRole("checkbox", { name: /Italienisch/ });
  await box.click();
  await expect(box).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Escape");

  await page.goto("/folders");
  await page.getByRole("link", { name: /Kochen/ }).click();
  await page.getByRole("link", { name: /Italienisch/ }).click();
  await expect(page.getByRole("link", { name: /Pasta wie in Rom/ })).toBeVisible();
});

test("rare actions sit in the menu, and the sleep timer is in the player", async ({ page }) => {
  await signIn(page);
  await page.goto("/search?q=Pasta");
  await page
    .getByRole("link", { name: /Pasta wie in Rom/ })
    .first()
    .click();
  await expect(page.getByRole("link", { name: "Datei laden" })).toHaveCount(0);
  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  const menu = page.getByRole("menu", { name: "Weitere Aktionen" });
  await expect(menu.getByRole("menuitem", { name: "Datei laden" })).toBeVisible();
  await expect(menu.getByRole("menuitem", { name: "Video löschen" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();

  await page.getByRole("button", { name: "Schlaf-Timer", exact: true }).click();
  await page.getByRole("menuitemradio", { name: "15 Minuten" }).click();
  await expect(page.getByRole("button", { name: "Schlaf-Timer: 15 min" })).toBeVisible();
  await page.getByRole("button", { name: "Schlaf-Timer: 15 min" }).click();
  await page.getByRole("menuitemradio", { name: "Aus" }).click();
  await expect(page.getByRole("button", { name: "Schlaf-Timer", exact: true })).toBeVisible();
});

test("the downloads page always offers to add a video", async ({ page }) => {
  await signIn(page);
  await page.goto("/downloads");
  await page.getByRole("main").getByRole("button", { name: "Video hinzufügen" }).first().click();
  await expect(page.getByRole("dialog", { name: "Video hinzufügen" })).toBeVisible();
});

test("a playback preference survives a reload", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings");
  const toggle = page.getByRole("switch", { name: "Lautstärke angleichen" });
  const before = await toggle.getAttribute("aria-checked");
  await toggle.click();
  const after = before === "true" ? "false" : "true";
  await expect(toggle).toHaveAttribute("aria-checked", after);
  await page.reload();
  await expect(toggle).toHaveAttribute("aria-checked", after);
  await toggle.click(); // back as it was
  await expect(toggle).toHaveAttribute("aria-checked", before ?? "true");
});

test("download settings are saved without a save button", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings");
  const quality = page.getByLabel("Auflösung", { exact: true });
  await expect(quality).toHaveValue(""); // best available by default
  await quality.selectOption("1080");
  await expect(page.getByText("Gespeichert", { exact: true })).toBeVisible();
  await page.reload();
  await expect(quality).toHaveValue("1080");
  await quality.selectOption(""); // back as it was
  await expect(page.getByText("Gespeichert", { exact: true }).first()).toBeVisible();
  await page.reload();
  await expect(quality).toHaveValue("");
});

test("the TV view works with the arrow keys", async ({ page }) => {
  await signIn(page);
  await page.goto("/tv");
  await expect(page.getByText("Weiterschauen").first()).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowRight");
  const focused = page.locator(":focus");
  await expect(focused).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/tv\/(play|channels|playlists)\//);
});

test("a kids profile only sees its channels", async ({ page, browser }) => {
  await signIn(page);
  const channels = (await (await page.request.get("/api/channels")).json()) as {
    id: number;
    name: string;
  }[];
  const allowed = channels[0];
  const created = await page.request.post("/api/users", {
    headers: CSRF,
    data: {
      username: `kind${Date.now()}`,
      password: "kinder-passwort",
      channel_access: "selected",
      channel_ids: [allowed.id],
      may_add: false,
    },
  });
  expect(created.status()).toBe(201);
  const kid = (await created.json()) as { username: string; can_add: boolean };
  expect(kid.can_add).toBe(false);
  // The admin has the add button on the library page …
  await page.goto("/library");
  await expect(page.getByRole("button", { name: "Video hinzufügen" })).toBeVisible();

  const context = await browser.newContext();
  const kidPage = await context.newPage();
  await signIn(kidPage, { username: kid.username, password: "kinder-passwort" });
  await kidPage.goto("/channels");
  await expect(kidPage.getByText(allowed.name).first()).toBeVisible();
  for (const other of channels.slice(1)) {
    await expect(kidPage.getByText(other.name)).toHaveCount(0);
  }
  // … the watch-only kid doesn't, and the library only holds the allowed channel.
  await kidPage.goto("/library");
  await expect(kidPage.getByRole("heading", { level: 1, name: "Bibliothek" })).toBeVisible();
  await expect(kidPage.getByRole("button", { name: "Video hinzufügen" })).toHaveCount(0);
  await context.close();
});
