import { useEffect, useRef, useState } from "react";
import { extractWarnings, getApiBase, getApiKey, getAuthHint } from "./api";
import { useTrackerPause } from "./trackerPause";

const API_BASE = getApiBase();

type StreamOptions = {
  interval?: number;
  enabled?: boolean;
  mode?: "combined" | "flights" | "ships";
};

export function useTrackerStream<T>(options: StreamOptions = {}) {
  const { interval = 5, enabled = true, mode = "combined" } = options;
  const [data, setData] = useState<T | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<number | null>(null);
  const attemptRef = useRef(0);
  const { paused } = useTrackerPause();

  useEffect(() => {
    let cancelled = false;
    let connectionGeneration = 0;
    const clearRetry = () => {
      if (retryRef.current !== null) {
        window.clearTimeout(retryRef.current);
        retryRef.current = null;
      }
    };
    const closeSocket = () => {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
    const scheduleReconnect = () => {
      if (cancelled || paused || !enabled) return;
      clearRetry();
      attemptRef.current += 1;
      const delay = Math.min(10000, 1500 + attemptRef.current * 1000);
      retryRef.current = window.setTimeout(() => {
        if (cancelled || paused || !enabled) return;
        void connect();
      }, delay);
    };
    const connect = async () => {
      const generation = connectionGeneration + 1;
      connectionGeneration = generation;
      clearRetry();
      closeSocket();
      setError(null);
      const params = new URLSearchParams();
      params.set("mode", mode);
      params.set("interval", String(interval));
      const apiKey = await getApiKey();
      if (cancelled || generation !== connectionGeneration) return;
      const baseUrl = new URL(API_BASE);
      const wsProtocol = baseUrl.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${wsProtocol}//${baseUrl.host}/ws/trackers?${params.toString()}`;
      const protocols = apiKey ? [`lotbook-key.${apiKey}`] : undefined;
      const ws = new WebSocket(wsUrl, protocols);
      socketRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setConnected(true);
        setError(null);
      };
      ws.onclose = (event) => {
        setConnected(false);
        if (event.code === 1008) {
          setError(`WebSocket rejected. ${getAuthHint()}`);
        } else if (event.code === 1006) {
          setError(`WebSocket closed unexpectedly. ${getAuthHint()}`);
        }
        scheduleReconnect();
      };
      ws.onerror = () => {
        setConnected(false);
        setError(`WebSocket connection failed. ${getAuthHint()}`);
        scheduleReconnect();
      };
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as T;
          setData(payload);
          setWarnings(extractWarnings(payload));
        } catch {
          setConnected(false);
          setError("WebSocket payload parsing failed.");
          setWarnings([]);
          scheduleReconnect();
        }
      };
    };

    if (!enabled || paused) {
      setConnected(false);
      setError(null);
      clearRetry();
      closeSocket();
      return () => {
        cancelled = true;
        clearRetry();
        closeSocket();
      };
    }
    void connect();
    return () => {
      cancelled = true;
      clearRetry();
      closeSocket();
    };
  }, [enabled, interval, mode, paused]);

  return { data, connected, error, warnings };
}
