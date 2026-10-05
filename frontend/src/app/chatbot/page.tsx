"use client";

import { useState, useRef, useEffect } from "react";
import { ArrowUp, Bot, Loader2, User, Database, Search } from "lucide-react";
import ReactMarkdown from "react-markdown";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  intent?: string;
  timestamp: Date;
}

const suggestedQueries = [
  "Who owns PaymentService?",
  "Who is on call for AuthService?",
  "What services does Team Backend own?",
  "Show me the service dependency map",
  "What are the recent deployment failures?",
];

export default function ChatbotPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (query: string) => {
    if (!query.trim() || loading) return;

    const userMsg: Message = {
      role: "user",
      content: query,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("http://localhost:8001/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, session_id: "dashboard" }),
      });

      if (!res.ok) throw new Error("API error");

      const data = await res.json();
      const assistantMsg: Message = {
        role: "assistant",
        content: data.answer,
        sources: data.sources,
        intent: data.intent,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Unable to reach the API. Make sure the backend is running: uvicorn api.main:app --reload",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="px-8 py-5 border-b border-[#e2e8f0]">
        <h1 className="text-2xl font-semibold text-[#0f172a] tracking-tight">Chatbot</h1>
        <p className="text-sm text-[#64748b] mt-1">
          RAG-powered Q&A over the knowledge graph, event logs, and system state
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-8 py-6">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full">
            <div className="w-14 h-14 rounded-2xl bg-[#eff6ff] flex items-center justify-center mb-5">
              <Bot className="w-7 h-7 text-[#1e40af]" />
            </div>
            <h2 className="text-lg font-semibold text-[#0f172a] mb-2">Artilery Assistant</h2>
            <p className="text-sm text-[#64748b] mb-8 text-center max-w-md">
              Ask questions about services, teams, deployments, and system state.
              Answers are generated using Gemini 2.5 Flash with context from Neo4j, DynamoDB, and ChromaDB.
            </p>
            <div className="grid grid-cols-1 gap-2 w-full max-w-lg">
              {suggestedQueries.map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="flex items-center gap-3 px-4 py-3 border border-[#e2e8f0] rounded-lg text-left hover:bg-[#f8fafc] transition-colors group"
                >
                  <Search className="w-4 h-4 text-[#94a3b8] group-hover:text-[#1e40af] transition-colors" />
                  <span className="text-[13px] text-[#475569] group-hover:text-[#0f172a] transition-colors">{q}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
                {msg.role === "assistant" && (
                  <div className="w-8 h-8 rounded-lg bg-[#eff6ff] flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Bot className="w-4 h-4 text-[#1e40af]" />
                  </div>
                )}
                <div className={`max-w-[80%] ${msg.role === "user" ? "order-first" : ""}`}>
                  <div
                    className={`rounded-xl px-4 py-3 text-[13.5px] leading-relaxed ${
                      msg.role === "user"
                        ? "bg-[#0f172a] text-white"
                        : "bg-[#f8fafc] border border-[#e2e8f0] text-[#0f172a]"
                    }`}
                  >
                    {msg.role === "assistant" ? (
                      <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0.5 prose-headings:my-2 prose-code:bg-[#e2e8f0] prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-[12px] prose-code:font-mono prose-pre:bg-[#1e293b] prose-pre:text-white prose-pre:rounded-lg prose-strong:text-[#0f172a]">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                    ) : (
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                    )}
                  </div>
                  {msg.role === "assistant" && (msg.sources?.length || msg.intent) && (
                    <div className="flex items-center gap-3 mt-2 px-1">
                      {msg.intent && (
                        <span className="text-[10px] font-medium text-[#64748b] bg-[#f1f5f9] px-2 py-0.5 rounded">
                          Intent: {msg.intent}
                        </span>
                      )}
                      {msg.sources?.map((s) => (
                        <span key={s} className="flex items-center gap-1 text-[10px] text-[#64748b]">
                          <Database className="w-3 h-3" />
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {msg.role === "user" && (
                  <div className="w-8 h-8 rounded-lg bg-[#0f172a] flex items-center justify-center flex-shrink-0 mt-0.5">
                    <User className="w-4 h-4 text-white" />
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-lg bg-[#eff6ff] flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4 text-[#1e40af]" />
                </div>
                <div className="bg-[#f8fafc] border border-[#e2e8f0] rounded-xl px-4 py-3">
                  <Loader2 className="w-4 h-4 text-[#94a3b8] animate-spin" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="px-8 py-4 border-t border-[#e2e8f0]">
        <div className="max-w-3xl mx-auto relative">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage(input)}
            placeholder="Ask about services, teams, deployments..."
            className="w-full border border-[#e2e8f0] rounded-xl px-4 py-3.5 pr-12 text-[14px] text-[#0f172a] placeholder:text-[#94a3b8] focus:outline-none focus:ring-2 focus:ring-[#1e40af] focus:border-transparent transition-shadow"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || loading}
            className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-lg bg-[#0f172a] flex items-center justify-center disabled:opacity-30 hover:bg-[#1e293b] transition-colors"
          >
            <ArrowUp className="w-4 h-4 text-white" />
          </button>
        </div>
      </div>
    </div>
  );
}
