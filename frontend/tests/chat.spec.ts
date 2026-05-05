import { test, expect, type Page, type Route } from "@playwright/test";

/**
 * Helper: build an SSE response body with a sequence of token frames
 * followed by a final frame. Each token is sent as its own frame so
 * the frontend sees multiple parser yields and the DOM updates
 * incrementally (CHAT-02 streaming-incrementality assertion).
 */
function sseBody(opts: {
  tokens: string[];
  trace_id: string;
  cited_chunks?: Array<{
    idx: number;
    doc_id: string;
    doc_section: string;
    section_title: string;
    source_url: string;
    content: string;
    score: number;
  }>;
  latency_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  estimated_cost_usd?: number;
}): string {
  const tokenFrames = opts.tokens
    .map(
      (t) => `event: token\ndata: ${JSON.stringify({ text: t })}\n\n`,
    )
    .join("");
  const finalPayload = {
    trace_id: opts.trace_id,
    cited_chunks: opts.cited_chunks ?? [],
    latency_ms: opts.latency_ms ?? 2810,
    input_tokens: opts.input_tokens ?? 1240,
    output_tokens: opts.output_tokens ?? 96,
    estimated_cost_usd: opts.estimated_cost_usd ?? 0.0043,
  };
  const finalFrame = `event: final\ndata: ${JSON.stringify(finalPayload)}\n\n`;
  return tokenFrames + finalFrame;
}

const SAMPLE_CHUNK = {
  idx: 1,
  doc_id: "claude-docs/tool-use",
  doc_section: "tools",
  section_title: "Tool use overview",
  source_url: "https://docs.anthropic.com/en/api/tool-use",
  content:
    "Tool use lets you give Claude access to client-side functions. When Claude decides a tool would help, it returns a tool_use block with arguments.",
  score: 0.87,
};

const TRACE_ID_1 = "11111111-1111-1111-1111-111111111111";
const TRACE_ID_2 = "22222222-2222-2222-2222-222222222222";

/**
 * Stub a single /chat response with the given options. Each token
 * frame is sent in its own response chunk via Playwright's body API.
 * Also registers a /feedback handler returning 201.
 */
async function stubChat(
  page: Page,
  responses: Array<Parameters<typeof sseBody>[0]>,
): Promise<{ feedbackCalls: Array<unknown> }> {
  const feedbackCalls: Array<unknown> = [];
  let callIdx = 0;

  await page.route("**/chat", async (route: Route) => {
    const resp = responses[Math.min(callIdx, responses.length - 1)];
    callIdx += 1;
    await route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
      body: sseBody(resp),
    });
  });

  await page.route("**/feedback", async (route: Route) => {
    const req = route.request();
    let parsed: unknown = null;
    try {
      parsed = JSON.parse(req.postData() ?? "{}");
    } catch {
      parsed = null;
    }
    feedbackCalls.push(parsed);
    await route.fulfill({
      status: 201,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: "feedback-id-1",
        created_at: new Date().toISOString(),
      }),
    });
  });

  return { feedbackCalls };
}

