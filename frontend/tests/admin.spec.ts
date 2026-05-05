import { test, expect, type Page, type Route } from "@playwright/test";

/**
 * Helper: build a CorpusState payload with sensible defaults.
 */
function corpusPayload(overrides: {
  doc_count?: number;
  chunk_count?: number;
  embedding_model?: string;
  embedding_model_version?: string;
  last_indexed_at?: string | null;
  docs?: Array<{
    id: string;
    doc_section: string;
    source_url: string;
    chunk_count: number;
    ingested_at: string;
  }>;
  chunking_config?: { chunk_size: number; overlap: number };
}) {
  return {
    doc_count: overrides.doc_count ?? 3,
    chunk_count: overrides.chunk_count ?? 4381,
    embedding_model: overrides.embedding_model ?? "voyage-code-3",
    embedding_model_version:
      overrides.embedding_model_version ?? "voyage-code-3@2025-09",
    last_indexed_at:
      overrides.last_indexed_at !== undefined
        ? overrides.last_indexed_at
        : "2026-05-05T11:42:00Z",
    docs:
      overrides.docs ?? [
        {
          id: "claude-docs/authentication",
          doc_section: "auth",
          source_url: "https://docs.anthropic.com/en/api/auth",
          chunk_count: 84,
          ingested_at: "2026-05-05T11:30:00Z",
        },
        {
          id: "claude-docs/messages",
          doc_section: "messages",
          source_url: "https://docs.anthropic.com/en/api/messages",
          chunk_count: 211,
          ingested_at: "2026-05-05T11:32:00Z",
        },
        {
          id: "claude-docs/tool-use",
          doc_section: "tools",
          source_url: "https://docs.anthropic.com/en/api/tool-use",
          chunk_count: 92,
          ingested_at: "2026-05-05T11:35:00Z",
        },
      ],
    chunking_config: overrides.chunking_config ?? {
      chunk_size: 900,
      overlap: 100,
    },
  };
}

const JOB_ID_RUNNING = "55555555-5555-5555-5555-555555555555";

interface AdminCalls {
  ingestPosts: Array<unknown>;
  chunkingPatches: Array<unknown>;
}

/**
 * Stub /admin/* routes. Returns capture arrays so tests can assert on
 * request bodies. The corpus payload returned by GET /admin/corpus is
 * controlled by the `corpus` arg.
 */
async function stubAdmin(
  page: Page,
  opts: {
    corpus?: ReturnType<typeof corpusPayload>;
    ingestStatus?: {
      ingest_job_id: string;
      status: "queued" | "running" | "succeeded" | "failed";
      started_at: string | null;
      finished_at: string | null;
      docs_processed: number;
      docs_total: number | null;
      chunks_written: number;
      progress: number;
      error?: string;
    };
  },
): Promise<AdminCalls> {
  const ingestPosts: Array<unknown> = [];
  const chunkingPatches: Array<unknown> = [];

  await page.route("**/admin/corpus", async (route: Route) => {
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts.corpus ?? corpusPayload({})),
    });
  });

  await page.route("**/admin/ingest", async (route: Route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postData();
      try {
        ingestPosts.push(body ? JSON.parse(body) : null);
      } catch {
        ingestPosts.push(body);
      }
      await route.fulfill({
        status: 202,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ingest_job_id: JOB_ID_RUNNING,
          status: "queued",
        }),
      });
      return;
    }
    await route.continue();
  });

  await page.route("**/admin/ingest/*", async (route: Route) => {
    const status = opts.ingestStatus ?? {
      ingest_job_id: JOB_ID_RUNNING,
      status: "running" as const,
      started_at: new Date().toISOString(),
      finished_at: null,
      docs_processed: 18,
      docs_total: 52,
      chunks_written: 1243,
      progress: 0.35,
    };
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(status),
    });
  });

  await page.route("**/admin/chunking-config", async (route: Route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postData();
      let parsed: unknown = null;
      try {
        parsed = body ? JSON.parse(body) : null;
      } catch {
        parsed = body;
      }
      chunkingPatches.push(parsed);
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
      });
      return;
    }
    await route.continue();
  });

  return { ingestPosts, chunkingPatches };
}

