import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { apiPost } from "../../lib/api";

type AssistantContextState = {
  region: string;
  industry: string;
  tickers: string;
  sources: string;
  clientId: string;
  accountId: string;
};

type AssistantSource = {
  route: string;
  source: string;
  timestamp?: number;
};

type AssistantResponse = {
  answer: string;
  sources?: AssistantSource[];
  confidence?: string;
  warnings?: string[];
  routing?: {
    rule?: string;
    handler?: string | null;
  };
};

type Message = {
  text: string;
  sender: "user" | "bot";
  meta?: {
    confidence?: string;
    sources?: AssistantSource[];
    warnings?: string[];
    routing?: {
      rule?: string;
      handler?: string | null;
    };
  };
};

type ChatDrawerProps = {
  entry?: string;
  onClose: () => void;
};

const CONTEXT_STORAGE_KEY = "lotbook.assistant.context";
const LEGACY_CONTEXT_STORAGE_KEY = "clear.assistant.context";
const DEFAULT_CONTEXT: AssistantContextState = {
  region: "Global",
  industry: "all",
  tickers: "",
  sources: "",
  clientId: "",
  accountId: ""
};

const readAssistantContext = (): AssistantContextState => {
  if (typeof window === "undefined") {
    return DEFAULT_CONTEXT;
  }
  try {
    const stored = window.localStorage.getItem(CONTEXT_STORAGE_KEY) ?? window.localStorage.getItem(LEGACY_CONTEXT_STORAGE_KEY);
    if (!stored) return DEFAULT_CONTEXT;
    const parsed = JSON.parse(stored) as Partial<AssistantContextState>;
    return {
      region: typeof parsed.region === "string" ? parsed.region : DEFAULT_CONTEXT.region,
      industry:
        typeof parsed.industry === "string" ? parsed.industry : DEFAULT_CONTEXT.industry,
      tickers: typeof parsed.tickers === "string" ? parsed.tickers : DEFAULT_CONTEXT.tickers,
      sources: typeof parsed.sources === "string" ? parsed.sources : DEFAULT_CONTEXT.sources,
      clientId: typeof parsed.clientId === "string" ? parsed.clientId : DEFAULT_CONTEXT.clientId,
      accountId:
        typeof parsed.accountId === "string" ? parsed.accountId : DEFAULT_CONTEXT.accountId
    };
  } catch (error) {
    return DEFAULT_CONTEXT;
  }
};

const persistAssistantContext = (context: AssistantContextState) => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(CONTEXT_STORAGE_KEY, JSON.stringify(context));
    window.localStorage.removeItem(LEGACY_CONTEXT_STORAGE_KEY);
  } catch (error) {
    return;
  }
};

