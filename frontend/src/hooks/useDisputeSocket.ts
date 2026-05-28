"use client";
import { useEffect, useRef, useCallback, useState } from "react";

export type DisputeSocketEventType =
  | "DISPUTE_QUEUED"
  | "ANALYSIS_COMPLETE"
  | "ANALYSIS_FAILED";

export interface DisputeQueuedEvent {
  type: "DISPUTE_QUEUED";
  case_id: string;
  customer_id: string;
  customer_name: string;
  merchant: string;
  amount: number;
  currency: string;
  timestamp: string;
}

export interface AnalysisCompleteEvent {
  type: "ANALYSIS_COMPLETE";
  case_id: string;
  case: Record<string, unknown>;
}

export interface AnalysisFailedEvent {
  type: "ANALYSIS_FAILED";
  case_id: string;
  errors: string[];
}

export type DisputeSocketEvent =
  | DisputeQueuedEvent
  | AnalysisCompleteEvent
  | AnalysisFailedEvent;

const WS_URL =
  (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")
    .replace(/^http/, "ws") + "/ws/disputes";

export function useDisputeSocket(
  onEvent: (event: DisputeSocketEvent) => void
): { isConnected: boolean } {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const isMounted = useRef(true);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (!isMounted.current) return;

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setIsConnected(true);
      // Ping every 20 s to keep the connection alive
      const ping = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
        else clearInterval(ping);
      }, 20_000);
    };

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as DisputeSocketEvent;
        onEventRef.current(event);
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      if (!isMounted.current) return;
      reconnectTimeout.current = setTimeout(connect, 2_000);
    };

    ws.onerror = () => ws.close();

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    isMounted.current = true;
    connect();
    return () => {
      isMounted.current = false;
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { isConnected };
}
