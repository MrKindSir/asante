"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "./story-domain";

export type CollabMessage = {
  id: string;
  projectId: string;
  accountId: string;
  authorName: string;
  body: string;
  createdAt: string;
};

export function useProjectCollab(projectId: string | null | undefined, enabled = true) {
  const [messages, setMessages] = useState<CollabMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!projectId || !enabled) {
      setMessages([]);
      setConnected(false);
      return;
    }
    let active = true;
    setError("");
    void api<{ messages: CollabMessage[] }>("/v1/workspace/projects/" + projectId + "/messages")
      .then((payload) => {
        if (active) setMessages(payload.messages || []);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load team messages.");
      });

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/asante/api/v1/workspace/projects/${projectId}/collab/ws`);
    socketRef.current = socket;
    socket.onopen = () => {
      if (active) setConnected(true);
    };
    socket.onclose = () => {
      if (active) setConnected(false);
    };
    socket.onerror = () => {
      if (active) setConnected(false);
    };
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(String(event.data)) as { type?: string; message?: CollabMessage };
        if (payload.type === "message" && payload.message) {
          setMessages((current) => {
            if (current.some((item) => item.id === payload.message!.id)) return current;
            return [...current, payload.message!];
          });
        }
      } catch {
        /* Ignore malformed frames. */
      }
    };

    const ping = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
    }, 25000);

    return () => {
      active = false;
      window.clearInterval(ping);
      socket.close();
      socketRef.current = null;
    };
  }, [projectId, enabled]);

  async function sendMessage(body: string): Promise<CollabMessage> {
    if (!projectId) throw new Error("No project selected.");
    const message = await api<CollabMessage>("/v1/workspace/projects/" + projectId + "/messages", { body });
    setMessages((current) => (current.some((item) => item.id === message.id) ? current : [...current, message]));
    return message;
  }

  return { messages, connected, error, sendMessage };
}