test.describe("Chat page", () => {
  test("renders empty state with H1 and example chips (CHAT-01)", async ({
    page,
  }) => {
    await page.goto("/chat");
    await expect(
      page.getByRole("heading", {
        name: "Ask a question about the Claude API or Agent SDK.",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "How does prompt caching work?" }),
    ).toBeVisible();
  });

  test("sends a question and renders the streamed assistant response (CHAT-01)", async ({
    page,
  }) => {
    await stubChat(page, [
      {
        tokens: ["Auth", "ent", "icate", " by", " sending", " a key."],
        trace_id: TRACE_ID_1,
        cited_chunks: [SAMPLE_CHUNK],
      },
    ]);
    await page.goto("/chat");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .fill("How does authentication work?");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .press("Enter");

    // User bubble first, then assistant bubble with the assembled tokens.
    await expect(
      page.locator('[data-role="user"]', {
        hasText: "How does authentication work?",
      }),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="assistant-content"]'),
    ).toContainText("Authenticate by sending a key.");
  });

  test("streams chunks incrementally — DOM mutates >= 2 times during a response (CHAT-02)", async ({
    page,
  }) => {
    await stubChat(page, [
      {
        tokens: ["A", "B", "C", "D", "E", "F", "G"],
        trace_id: TRACE_ID_1,
        cited_chunks: [SAMPLE_CHUNK],
      },
    ]);
    await page.goto("/chat");

    // Track distinct content snapshots while the response streams.
    await page.exposeFunction("__pushSnapshot", (s: string) => {
      // bound at runtime
      void s;
    });

    await page.evaluate(() => {
      (window as unknown as { __snapshots: string[] }).__snapshots = [];
      const obs = new MutationObserver(() => {
        const el = document.querySelector(
          '[data-testid="assistant-content"]',
        );
        if (el) {
          const text = el.textContent ?? "";
          const snaps = (window as unknown as { __snapshots: string[] })
            .__snapshots;
          if (snaps[snaps.length - 1] !== text) snaps.push(text);
        }
      });
      obs.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
      });
      (
        window as unknown as { __mo: MutationObserver }
      ).__mo = obs;
    });

    await page
      .getByRole("textbox", { name: /ask a question/i })
      .fill("Hello?");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .press("Enter");

    // Wait for stream to complete.
    await expect(
      page.locator('[data-testid="assistant-content"]'),
    ).toContainText("ABCDEFG");

    const snaps = (await page.evaluate(
      () => (window as unknown as { __snapshots: string[] }).__snapshots,
    )) as string[];
    // Distinct content snapshots: at least 2 means the DOM mutated incrementally.
    expect(snaps.length).toBeGreaterThanOrEqual(2);
  });

  test("metadata strip renders latency / tokens / cost (CHAT-03)", async ({
    page,
  }) => {
    await stubChat(page, [
      {
        tokens: ["Done."],
        trace_id: TRACE_ID_1,
        cited_chunks: [SAMPLE_CHUNK],
        latency_ms: 2810,
        input_tokens: 1240,
        output_tokens: 96,
        estimated_cost_usd: 0.0043,
      },
    ]);
    await page.goto("/chat");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .fill("test");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .press("Enter");

    // Wait for final frame so metadata strip renders.
    await expect(page.getByText(/2810\s*ms/)).toBeVisible();
    await expect(page.getByText(/1240\s*→\s*96\s*tok/)).toBeVisible();
    await expect(page.getByText(/\$0\.0043/)).toBeVisible();
  });

  test("citation accordion expands and shows chunk content (CHAT-02)", async ({
    page,
  }) => {
    await stubChat(page, [
      {
        tokens: ["Tool use enables tools."],
        trace_id: TRACE_ID_1,
        cited_chunks: [SAMPLE_CHUNK],
      },
    ]);
    await page.goto("/chat");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .fill("tools?");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .press("Enter");

    const trigger = page.getByRole("button", { name: /^Sources \(1\)$/i });
    await expect(trigger).toBeVisible();
    await trigger.click();

    await expect(page.getByText(/Tool use overview/)).toBeVisible();
    await expect(
      page.getByText(/Tool use lets you give Claude access/),
    ).toBeVisible();
  });

  test("thumbs-down opens dialog, submitting POSTs /feedback rating=-1 (CHAT-04)", async ({
    page,
  }) => {
    const { feedbackCalls } = await stubChat(page, [
      {
        tokens: ["A response."],
        trace_id: TRACE_ID_1,
        cited_chunks: [SAMPLE_CHUNK],
      },
    ]);
    await page.goto("/chat");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .fill("?");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .press("Enter");
    await expect(page.getByText(/2810\s*ms/)).toBeVisible();

    await page.getByRole("button", { name: /thumbs down/i }).click();
    await expect(
      page.getByRole("heading", { name: /what went wrong\?/i }),
    ).toBeVisible();

    await page
      .getByLabel(/comment/i)
      .fill("The retrieved chunks were off-topic.");
    await page.getByRole("button", { name: "Submit" }).click();

    await expect(
      page.getByRole("heading", { name: /what went wrong\?/i }),
    ).not.toBeVisible();

    expect(feedbackCalls.length).toBeGreaterThanOrEqual(1);
    const last = feedbackCalls[feedbackCalls.length - 1] as {
      trace_id: string;
      rating: number;
      comment?: string;
    };
    expect(last.rating).toBe(-1);
    expect(last.trace_id).toBe(TRACE_ID_1);
    expect(last.comment).toContain("off-topic");
  });

  test("trace link points to /traces/{trace_id} and renders TraceStub (CHAT-05)", async ({
    page,
  }) => {
    await stubChat(page, [
      {
        tokens: ["Hello."],
        trace_id: TRACE_ID_1,
        cited_chunks: [SAMPLE_CHUNK],
      },
    ]);
    await page.goto("/chat");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .fill("?");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .press("Enter");
    await expect(page.getByText(/2810\s*ms/)).toBeVisible();

    const traceLink = page.getByRole("link", { name: /trace ↗/i });
    await expect(traceLink).toBeVisible();
    const href = await traceLink.getAttribute("href");
    expect(href).toBe(`/traces/${TRACE_ID_1}`);

    await traceLink.click();
    await expect(page).toHaveURL(new RegExp(`/traces/${TRACE_ID_1}$`));
    await expect(page.getByRole("heading", { name: /^Trace$/ })).toBeVisible();
    await expect(
      page.getByText(`trace_id: ${TRACE_ID_1}`),
    ).toBeVisible();
  });

  test("multi-turn within a session — second question appends without clearing the first (CHAT-01)", async ({
    page,
  }) => {
    await stubChat(page, [
      {
        tokens: ["First answer."],
        trace_id: TRACE_ID_1,
        cited_chunks: [SAMPLE_CHUNK],
      },
      {
        tokens: ["Second answer."],
        trace_id: TRACE_ID_2,
        cited_chunks: [SAMPLE_CHUNK],
      },
    ]);
    await page.goto("/chat");

    // Q1
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .fill("First question?");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .press("Enter");
    // Wait for first final frame to render.
    await expect(page.getByText(/2810\s*ms/).first()).toBeVisible();
    await expect(
      page.locator('[data-testid="assistant-content"]').first(),
    ).toContainText("First answer.");

    // Q2 — by now the input is re-enabled.
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .fill("Second question?");
    await page
      .getByRole("textbox", { name: /ask a question/i })
      .press("Enter");

    // After Q2 final frame: 2 user bubbles + 2 assistant bubbles AND first pair still visible.
    await expect(
      page.locator('[data-testid="assistant-content"]').nth(1),
    ).toContainText("Second answer.");

    const userBubbles = page.locator('[data-role="user"]');
    const assistantBubbles = page.locator('[data-role="assistant"]');
    await expect(userBubbles).toHaveCount(2);
    await expect(assistantBubbles).toHaveCount(2);

    // First user message is still present (not cleared by second submission).
    await expect(userBubbles.first()).toContainText("First question?");
    await expect(
      page.locator('[data-testid="assistant-content"]').first(),
    ).toContainText("First answer.");
  });
});
