import { expect, test } from "@playwright/test";
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";

const repository = resolve(__dirname, "..");
const workspace = resolve(repository, "..");
const originals = join(workspace, ".local-diagnostics", "creator-cards-20260927");
const manifestPath = join(originals, "manifest.json");
const allCardsAvailable = existsSync(manifestPath) && ["Seraphina.png", "Sakana.png", "FluxTheCat.png"]
  .every((name) => existsSync(join(originals, name)));

test.describe("real card upload through Next and isolated contributor backend", () => {
  test.skip(!allCardsAvailable, "the three external card originals are not available in this checkout");

  let backend: ChildProcess | undefined;
  let frontend: ChildProcess | undefined;
  let backendLog = () => "";
  let frontendLog = () => "";
  let base = "";
  let dataRoot = "";

  test.beforeAll(async () => {
    const backendPort = await availablePort();
    const frontendPort = await availablePort();
    const backendUrl = `http://127.0.0.1:${backendPort}`;
    base = `http://127.0.0.1:${frontendPort}`;
    dataRoot = mkdtempSync(join(tmpdir(), "angmoo-card-upload-"));

    const python = process.env.ANGMOO_CARD_TEST_PYTHON ?? join(repository, "backend", ".venv",
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
    if (!existsSync(python)) throw new Error("isolated test backend Python is unavailable");
    backend = spawn(python, ["-m", "uvicorn",
      "app.runtime.contributor_backend:create_contributor_runtime_app_from_environment",
      "--factory", "--host", "127.0.0.1", "--port", String(backendPort)], {
      cwd: join(repository, "backend"),
      env: {
        ...process.env,
        ANGMOO_CONTRIBUTOR_DATA_ROOT: dataRoot,
        ANGMOO_FRONTEND_ORIGIN: base,
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    backendLog = captureOutput(backend);
    await ready(backendUrl + "/health", () => backend!, backendLog, 120_000);

    const nextCli = join(repository, "frontend", "node_modules", "next", "dist", "bin", "next");
    frontend = spawn(process.execPath,
      [nextCli, "dev", "--hostname", "127.0.0.1", "--port", String(frontendPort)], {
        cwd: join(repository, "frontend"),
        env: {
          ...process.env,
          ANGMOO_API_BASE_URL: backendUrl,
          NEXT_TELEMETRY_DISABLED: "1",
        },
        stdio: ["ignore", "pipe", "pipe"],
      });
    frontendLog = captureOutput(frontend);
    await ready(base + "/", () => frontend!, frontendLog, 120_000);
  });

  test.afterAll(async () => {
    if (frontend) await stopChild(frontend);
    if (backend) await stopChild(backend);
    if (dataRoot) console.log(`Isolated card upload data root: ${dataRoot}`);
  });

  test("Sakana, Seraphina and Flux pass the browser upload and preserve their original bytes", async ({ page }) => {
    const frontOrigin = { Origin: base, "Sec-Fetch-Site": "same-origin" };
    const bootstrap = await page.request.get(base + "/api/backend/auth/local/bootstrap");
    expect(bootstrap.status(), await bootstrap.text()).toBe(200);
    expect((await bootstrap.json()).state).toBe("unclaimed");
    const challenge = await page.request.post(base + "/api/backend/auth/local/bootstrap/challenge", {
      headers: frontOrigin,
      data: {},
    });
    expect(challenge.status(), await challenge.text()).toBe(201);
    const claim = await page.request.post(base + "/api/backend/auth/local/bootstrap/claim", {
      headers: frontOrigin,
      data: { display_name: "Card Test Owner", local_label: "Isolated Card Test", privacy_acknowledged: true },
    });
    expect(claim.status(), await claim.text()).toBe(201);

    const items = JSON.parse(readFileSync(manifestPath, "utf8")) as Array<{
      name: string; bytes: number; sha256: string;
    }>;
    const cards = ["Sakana", "Seraphina", "FluxTheCat"];
    for (const name of cards) {
      const record = items.find((card) => card.name === name);
      expect(record).toBeTruthy();
      const filePath = join(originals, name + ".png");
      const original = readFileSync(filePath);
      expect(original.byteLength).toBe(record!.bytes);
      expect(createHash("sha256").update(original).digest("hex")).toBe(record!.sha256.toLowerCase());

      await page.goto(base + "/agents/new");
      await expect(page.getByLabel("만드는 방법", { exact: true })).toBeVisible();
      await page.getByLabel("만드는 방법", { exact: true }).selectOption("card");
      const uploaded = page.waitForResponse((response) =>
        /^\/api\/backend\/agents\/drafts\/[^/]+\/card$/.test(new URL(response.url()).pathname)
        && response.request().method() === "POST");
      await page.getByLabel("캐릭터 카드 PNG 또는 JSON", { exact: true }).setInputFiles(filePath);
      const response = await uploaded;
      expect(response.status(), `${basename(filePath)}: ${await response.text()}`).toBe(200);
      const result = await response.json() as { card_version: number; draft: {
        id: string; name: string; source_kind: string; revision: number; avatar_temp_url: string | null;
      }};
      expect(result.card_version).toBe(name === "Seraphina" ? 3 : 2);
      expect(result.draft.name).toBe(name === "FluxTheCat" ? "Flux the Cat" : name);
      expect(result.draft.source_kind).toBe("card");
      expect(result.draft.revision).toBe(2);
      expect(result.draft.avatar_temp_url).toBeTruthy();
      await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue(result.draft.name);

      const source = await page.request.get(base + `/api/backend/agents/drafts/${encodeURIComponent(result.draft.id)}/card-source`);
      expect(source.status(), await source.text()).toBe(200);
      expect((await source.json()).sha256).toBe(record!.sha256.toLowerCase());
      const reloaded = await page.request.get(base + `/api/backend/agents/drafts/${encodeURIComponent(result.draft.id)}`);
      expect(reloaded.status(), await reloaded.text()).toBe(200);
      expect((await reloaded.json()).revision).toBe(result.draft.revision);

      if (name === "Sakana") {
        const cardUrl = base + `/api/backend/agents/drafts/${encodeURIComponent(result.draft.id)}/card`;
        const tooLarge = await page.request.post(cardUrl, {
          headers: frontOrigin,
          data: Buffer.alloc(28_000_000 + 256 * 1024 + 1, 0x61),
        });
        expect(tooLarge.status()).toBe(413);
        expect(await tooLarge.json()).toEqual({ detail: "Request body exceeds the allowed limit." });
        const afterReject = await page.request.get(base + `/api/backend/agents/drafts/${encodeURIComponent(result.draft.id)}`);
        expect((await afterReject.json()).revision).toBe(result.draft.revision);
        const sourceAfterReject = await page.request.get(base + `/api/backend/agents/drafts/${encodeURIComponent(result.draft.id)}/card-source`);
        expect((await sourceAfterReject.json()).sha256).toBe(record!.sha256.toLowerCase());
      }

      await page.evaluate(() => sessionStorage.removeItem("angmoo.creation.v2:default"));
    }
  });
});

function captureOutput(child: ChildProcess): () => string {
  let output = "";
  for (const stream of [child.stdout, child.stderr]) {
    stream?.on("data", (chunk: Buffer) => { output = (output + chunk.toString()).slice(-4_000); });
  }
  return () => output;
}

async function ready(url: string, child: () => ChildProcess, output: () => string, timeout: number) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (child().exitCode !== null) throw new Error(`Isolated service exited: ${child().exitCode}\n${output()}`);
    try {
      const response = await fetch(url, { redirect: "manual" });
      if (response.status > 0) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`Isolated service did not start: ${url}\n${output()}`);
}

async function availablePort(): Promise<number> {
  const server = createServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Failed to allocate local port");
  server.close();
  await once(server, "close");
  return address.port;
}

async function stopChild(child: ChildProcess) {
  if (child.exitCode !== null || child.pid === undefined) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    child.kill("SIGTERM");
  }
  await Promise.race([once(child, "exit"), new Promise((resolve) => setTimeout(resolve, 5_000))]);
}
