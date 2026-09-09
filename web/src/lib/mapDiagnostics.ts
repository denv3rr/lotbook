type StylePreflight = {
  ok: boolean;
  detail: string;
};

export async function preflightStyle(
  url: string,
  timeoutMs = 4000
): Promise<StylePreflight> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      cache: "no-store"
    });
    if (!response.ok) {
      return { ok: false, detail: `HTTP ${response.status}` };
    }
    return { ok: true, detail: "ok" };
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return { ok: false, detail: "timeout" };
    }
    if (err instanceof Error) {
      return { ok: false, detail: err.message };
    }
    return { ok: false, detail: "unknown error" };
  } finally {
    window.clearTimeout(timeout);
  }
}

export function checkWorkerClass(maplibre: { getWorkerUrl: () => string }) {
  if (!maplibre.getWorkerUrl()) {
    return "Worker: missing";
  }
  try {
    const worker = new Worker(maplibre.getWorkerUrl(), { type: "module" });
    worker.terminate();
    return "Worker: ok";
  } catch (err) {
    if (err instanceof Error) {
      return `Worker: ${err.message}`;
    }
    return "Worker: init failed";
  }
}

export async function preflightWorkerScript(url: string) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      return `Worker script: HTTP ${response.status}`;
    }
    const contentType = response.headers.get("content-type") || "";
    const snippet = (await response.text()).slice(0, 32).trim();
    if (snippet.startsWith("<")) {
      return "Worker script: HTML response";
    }
    if (contentType && !contentType.includes("javascript")) {
      return `Worker script: ${contentType}`;
    }
    return "Worker script: ok";
  } catch (err) {
    if (err instanceof Error) {
      return `Worker script: ${err.message}`;
    }
    return "Worker script: failed";
  }
}

function resolveTemplate(url: string, tokens: Record<string, string>) {
  let next = url;
  Object.entries(tokens).forEach(([key, value]) => {
    next = next.replace(`{${key}}`, value);
  });
  return next;
}

async function probeUrl(label: string, url: string) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      return `${label}: HTTP ${response.status}`;
    }
    return `${label}: ok`;
  } catch (err) {
    if (err instanceof Error) {
      return `${label}: ${err.message}`;
    }
    return `${label}: failed`;
  }
}

export async function preflightMapResources(styleUrl: string) {
  const diagnostics: string[] = [];
  try {
    const response = await fetch(styleUrl, { cache: "no-store" });
    if (!response.ok) {
      return [`Style: HTTP ${response.status}`];
    }
    const style = (await response.json()) as {
      sprite?: string;
      glyphs?: string;
      sources?: Record<string, { tiles?: string[]; url?: string }>;
    };
    diagnostics.push("Style: ok");
    if (style.sprite) {
      diagnostics.push(await probeUrl("Sprite JSON", `${style.sprite}.json`));
      diagnostics.push(await probeUrl("Sprite PNG", `${style.sprite}.png`));
    }
    if (style.glyphs) {
      const glyphUrl = resolveTemplate(style.glyphs, {
        fontstack: encodeURIComponent("Open Sans Regular"),
        range: "0-255"
      });
      diagnostics.push(await probeUrl("Glyphs", glyphUrl));
    }
    const firstSource = style.sources
      ? Object.values(style.sources).find((source) => source.tiles?.length)
      : undefined;
    if (firstSource?.tiles?.[0]) {
      const tileUrl = resolveTemplate(firstSource.tiles[0], {
        s: "a",
        z: "0",
        x: "0",
        y: "0",
        "bbox-epsg-3857": "0,0,0,0"
      });
      diagnostics.push(await probeUrl("Tile", tileUrl));
      return diagnostics;
    }

    const urlSource = style.sources
      ? Object.values(style.sources).find((source) => source.url)
      : undefined;
    if (urlSource?.url) {
      diagnostics.push(await probeUrl("TileJSON", urlSource.url));
      try {
        const tileJsonResponse = await fetch(urlSource.url, { cache: "no-store" });
        if (tileJsonResponse.ok) {
          const tileJson = (await tileJsonResponse.json()) as { tiles?: string[] };
          const tileTemplate = tileJson.tiles?.[0];
          if (tileTemplate) {
            const tileUrl = resolveTemplate(tileTemplate, {
              s: "a",
              z: "0",
              x: "0",
              y: "0",
              "bbox-epsg-3857": "0,0,0,0"
            });
            diagnostics.push(await probeUrl("Tile", tileUrl));
            return diagnostics;
          }
        }
      } catch (err) {
        if (err instanceof Error) {
          diagnostics.push(`TileJSON parse: ${err.message}`);
        } else {
          diagnostics.push("TileJSON parse: failed");
        }
      }
    }
    diagnostics.push("Tile: none");
  } catch (err) {
    if (err instanceof Error) {
      diagnostics.push(`Style parse: ${err.message}`);
    } else {
      diagnostics.push("Style parse: failed");
    }
  }
  return diagnostics;
}
