import { expect, test, type APIResponse, type Response } from "@playwright/test";
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
type CardRecord = { name: string; bytes: number; sha256: string; file?: string; characterName?: string; version?: number; worldviewLength?: number };
type CardDataset = { label: string; directory: string; available: boolean; duplicate?: boolean; records?: CardRecord[] };
const userDirectory = process.env.ANGMOO_CARD_ORIGINAL_DIR ?? "";
const userRecords: CardRecord[] = [
  { name: "Red", file: "main_red-69957f8d_spec_v2.png", bytes: 1680504, sha256: "815c2e52205e73430cab1ae42aeef092a3e9400cecbe05c7790584d65e328b1b", worldviewLength: 3362 },
  { name: "Raymond", file: "main_overprotective-father-raymond-610a34d02145_spec_v2.png", bytes: 2071527, sha256: "d9507f310ae2c228ad23bc4e8af0f74513cbc6bdbff4173b1f58241911798bca", worldviewLength: 6847 },
  { name: "Elias Finch", file: "main_elias-da06fb375f61_spec_v2.png", bytes: 3885093, sha256: "c29ac8b9a9210af235de2e1f8081aa72a6d5f4c22c167a043dc19bf12466e23f", worldviewLength: 6520 },
];
const datasets: CardDataset[] = [
  { label: "synthetic", directory: synthetic, available: true },
  { label: "synthetic duplicates", directory: createSyntheticCards(true), available: true, duplicate: true },
  { label: "user duplicate originals", directory: userDirectory, available: Boolean(userDirectory) && userRecords.every((item) => existsSync(join(userDirectory, item.file!))), duplicate: true, records: userRecords },
  { label: "external originals", directory: originals, available: allCardsAvailable },
];
for (const dataset of datasets) {
test.describe(`${dataset.label} card upload through Next and isolated contributor backend`, () => {
  test.skip(!dataset.available, "optional external card originals are not available in this checkout");

  let backend: ChildProcess | undefined;
  let frontend: ChildProcess | undefined;
  let backendLog = () => "";
  let frontendLog = () => "";
  let base = "";
  let backendBase = "";
  let dataRoot = "";

  test.beforeAll(async () => {
    const backendPort = await availablePort();
    const frontendPort = await availablePort();
    const backendUrl = `http://127.0.0.1:${backendPort}`;
    backendBase = backendUrl;
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
      detached: process.platform !== "win32",
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
        detached: process.platform !== "win32",
        stdio: ["ignore", "pipe", "pipe"],
      });
    frontendLog = captureOutput(frontend);
    console.log(`Owned card test services: backend=${backend.pid}:${backendPort}, frontend=${frontend.pid}:${frontendPort}`);
    await ready(base + "/", () => frontend!, frontendLog, 120_000);
  });

  test.afterAll(async () => {
    try {
      if (frontend) await stopChild(frontend);
    } finally {
      if (backend) await stopChild(backend);
    }
    for (const address of [base, backendBase]) {
      await expect.poll(async () => {
        try { await fetch(address, { signal: AbortSignal.timeout(500) }); return true; }
        catch { return false; }
      }).toBe(false);
    }
    if (dataRoot) console.log(`Isolated card upload data root: ${dataRoot}`);
  });

  test("cards pass upload, metadata restore and registration without changing originals", async ({ page }) => {
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

    const items: CardRecord[] = dataset.records ?? JSON.parse(readFileSync(join(dataset.directory, "manifest.json"), "utf8"));
    for (const record of items) {
      const name = record.name;
      const filePath = join(dataset.directory, record.file ?? name + ".png");
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
      const result = await response.json() as { card_version: number; metadata_selection: { multiple_definitions: boolean; same_keyword_count: number }; draft: {
        id: string; name: string; worldview: string; source_kind: string; revision: number; avatar_temp_url: string | null;
      }};
      expect(result.card_version).toBe(record.version ?? (name === "Seraphina" ? 3 : 2));
      expect(result.draft.name).toBe(record.characterName ?? (name === "FluxTheCat" ? "Flux the Cat" : name));
      if (record.worldviewLength) expect(result.draft.worldview.length).toBe(record.worldviewLength);
      expect(result.draft.source_kind).toBe("card");
      expect(result.draft.revision).toBe(2);
      expect(result.draft.avatar_temp_url).toBeTruthy();
      await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue(result.draft.name);
      if (dataset.duplicate) {
        expect(result.metadata_selection.same_keyword_count).toBe(2);
        expect(result.metadata_selection.multiple_definitions).toBe(true);
        const notice = page.getByRole("status").filter({ hasText: "같은 형식의 캐릭터 정의가 여러 개" });
        await expect(notice).toBeVisible();
        const restored = page.waitForResponse((item) => item.url().includes("/card-source?include_document=false"));
        await page.reload();
        const summary = await restored;
        expect(summary.status()).toBe(200);
        expect((await summary.json()).document).toBeNull();
        await expect(notice).toBeVisible();
        await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue(result.draft.name);
        // Existing replace confirmation still protects edits; duplicates need no extra approval.
        await page.getByRole("textbox", { name: "이름", exact: true }).fill(result.draft.name + " edited");
        await page.getByRole("button", { name: "이전", exact: true }).click();
        await page.getByLabel("캐릭터 카드 PNG 또는 JSON", { exact: true }).setInputFiles(filePath);
        await expect(page.getByText("현재 편집 내용을 이 카드의 설정으로 교체할까요?", { exact: true })).toBeVisible();
        await page.getByRole("button", { name: "취소", exact: true }).click();
        await expect(page.getByRole("button", { name: "교체하기", exact: true })).toHaveCount(0);
        await page.getByLabel("만드는 방법", { exact: true }).selectOption("direct");
        await expect(notice).toHaveCount(0);
        await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
        await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue(result.draft.name + " edited");
        await page.getByRole("button", { name: "이전", exact: true }).click();
        await page.getByLabel("만드는 방법", { exact: true }).selectOption("card");
        await expect(notice).toBeVisible();
        await page.getByRole("button", { name: "나중에 하기", exact: true }).click();
        await page.goto(base + "/agents/new");
        // Unsaved edits are not silently applied to the stored original draft.
        await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue(result.draft.name);
        await expect(notice).toBeVisible();
      }

      const source = await page.request.get(base + `/api/backend/agents/drafts/${encodeURIComponent(result.draft.id)}/card-source`);
      expect(source.status(), await source.text()).toBe(200);
      expect((await source.json()).sha256).toBe(record!.sha256.toLowerCase());
      expect(source.headers()["cache-control"]).toBe("private, no-store");
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

      let completed: APIResponse | Response;
      if (dataset.duplicate) {
        const avatarResponse = page.waitForResponse((item) => new URL(item.url()).pathname.endsWith(`/agents/drafts/${result.draft.id}/media/avatar`));
        await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
        const media = await avatarResponse;
        expect(media.status()).toBe(200);
        expect(media.headers()["content-type"]).toContain("image/webp");
        const avatar = page.getByRole("img", { name: `${result.draft.name} 프로필 이미지`, exact: true });
        await expect(avatar).toBeVisible();
        const image = avatar.locator("img");
        await expect(image).toBeVisible();
        await expect.poll(() => image.evaluate((node: HTMLImageElement) => node.complete && node.naturalWidth > 0)).toBe(true);
        await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
        const registration = page.waitForResponse((item) => item.request().method() === "POST"
          && new URL(item.url()).pathname.endsWith(`/agents/drafts/${result.draft.id}/complete`));
        await page.getByRole("button", { name: "자율활동 OFF로 등록", exact: true }).click();
        completed = await registration;
        await expect(page.getByRole("heading", { name: `${result.draft.name} 등록 완료`, exact: true })).toBeVisible();
      } else {
        completed = await page.request.post(base + `/api/backend/agents/drafts/${encodeURIComponent(result.draft.id)}/complete`, {
          headers: frontOrigin, data: { revision: result.draft.revision },
        });
      }
      expect(completed.status(), await completed.text()).toBe(200);
      const character = (await completed.json()).character;
      expect(createHash("sha256").update(readFileSync(filePath)).digest("hex")).toBe(record.sha256.toLowerCase());
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

test("isolated service cleanup closes its descendant server before another build", async () => {
  const port = await availablePort();
  const url = `http://127.0.0.1:${port}`;
  const descendant = `require('node:http').createServer((_, response) => response.end('ready')).listen(${port}, '127.0.0.1');`;
  const parent = `require('node:child_process').spawn(process.execPath, ['-e', ${JSON.stringify(descendant)}], { stdio: 'inherit' }); setInterval(() => {}, 1000);`;
  const child = spawn(process.execPath, ["-e", parent], {
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });
  const output = captureOutput(child);
  try {
    await ready(url, () => child, output, 15_000);
    await stopChild(child);
    await expect.poll(async () => {
      try {
        await fetch(url, { signal: AbortSignal.timeout(500) });
        return true;
      } catch {
        return false;
      }
    }).toBe(false);
  } finally {
    await stopChild(child);
  }
});

function createSyntheticCards(duplicate = false): string {
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
    if (duplicate) {
      const other = { ...document, data: { ...document.data, name: "Unused alternative", description: "Must never replace or merge the first definition." } };
      parts.push(pngChunk("tEXt", Buffer.from(`${version === 3 ? "CCV3" : "CHARA"}\0${Buffer.from(JSON.stringify(other)).toString("base64")}`)));
    }
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
  const pid = child.pid;
  if (pid === undefined) return;
  const exited = child.exitCode !== null || child.signalCode !== null;
  if (process.platform === "win32" && exited) return;
  // On Windows an inherited pipe can delay 'close' after the owned tree exits.
  const closed = exited ? Promise.resolve() : once(child, "exit");
  const signal = (value: NodeJS.Signals) => {
    if (process.platform === "win32") {
      const result = spawnSync("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore" });
      if (result.error || result.status !== 0) {
        // Windows can remove the process before Node receives its exit event.
        // Accept that race only after an OS liveness check confirms this PID is gone.
        try { process.kill(pid, 0); }
        catch (error) {
          if ((error as NodeJS.ErrnoException).code === "ESRCH") return;
          throw error;
        }
        throw new Error("Isolated service tree shutdown failed");
      }
    } else {
      try {
        // Every owned service starts in its own group. Next forks a worker;
        // terminating only the CLI can leave it writing dev type artifacts.
        process.kill(-pid, value);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
      }
    }
  };
  const waitClosed = async (milliseconds: number) => {
    let timer: NodeJS.Timeout | undefined;
    try {
      return await Promise.race([
        closed.then(() => true),
        new Promise<boolean>((resolve) => { timer = setTimeout(() => resolve(false), milliseconds); }),
      ]);
    } finally {
      clearTimeout(timer);
    }
  };
  signal("SIGTERM");
  if (!await waitClosed(5_000)) {
    signal("SIGKILL");
    if (!await waitClosed(5_000)) {
      try { process.kill(pid, 0); }
      catch (error) { if ((error as NodeJS.ErrnoException).code === "ESRCH") return; throw error; }
      throw new Error("Isolated service shutdown timed out");
    }
  }
}