test.describe("Admin page", () => {
  test("renders 4 KPI cards with the expected labels (ADMN-01)", async ({
    page,
  }) => {
    await stubAdmin(page, {});
    await page.goto("/admin");

    await expect(page.getByRole("heading", { name: "Corpus" })).toBeVisible();
    // Tremor Title text is uppercase via class; we assert the label text.
    await expect(page.getByText("DOCUMENTS", { exact: true })).toBeVisible();
    await expect(page.getByText("CHUNKS", { exact: true })).toBeVisible();
    await expect(
      page.getByText("EMBEDDING MODEL", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("LAST INDEXED", { exact: true })).toBeVisible();
  });

  test("renders the doc list with a row per doc (ADMN-01)", async ({ page }) => {
    await stubAdmin(page, {});
    await page.goto("/admin");

    // Wait for cards before checking rows so the corpus query has settled.
    await expect(page.getByText("DOCUMENTS", { exact: true })).toBeVisible();

    const rows = page.locator('[data-testid="doc-row"]');
    await expect(rows).toHaveCount(3);
    await expect(
      page.getByText("claude-docs/authentication"),
    ).toBeVisible();
    await expect(page.getByText("claude-docs/messages")).toBeVisible();
    await expect(page.getByText("claude-docs/tool-use")).toBeVisible();
  });

  test("re-index button is two-tap and starts polling (ADMN-02)", async ({
    page,
  }) => {
    const { ingestPosts } = await stubAdmin(page, {});
    await page.goto("/admin");

    const btn = page.getByTestId("reindex-button");
    await expect(btn).toBeVisible();
    await expect(btn).toHaveText(/Re-index corpus/);

    // First click — confirm state.
    await btn.click();
    await expect(btn).toHaveText(/Click again to confirm/);

    // Second click within 3s — fires POST /admin/ingest and transitions to running.
    await btn.click();
    await expect(btn).toHaveText(/Indexing/);

    // Confirm POST happened.
    await expect.poll(() => ingestPosts.length).toBeGreaterThanOrEqual(1);
    expect(ingestPosts[0]).toEqual({ source: "claude-docs" });

    // Polling kicks in — IngestProgress is rendered with status text.
    await expect(page.getByTestId("ingest-progress")).toBeVisible();
  });

  test("re-index progress UI shows docs/chunks counts (ADMN-02)", async ({
    page,
  }) => {
    await stubAdmin(page, {
      ingestStatus: {
        ingest_job_id: JOB_ID_RUNNING,
        status: "running",
        started_at: new Date().toISOString(),
        finished_at: null,
        docs_processed: 18,
        docs_total: 52,
        chunks_written: 1243,
        progress: 0.35,
      },
    });
    await page.goto("/admin");

    const btn = page.getByTestId("reindex-button");
    await btn.click();
    await btn.click();

    // Counter row — load-bearing format strings.
    await expect(page.getByText(/18\s*\/\s*52\s*docs/)).toBeVisible();
    await expect(page.getByText(/1,243\s*chunks/)).toBeVisible();
  });

  test("chunking config form persists via PATCH (ADMN-03)", async ({ page }) => {
    const { chunkingPatches } = await stubAdmin(page, {});
    await page.goto("/admin");

    // Wait for the form to mount with initial values.
    const chunkSize = page.getByLabel("chunk_size");
    const overlap = page.getByLabel("overlap");
    await expect(chunkSize).toBeVisible();
    await chunkSize.fill("600");
    await overlap.fill("50");

    await page.getByRole("button", { name: /Save settings/i }).click();

    await expect.poll(() => chunkingPatches.length).toBeGreaterThanOrEqual(1);
    expect(chunkingPatches[0]).toEqual({ chunk_size: 600, overlap: 50 });

    // Success toast surfaces. (`.first()` to disambiguate the visible toast
    // body from the aria-live screen-reader announcer.)
    await expect(
      page.getByText(/Chunking settings saved/i).first(),
    ).toBeVisible();
  });

  test("URL ingest validates each line client-side (ADMN-04)", async ({
    page,
  }) => {
    const { ingestPosts } = await stubAdmin(page, {});
    await page.goto("/admin");

    const textarea = page.getByLabel("Ingest URLs");
    await expect(textarea).toBeVisible();
    await textarea.fill("not-a-url\nhttps://valid.com/x");

    await page.getByRole("button", { name: /Add URLs/i }).click();

    // Inline error visible; no POST sent.
    await expect(page.getByText(/Line 1: not a URL/)).toBeVisible();
    expect(ingestPosts.length).toBe(0);
  });

  test("URL ingest submits valid URLs (ADMN-04)", async ({ page }) => {
    const { ingestPosts } = await stubAdmin(page, {});
    await page.goto("/admin");

    const textarea = page.getByLabel("Ingest URLs");
    await textarea.fill(
      "https://docs.anthropic.com/en/api/messages\nhttps://docs.anthropic.com/en/api/auth",
    );
    await page.getByRole("button", { name: /Add URLs/i }).click();

    await expect.poll(() => ingestPosts.length).toBeGreaterThanOrEqual(1);
    const payload = ingestPosts[0] as { urls: string[] };
    expect(Array.isArray(payload.urls)).toBe(true);
    expect(payload.urls).toHaveLength(2);
    expect(payload.urls[0]).toBe("https://docs.anthropic.com/en/api/messages");
    expect(payload.urls[1]).toBe("https://docs.anthropic.com/en/api/auth");
  });

  test("empty corpus surfaces amber Callout banner (ADMN-01)", async ({
    page,
  }) => {
    await stubAdmin(page, {
      corpus: corpusPayload({
        doc_count: 0,
        chunk_count: 0,
        last_indexed_at: null,
        docs: [],
      }),
    });
    await page.goto("/admin");

    await expect(page.getByTestId("empty-corpus-banner")).toBeVisible();
    await expect(page.getByText(/No corpus yet/i)).toBeVisible();
    // Doc list shows the empty-state message.
    await expect(page.getByText("No documents indexed yet.")).toBeVisible();
  });
});
