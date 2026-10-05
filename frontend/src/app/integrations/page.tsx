"use client";

import {
  CheckCircle2,
  ExternalLink,
  GitBranch,
  Hash,
  Key,
  Link2,
  MessageSquare,
  Ticket,
  FileText,
  Database,
  HardDrive,
  Server,
  Cpu,
  Sparkles,
} from "lucide-react";

const integrations = [
  {
    name: "Slack",
    description: "Real-time notifications via Block Kit. Rich DMs with severity badges, Jira links, and action buttons sent to on-call engineers.",
    status: "connected",
    icon: MessageSquare,
    color: "#1e40af",
    bg: "#eff6ff",
    config: [
      { label: "Bot Token", value: "xoxb-1090...UqmH", masked: true },
      { label: "Channel", value: "#general (C0B2CED6DR8)" },
    ],
    usedBy: ["Triage Agent", "Review Agent", "Ops Agent"],
    lastActivity: "2 min ago",
  },
  {
    name: "Jira",
    description: "Automated ticket lifecycle management. Creates Bug issues with priority, assignee, labels, and full context from the triage pipeline.",
    status: "connected",
    icon: Ticket,
    color: "#1e40af",
    bg: "#eff6ff",
    config: [
      { label: "Instance", value: "swarnim29.atlassian.net" },
      { label: "Project", value: "ART" },
      { label: "Auth", value: "API Token (swarnimbane1234@gmail.com)", masked: true },
    ],
    usedBy: ["Triage Agent"],
    lastActivity: "5 min ago",
  },
  {
    name: "Notion",
    description: "Mirrors every Jira ticket to a custom database with Status, Priority, Service, Assignee, and Jira Link properties. Enables non-engineer visibility.",
    status: "connected",
    icon: FileText,
    color: "#0f172a",
    bg: "#f8fafc",
    config: [
      { label: "Database", value: "Artilery Bug Tracker" },
      { label: "Token", value: "ntn_6454...8gTf", masked: true },
    ],
    usedBy: ["Triage Agent"],
    lastActivity: "5 min ago",
  },
  {
    name: "GitHub",
    description: "Receives webhook events for PR lifecycle (opened, reviewed, approved, merged). Validates signatures with HMAC-SHA256 for security.",
    status: "configured",
    icon: GitBranch,
    color: "#0f172a",
    bg: "#f8fafc",
    config: [
      { label: "Webhook", value: "POST /webhook/github" },
      { label: "Secret", value: "HMAC-SHA256 validated", masked: true },
      { label: "Events", value: "pull_request, pull_request_review" },
    ],
    usedBy: ["Review Agent", "Ops Agent"],
    lastActivity: "Awaiting webhook",
  },
  {
    name: "Neo4j",
    description: "Property graph storing team structure, service ownership, developer skills, on-call schedules, and service dependencies. Powers instant lookups.",
    status: "connected",
    icon: Database,
    color: "#16a34a",
    bg: "#f0fdf4",
    config: [
      { label: "URI", value: "bolt://localhost:7687" },
      { label: "Nodes", value: "31 (Teams, Developers, Services, Skills)" },
      { label: "Relationships", value: "MEMBER_OF, OWNS, ON_CALL, DEPENDS_ON, HAS_SKILL" },
    ],
    usedBy: ["Triage Agent", "Review Agent", "Chatbot Agent"],
    lastActivity: "Connected",
  },
  {
    name: "Gemini 2.5 Flash",
    description: "Primary LLM for intent classification, RAG answer synthesis, and deployment failure diagnosis. Free-tier Google AI with sub-second latency.",
    status: "connected",
    icon: Sparkles,
    color: "#7c3aed",
    bg: "#f5f3ff",
    config: [
      { label: "Model", value: "gemini-2.5-flash" },
      { label: "API", value: "Google AI (generativelanguage.googleapis.com)" },
      { label: "Fallback", value: "Ollama (local) / AWS Bedrock (production)" },
    ],
    usedBy: ["Chatbot Agent", "Ops Agent", "Intent Classifier"],
    lastActivity: "Active",
  },
];

const infrastructure = [
  { name: "Apache Kafka", detail: "20 topics (10 event + 10 DLQ)", port: "9092", status: "running", icon: Server },
  { name: "DynamoDB Local", detail: "PR state, chat history, checkpoints", port: "8000", status: "running", icon: HardDrive },
  { name: "MinIO (S3)", detail: "Event log archival", port: "9000", status: "running", icon: HardDrive },
  { name: "ChromaDB", detail: "Vector embeddings for semantic search", port: "embedded", status: "running", icon: Cpu },
];

export default function IntegrationsPage() {
  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[#0f172a] tracking-tight">Integrations</h1>
        <p className="text-sm text-[#64748b] mt-1">
          External services and infrastructure powering the platform
        </p>
      </div>

      {/* External Services */}
      <div className="mb-10">
        <h2 className="text-[13px] font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">
          External Services
        </h2>
        <div className="grid grid-cols-2 gap-5">
          {integrations.map((int) => (
            <div key={int.name} className="border border-[#e2e8f0] rounded-xl bg-white overflow-hidden">
              <div className="p-5 border-b border-[#f1f5f9]">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: int.bg }}>
                      <int.icon className="w-5 h-5" style={{ color: int.color }} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-[15px] font-semibold text-[#0f172a]">{int.name}</h3>
                        <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                          int.status === "connected"
                            ? "text-[#16a34a] bg-[#f0fdf4] border border-[#bbf7d0]"
                            : "text-[#d97706] bg-[#fffbeb] border border-[#fde68a]"
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${int.status === "connected" ? "bg-[#16a34a]" : "bg-[#d97706]"}`} />
                          {int.status === "connected" ? "Connected" : "Configured"}
                        </span>
                      </div>
                      <p className="text-[12px] text-[#64748b] mt-1 leading-relaxed">{int.description}</p>
                    </div>
                  </div>
                </div>
              </div>
              <div className="px-5 py-4">
                <div className="space-y-2">
                  {int.config.map((c) => (
                    <div key={c.label} className="flex items-center justify-between">
                      <span className="text-[11px] text-[#94a3b8]">{c.label}</span>
                      <span className="text-[12px] font-mono text-[#475569]">
                        {c.masked ? "••••" + c.value.slice(-8) : c.value}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 pt-3 border-t border-[#f1f5f9] flex items-center justify-between">
                  <div className="flex gap-1.5">
                    {int.usedBy.map((u) => (
                      <span key={u} className="text-[10px] bg-[#f8fafc] border border-[#e2e8f0] px-1.5 py-0.5 rounded text-[#64748b]">
                        {u}
                      </span>
                    ))}
                  </div>
                  <span className="text-[11px] text-[#94a3b8]">{int.lastActivity}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Infrastructure */}
      <div>
        <h2 className="text-[13px] font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">
          Infrastructure (Docker)
        </h2>
        <div className="grid grid-cols-4 gap-5">
          {infrastructure.map((svc) => (
            <div key={svc.name} className="border border-[#e2e8f0] rounded-xl p-5 bg-white">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-9 h-9 rounded-lg bg-[#f8fafc] flex items-center justify-center">
                  <svc.icon className="w-4 h-4 text-[#64748b]" />
                </div>
                <div>
                  <h3 className="text-[13px] font-semibold text-[#0f172a]">{svc.name}</h3>
                  <p className="text-[11px] text-[#94a3b8]">Port {svc.port}</p>
                </div>
              </div>
              <p className="text-[12px] text-[#64748b] mb-3">{svc.detail}</p>
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-[#16a34a]" />
                <span className="text-[11px] font-medium text-[#16a34a]">Running</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
