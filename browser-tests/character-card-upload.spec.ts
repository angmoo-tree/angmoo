import { expect, test } from "@playwright/test";
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { deflateSync } from "node:zlib";

const repository = resolve(__dirname, "..");
const workspace = resolve(repository, "..");
const originals = join(workspace, ".local-diagnostics", "creator-cards-20260927");
const manifestPath = join(originals, "manifest.json");
const allCardsAvailable = existsSync(manifestPath) && ["Seraphina.png", "Sakana.png", "FluxTheCat.png"]
  .every((name) => existsSync(join(originals, name)));

// Required public CI uses self-contained, authored fixtures. Optional external
// originals still run the identical byte-preservation and registration checks.
const synthetic = createSyntheticCards();
for (const dataset of [
  { label: "synthetic", directory: synthetic, available: true },
  { label: "external originals", directory: originals, available: allCardsAvailable },
]) {
test.describe(`${dataset.label} card upload through Next and isolated contributor backend`, () => {
  test.skip(!dataset.available, "optional external card originals are not available in this checkout");

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
        DAILY_PREPARATION_ENABLED: "true",
        ANGMOO_FRONTEND_ORIGIN: base,
        RESIDENT_TICK_SCHEDULER_ENABLED: "false",
        POST_IMAGE_JOB_WORKER_ENABLED: "false",
        POLLINATIONS_SERVICE_IMAGE_ENABLED: "false",
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

    const items = JSON.parse(readFileSync(join(dataset.directory, "manifest.json"), "utf8")) as Array<{
      name: string; bytes: number; sha256: string;
    }>;
    const cards = ["Sakana", "Seraphina", "FluxTheCat"];
    for (const name of cards) {
      const record = items.find((card) => card.name === name);
      expect(record).toBeTruthy();
      const filePath = join(dataset.directory, name + ".png");
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
        id: string; name: string; worldview: string; source_kind: string; revision: number; avatar_temp_url: string | null;
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
      const rawDraft = await reloaded.json();
      expect(rawDraft.revision).toBe(result.draft.revision);
      await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
      // Textarea DOM normalizes CRLF; the stored draft and card bytes below do not.
      await expect(page.getByRole("textbox", { name: "캐릭터 설명", exact: true })).toHaveValue(rawDraft.worldview.replace(/\r\n?/g, "\n"));
      await expect(page.getByText("{{user}}는 활동할 때 이 World의 내 프로필 이름으로", { exact: false })).toBeVisible();
      const savedDraft = await page.request.get(base + `/api/backend/agents/drafts/${encodeURIComponent(result.draft.id)}`);
      const saved = await savedDraft.json();
      expect(saved.worldview).toBe(rawDraft.worldview);
      result.draft.revision = saved.revision;

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

      const completed = await page.request.post(base + `/api/backend/agents/drafts/${encodeURIComponent(result.draft.id)}/complete`, {
        headers: frontOrigin, data: { revision: result.draft.revision },
      });
      expect(completed.status(), await completed.text()).toBe(200);
      const character = (await completed.json()).character;
      const worlds = await page.request.post(base + "/api/backend/worlds/default-space/ensure", { headers: frontOrigin, data: {} });
      expect(worlds.status(), await worlds.text()).toBe(200);
      const world = await worlds.json();
      const prepared = await page.request.get(base + `/api/backend/characters/${character.id}/worlds/${world.id}/daily-preparation`);
      expect(prepared.status(), await prepared.text()).toBe(200);
      expect((await prepared.json()).plan_state).toBe("pending");
      expect((await prepared.json()).topic_state).toBe("pending");
      expect((await completed.json()).settings.auto_enabled).toBe(false);
      const withoutKey = await page.request.post(base + `/api/backend/characters/${character.id}/worlds/${world.id}/daily-preparation`, {
        headers: frontOrigin, data: { request_id: `missing-key-${name}` },
      });
      expect(withoutKey.status(), await withoutKey.text()).toBe(409);
      expect(await withoutKey.json()).toEqual({ detail: "preparation_credential_unavailable" });
      const afterFailedPrepare = await page.request.get(base + `/api/backend/characters/${character.id}/worlds/${world.id}/daily-preparation`);
      expect((await afterFailedPrepare.json()).request_id).toBeNull();
      expect((await afterFailedPrepare.json()).plan_state).toBe("pending");

      if (name === "Sakana") {
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto(base + `/agents/${encodeURIComponent(character.id)}?tab=settings`);
        await expect(page.getByRole("textbox", { name: "캐릭터 설명", exact: true })).toHaveValue(saved.worldview.replace(/\r\n?/g, "\n"));
        await expect(page.getByText("{{user}}는 활동할 때 이 World의 내 프로필 이름으로", { exact: false })).toBeVisible();
        await expect(page.getByRole("textbox", { name: "캐릭터 설명", exact: true })).not.toHaveAttribute("required", "");
        const macroSource = "{{char}}의 동료: {{user}}. 입력 원문은 그대로 저장합니다.";
        await page.getByRole("textbox", { name: "캐릭터 설명", exact: true }).fill(macroSource);
        const savedPersona = page.waitForResponse((response) => response.request().method() === "PUT"
          && new URL(response.url()).pathname.endsWith(`/agents/${character.id}/persona`));
        await page.getByRole("button", { name: "페르소나 저장", exact: true }).click();
        expect((await savedPersona).status()).toBe(200);
        await page.reload();
        await expect(page.getByRole("textbox", { name: "캐릭터 설명", exact: true })).toHaveValue(macroSource);

        await page.goto(base + `/agents/new?worldId=${encodeURIComponent(world.id)}`);
        await page.getByLabel("만드는 방법", { exact: true }).selectOption("card");
        const worldUpload = page.waitForResponse((response) => response.request().method() === "POST"
          && /^\/api\/backend\/agents\/drafts\/[^/]+\/card$/.test(new URL(response.url()).pathname));
        await page.getByLabel("캐릭터 카드 PNG 또는 JSON", { exact: true }).setInputFiles(filePath);
        expect((await worldUpload).status()).toBe(200);
        await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
        await expect(page.getByRole("textbox", { name: "캐릭터 설명", exact: true })).toHaveValue(saved.worldview.replace(/\r\n?/g, "\n"));
        await expect(page.getByText("{{user}}는 활동할 때 이 World의 내 프로필 이름으로", { exact: false })).toBeVisible();
        await page.getByRole("textbox", { name: "캐릭터 설명", exact: true }).focus();
        await page.keyboard.press("Tab");
        await expect(page.getByRole("textbox", { name: "캐릭터 설명", exact: true })).not.toBeFocused();
        await page.setViewportSize({ width: 1280, height: 900 });
      }

      await page.evaluate(() => sessionStorage.removeItem("angmoo.creation.v2:default"));
    }
  });
});
}

