/**
 * 本文件为 /messages 页面：客服消息管理视图。
 * 使用 SWR 每 3s 拉取状态，显示用户消息和回复功能。
 * 仅用于本地测试与演示。
 */

"use client";

import React, { useState } from "react";
import useSWR from "swr";

type Message = {
  id: string;
  userId: string;
  username: string;
  message: string;
  reply: string | null;
  created_at: string;
  replied_at: string | null;
  status: "pending" | "replied";
};

const fetcher = async (url: string): Promise<Message[]> => {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

export default function MessagesPage() {
  const apiBase = process.env.NEXT_PUBLIC_API || process.env.NEXT_PUBLIC_CSMS_HTTP || "http://localhost:9000";
  const { data: messages = [], error, isLoading, mutate } = useSWR<Message[]>(
    `${apiBase}/api/messages`,
    fetcher,
    { refreshInterval: 3000 }
  );

  const [replyingId, setReplyingId] = useState<string | null>(null);
  const [replyText, setReplyText] = useState("");
  const [replying, setReplying] = useState(false);

  const handleReply = async (messageId: string) => {
    if (!replyText.trim()) {
      alert("请输入回复内容");
      return;
    }

    try {
      setReplying(true);
      const res = await fetch(`${apiBase}/api/messages/reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messageId,
          reply: replyText.trim(),
        }),
      });

      if (res.ok) {
        setReplyText("");
        setReplyingId(null);
        await mutate(); // Refresh messages
        alert("回复成功");
      } else {
        alert("回复失败");
      }
    } catch (error) {
      console.error("Reply failed:", error);
      alert("网络错误");
    } finally {
      setReplying(false);
    }
  };

  const stats = {
    total: messages.length,
    pending: messages.filter((m) => m.status === "pending").length,
    replied: messages.filter((m) => m.status === "replied").length,
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
      color: "#fff",
      padding: 20,
      fontFamily: "ui-sans-serif, system-ui",
    }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 28, fontWeight: "700", marginBottom: 8, color: "#fff" }}>
          💬 客服消息中心
        </h1>
        <div style={{ display: "flex", gap: 16, fontSize: 14, color: "#aaa" }}>
          <span>实时刷新: 3秒</span>
        </div>
      </div>

      {/* Stats Cards */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: 16,
        marginBottom: 32,
      }}>
        <StatCard label="总计" value={stats.total} color="#8b5cf6" />
        <StatCard label="待回复" value={stats.pending} color="#ff9500" />
        <StatCard label="已回复" value={stats.replied} color="#34c759" />
      </div>

      {/* Messages List */}
      {isLoading ? (
        <div style={{ textAlign: "center", padding: 48, color: "#aaa" }}>加载中...</div>
      ) : error ? (
        <div style={{ textAlign: "center", padding: 48, color: "#ff3b30" }}>加载失败: {error.message}</div>
      ) : messages.length === 0 ? (
        <div style={{ background: "rgba(255,255,255,0.05)", borderRadius: 12, padding: 48, textAlign: "center", border: "1px solid rgba(255,255,255,0.1)" }}>
          <p style={{ fontSize: 18, color: "#888" }}>暂无消息</p>
          <p style={{ fontSize: 14, color: "#666", marginTop: 8 }}>用户发送的消息将显示在这里</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {messages.map((msg) => (
            <MessageCard
              key={msg.id}
              message={msg}
              isReplying={replyingId === msg.id}
              replyText={replyText}
              onReplyTextChange={setReplyText}
              onStartReply={() => setReplyingId(msg.id)}
              onCancelReply={() => {
                setReplyingId(null);
                setReplyText("");
              }}
              onSendReply={() => handleReply(msg.id)}
              replying={replying}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.05)",
      borderRadius: 12,
      padding: 16,
      border: `1px solid ${color}40`,
    }}>
      <div style={{ fontSize: 12, color: "#aaa", marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: "700", color: color }}>{value}</div>
    </div>
  );
}

function MessageCard({
  message,
  isReplying,
  replyText,
  onReplyTextChange,
  onStartReply,
  onCancelReply,
  onSendReply,
  replying,
}: {
  message: Message;
  isReplying: boolean;
  replyText: string;
  onReplyTextChange: (text: string) => void;
  onStartReply: () => void;
  onCancelReply: () => void;
  onSendReply: () => void;
  replying: boolean;
}) {
  const statusColor = message.status === "pending" ? "#ff9500" : "#34c759";
  const statusText = message.status === "pending" ? "待回复" : "已回复";

  return (
    <div style={{
      background: "rgba(255,255,255,0.05)",
      borderRadius: 12,
      padding: 20,
      border: "1px solid rgba(255,255,255,0.1)",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: "600", marginBottom: 4 }}>{message.username}</div>
          <div style={{ fontSize: 12, color: "#aaa" }}>
            {message.userId} • {new Date(message.created_at).toLocaleString()}
          </div>
        </div>
        <div style={{
          background: `${statusColor}20`,
          border: `1px solid ${statusColor}`,
          borderRadius: 8,
          padding: "6px 12px",
          fontSize: 12,
          fontWeight: "600",
          color: statusColor,
        }}>
          {statusText}
        </div>
      </div>

      {/* Message Content */}
      <div style={{
        background: "rgba(0,0,0,0.2)",
        borderRadius: 8,
        padding: 16,
        marginBottom: 12,
        borderLeft: "3px solid #007AFF",
      }}>
        <div style={{ fontSize: 14, color: "#fff", lineHeight: 1.6 }}>{message.message}</div>
      </div>

      {/* Reply (if exists) */}
      {message.reply && (
        <div style={{
          background: "rgba(52, 199, 89, 0.1)",
          borderRadius: 8,
          padding: 16,
          marginBottom: 12,
          borderLeft: "3px solid #34c759",
        }}>
          <div style={{ fontSize: 12, color: "#aaa", marginBottom: 8 }}>客服回复</div>
          <div style={{ fontSize: 14, color: "#fff", lineHeight: 1.6 }}>{message.reply}</div>
          <div style={{ fontSize: 12, color: "#666", marginTop: 8 }}>
            {message.replied_at && new Date(message.replied_at).toLocaleString()}
          </div>
        </div>
      )}

      {/* Reply Input */}
      {message.status === "pending" && (
        <div>
          {!isReplying ? (
            <button
              onClick={onStartReply}
              style={{
                width: "100%",
                padding: 12,
                background: "rgba(255,255,255,0.1)",
                border: "1px solid rgba(255,255,255,0.2)",
                borderRadius: 8,
                color: "#fff",
                fontSize: 14,
                fontWeight: "600",
                cursor: "pointer",
              }}
            >
              回复
            </button>
          ) : (
            <div>
              <textarea
                value={replyText}
                onChange={(e) => onReplyTextChange(e.target.value)}
                placeholder="请输入回复内容..."
                style={{
                  width: "100%",
                  minHeight: 80,
                  padding: 12,
                  background: "rgba(0,0,0,0.2)",
                  border: "1px solid rgba(255,255,255,0.2)",
                  borderRadius: 8,
                  color: "#fff",
                  fontSize: 14,
                  fontFamily: "inherit",
                  resize: "vertical",
                }}
              />
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button
                  onClick={onSendReply}
                  disabled={replying || !replyText.trim()}
                  style={{
                    flex: 1,
                    padding: 12,
                    background: replying || !replyText.trim() ? "#666" : "#34c759",
                    border: "none",
                    borderRadius: 8,
                    color: "#fff",
                    fontSize: 14,
                    fontWeight: "600",
                    cursor: replying || !replyText.trim() ? "not-allowed" : "pointer",
                    opacity: replying || !replyText.trim() ? 0.6 : 1,
                  }}
                >
                  {replying ? "发送中..." : "发送回复"}
                </button>
                <button
                  onClick={onCancelReply}
                  disabled={replying}
                  style={{
                    flex: 1,
                    padding: 12,
                    background: "rgba(255,255,255,0.1)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 8,
                    color: "#fff",
                    fontSize: 14,
                    fontWeight: "600",
                    cursor: replying ? "not-allowed" : "pointer",
                    opacity: replying ? 0.6 : 1,
                  }}
                >
                  取消
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