const buildScopeLabel = (context: AssistantContextState) => {
  const parts: string[] = [];
  const region = context.region.trim() || "Global";
  const industry = context.industry.trim() || "all";
  parts.push(region, industry);
  if (context.tickers.trim()) {
    parts.push(`Tickers: ${context.tickers.trim()}`);
  }
  if (context.clientId.trim()) {
    parts.push(`Client: ${context.clientId.trim()}`);
  }
  if (context.accountId.trim()) {
    parts.push(`Account: ${context.accountId.trim()}`);
  }
  return `Scope: ${parts.join(" \u2022 ")}`;
};
export function ChatDrawer({ entry, onClose }: ChatDrawerProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [region, setRegion] = useState(DEFAULT_CONTEXT.region);
  const [industry, setIndustry] = useState(DEFAULT_CONTEXT.industry);
  const [tickers, setTickers] = useState(DEFAULT_CONTEXT.tickers);
  const [sources, setSources] = useState(DEFAULT_CONTEXT.sources);
  const [clientId, setClientId] = useState(DEFAULT_CONTEXT.clientId);
  const [accountId, setAccountId] = useState(DEFAULT_CONTEXT.accountId);

  useEffect(() => {
    const stored = readAssistantContext();
    setRegion(stored.region);
    setIndustry(stored.industry);
    setTickers(stored.tickers);
    setSources(stored.sources);
    setClientId(stored.clientId);
    setAccountId(stored.accountId);
  }, []);

  useEffect(() => {
    persistAssistantContext({
      region,
      industry,
      tickers,
      sources,
      clientId,
      accountId
    });
  }, [region, industry, tickers, sources, clientId, accountId]);

  const sendMessage = async () => {
    if (!input.trim()) return;

    const newMessages: Message[] = [...messages, { text: input, sender: "user" }];
    setMessages(newMessages);
    setInput("");

    const context = {
      region,
      industry,
      tickers: tickers
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      client_id: clientId.trim() || undefined,
      account_id: accountId.trim() || undefined
    };
    const sourceList = sources
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

    try {
      const response = await apiPost<AssistantResponse>("/api/assistant/query", {
        question: input,
        context,
        sources: sourceList.length ? sourceList : undefined,
        entry
      });
      setMessages([
        ...newMessages,
        {
          text: response.answer,
          sender: "bot",
          meta: {
            confidence: response.confidence,
            sources: response.sources,
            warnings: response.warnings,
            routing: response.routing
          }
        }
      ]);
    } catch (error) {
      setMessages([
        ...newMessages,
        { text: "Error: Could not connect to the AI assistant.", sender: "bot" }
      ]);
    }
  };

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md bg-ink-900 border-l border-slate-800/60 shadow-lg flex flex-col">
      <div className="flex items-center justify-between p-4 border-b border-slate-800/60">
        <div>
          <h2 className="text-lg font-medium text-slate-100">AI Assistant</h2>
          <div className="text-xs text-slate-400">
            {buildScopeLabel({ region, industry, tickers, sources, clientId, accountId })}
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-full p-1 text-slate-400 hover:bg-slate-800/60"
        >
          <X size={20} />
        </button>
      </div>
      <div className="border-b border-slate-800/60 px-4 py-3">
        <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">
          Context
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-slate-400">Region</label>
            <input
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="mt-1 w-full rounded-lg bg-ink-950/60 border border-slate-800 px-3 py-1.5 text-xs text-slate-200"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400">Industry</label>
            <input
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="mt-1 w-full rounded-lg bg-ink-950/60 border border-slate-800 px-3 py-1.5 text-xs text-slate-200"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400">Tickers</label>
            <input
              value={tickers}
              onChange={(e) => setTickers(e.target.value)}
              placeholder="AAPL, MSFT"
              className="mt-1 w-full rounded-lg bg-ink-950/60 border border-slate-800 px-3 py-1.5 text-xs text-slate-200"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400">Sources</label>
            <input
              value={sources}
              onChange={(e) => setSources(e.target.value)}
              placeholder="bbc.com, cnbc.com"
              className="mt-1 w-full rounded-lg bg-ink-950/60 border border-slate-800 px-3 py-1.5 text-xs text-slate-200"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400">Client ID</label>
            <input
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="mt-1 w-full rounded-lg bg-ink-950/60 border border-slate-800 px-3 py-1.5 text-xs text-slate-200"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400">Account ID</label>
            <input
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              className="mt-1 w-full rounded-lg bg-ink-950/60 border border-slate-800 px-3 py-1.5 text-xs text-slate-200"
            />
          </div>
        </div>
      </div>
      <div className="flex-1 p-4 overflow-y-auto">
        <div className="space-y-4">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${
                message.sender === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`rounded-lg px-4 py-2 ${
                  message.sender === "user"
                    ? "bg-emerald-600 text-white"
                    : "bg-slate-700 text-slate-100"
                }`}
              >
                {message.text}
                {message.sender === "bot" && message.meta ? (
                  <div className="mt-2 space-y-1 text-[11px] text-slate-300/90">
                    {message.meta.confidence ? (
                      <div>Confidence: {message.meta.confidence}</div>
                    ) : null}
                    {message.meta.routing?.rule ? (
                      <div>
                        Routing: {message.meta.routing.rule}
                        {message.meta.routing.handler
                          ? ` (${message.meta.routing.handler})`
                          : ""}
                      </div>
                    ) : null}
                    {message.meta.sources && message.meta.sources.length ? (
                      <div>
                        Sources:{" "}
                        {message.meta.sources
                          .map((source) =>
                            source.source ? `${source.route} (${source.source})` : source.route
                          )
                          .join(", ")}
                      </div>
                    ) : null}
                    {message.meta.warnings && message.meta.warnings.length ? (
                      <div>
                        Warnings: {message.meta.warnings.join(", ")}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="p-4 border-t border-slate-800/60">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage();
          }}
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question..."
            className="w-full rounded-xl bg-ink-950/60 border border-slate-800 px-4 py-2 text-sm text-slate-200"
          />
        </form>
      </div>
    </div>
  );
}