function createSyntheticCards(): string {
  const directory = mkdtempSync(join(tmpdir(), "angmoo-synthetic-cards-"));
  const records = [
    { name: "Seraphina", bytes: 551_901, version: 3 },
    { name: "Sakana", bytes: 1_433_772, version: 2 },
    { name: "FluxTheCat", bytes: 612_357, version: 2 },
  ].map(({ name, bytes, version }) => {
    const document = { spec: `chara_card_v${version}`, spec_version: `${version}.0`, data: {
      name: name === "FluxTheCat" ? "Flux the Cat" : name,
      description: "A synthetic character for upload, preservation and registration tests.",
      personality: "Curious", scenario: "A shared local SNS", first_mes: "Hello!", mes_example: "Hello!",
    } };
    const header = Buffer.alloc(13);
    header.writeUInt32BE(1, 0); header.writeUInt32BE(1, 4);
    header[8] = 8; header[9] = 2; // One RGB pixel, no interlace.
    const metadata = Buffer.from(`${version === 3 ? "ccv3" : "chara"}\0${Buffer.from(JSON.stringify(document)).toString("base64")}`);
    const parts = [Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
      pngChunk("IHDR", header), pngChunk("tEXt", metadata),
      pngChunk("IDAT", deflateSync(Buffer.from([0, 16, 32, 48])))];
    const overhead = parts.reduce((sum, part) => sum + part.length, 0) + 24;
    const content = Buffer.concat([...parts, pngChunk("npAD", Buffer.alloc(bytes - overhead)), pngChunk("IEND", Buffer.alloc(0))]);
    if (content.length !== bytes) throw new Error("Synthetic card length differs");
    writeFileSync(join(directory, name + ".png"), content);
    return { name, bytes, sha256: createHash("sha256").update(content).digest("hex") };
  });
  writeFileSync(join(directory, "manifest.json"), JSON.stringify(records));
  return directory;
}

function pngChunk(kind: string, data: Buffer): Buffer {
  const value = Buffer.concat([Buffer.from(kind, "ascii"), data]);
  let crc = 0xffffffff;
  for (const byte of value) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  const result = Buffer.alloc(data.length + 12);
  result.writeUInt32BE(data.length, 0); value.copy(result, 4);
  result.writeUInt32BE((crc ^ 0xffffffff) >>> 0, result.length - 4);
  return result;
}

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
