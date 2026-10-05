"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Filter,
  RefreshCw,
  Search,
  Zap,
} from "lucide-react";

const events = [
  {
    id: "7ac67e08",
    topic: "bug.ingested",
    key: "BUG-DEMO-1778186729",
    service: "PaymentService",
    status: "processed",
    agent: "Triage",
    timestamp: "2026-05-08T02:15:29Z",
    actions: ["Jira: ART-3", "Notion: Page created", "Slack: DM sent"],
    latency: "1.2s",
    partition: 1,
    offset: 4,
  },
  {
    id: "10be9365",
    topic: "ticket.created",
    key: "ART-3",
    service: "PaymentService",
    status: "processed",
    agent: "Ops",
    timestamp: "2026-05-08T02:15:30Z",
    actions: ["Monitoring initiated"],
    latency: "0.3s",
    partition: 0,
    offset: 3,
  },
  {
    id: "a9f13d42",
    topic: "pr.opened",
    key: "PR-47",
    service: "AuthService",
    status: "processed",
    agent: "Review",
    timestamp: "2026-05-08T01:45:12Z",
    actions: ["Reviewer: Arjun Mehta", "Slack: Notification sent"],
    latency: "2.1s",
    partition: 0,
    offset: 12,
  },
  {
    id: "b7c22e91",
    topic: "pr.approved",
    key: "PR-46",
    service: "UserService",
    status: "processed",
    agent: "Review",
    timestamp: "2026-05-08T01:30:45Z",
    actions: ["State: approved", "Deploy: triggered"],
    latency: "1.8s",
    partition: 1,
    offset: 8,
  },
  {
    id: "c3d89f01",
    topic: "deploy.succeeded",
    key: "DEPLOY-029",
    service: "UserService",
    status: "processed",
    agent: "Ops",
    timestamp: "2026-05-08T01:32:10Z",
    actions: ["Jira: Ticket resolved", "Slack: Success notification"],
    latency: "0.9s",
    partition: 0,
    offset: 5,
  },
  {
    id: "d4e90a12",
    topic: "deploy.failed",
    key: "DEPLOY-028",
    service: "NotificationService",
    status: "escalated",
    agent: "Ops",
    timestamp: "2026-05-08T00:15:33Z",
    actions: ["AI Diagnosis: Memory leak", "Rollback: Executed", "Slack: Alert sent"],
    latency: "4.2s",
    partition: 1,
    offset: 3,
  },
  {
    id: "e5fa1b23",
    topic: "bug.ingested",
    key: "BUG-0041",
    service: "APIGateway",
    status: "processed",
    agent: "Triage",
    timestamp: "2026-05-07T23:48:22Z",
    actions: ["Jira: ART-1", "Notion: Page created", "Slack: DM sent"],
    latency: "1.5s",
    partition: 0,
    offset: 2,
  },
  {
    id: "f6gb2c34",
    topic: "pr.reviewed",
    key: "PR-45",
    service: "PaymentService",
    status: "processed",
    agent: "Review",
    timestamp: "2026-05-07T22:10:09Z",
    actions: ["Review state: changes_requested", "Author notified"],
    latency: "1.1s",
    partition: 0,
    offset: 7,
  },
];

const topicColors: Record<string, string> = {
  "bug.ingested": "#dc2626",
  "ticket.created": "#16a34a",
  "pr.opened": "#7c3aed",
  "pr.reviewed": "#7c3aed",
  "pr.approved": "#16a34a",
  "deploy.triggered": "#0891b2",
  "deploy.failed": "#dc2626",
  "deploy.succeeded": "#16a34a",
};

export default function EventsPage() {
  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-[#0f172a] tracking-tight">Event Pipeline</h1>
          <p className="text-sm text-[#64748b] mt-1">
            Kafka event log — every action in the system is traceable
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-4 h-4 text-[#94a3b8] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search events..."
              className="pl-9 pr-4 py-2 border border-[#e2e8f0] rounded-lg text-[13px] w-64 focus:outline-none focus:ring-2 focus:ring-[#1e40af] focus:border-transparent"
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="border border-[#e2e8f0] rounded-xl bg-white overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#e2e8f0] bg-[#fafbfc]">
              <th className="text-left px-5 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Event ID</th>
              <th className="text-left px-5 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Topic</th>
              <th className="text-left px-5 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Key</th>
              <th className="text-left px-5 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Service</th>
              <th className="text-left px-5 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Agent</th>
              <th className="text-left px-5 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Actions</th>
              <th className="text-left px-5 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Latency</th>
              <th className="text-left px-5 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#f8fafc]">
            {events.map((event) => (
              <tr key={event.id} className="hover:bg-[#fafbfc] transition-colors">
                <td className="px-5 py-3.5">
                  <span className="text-[12px] font-mono text-[#64748b]">{event.id}</span>
                </td>
                <td className="px-5 py-3.5">
                  <span
                    className="text-[11px] font-mono font-medium px-2 py-1 rounded"
                    style={{
                      color: topicColors[event.topic] || "#64748b",
                      backgroundColor: (topicColors[event.topic] || "#64748b") + "10",
                    }}
                  >
                    {event.topic}
                  </span>
                </td>
                <td className="px-5 py-3.5">
                  <span className="text-[12px] font-medium text-[#0f172a]">{event.key}</span>
                </td>
                <td className="px-5 py-3.5">
                  <span className="text-[12px] text-[#475569]">{event.service}</span>
                </td>
                <td className="px-5 py-3.5">
                  <span className="text-[11px] font-medium text-[#64748b] bg-[#f8fafc] border border-[#e2e8f0] px-2 py-0.5 rounded">
                    {event.agent}
                  </span>
                </td>
                <td className="px-5 py-3.5">
                  <div className="flex flex-wrap gap-1">
                    {event.actions.map((a, i) => (
                      <span key={i} className="text-[10px] text-[#64748b] bg-[#f1f5f9] px-1.5 py-0.5 rounded">
                        {a}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-1">
                    <Clock className="w-3 h-3 text-[#94a3b8]" />
                    <span className="text-[12px] text-[#64748b]">{event.latency}</span>
                  </div>
                </td>
                <td className="px-5 py-3.5">
                  {event.status === "processed" ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#16a34a]">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Processed
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#d97706]">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      Escalated
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pipeline Visualization */}
      <div className="mt-8 border border-[#e2e8f0] rounded-xl p-6 bg-white">
        <h2 className="text-[15px] font-semibold text-[#0f172a] mb-1">Event Flow Architecture</h2>
        <p className="text-[12px] text-[#94a3b8] mb-6">How events propagate through the system</p>
        <div className="flex items-center justify-between px-4">
          {[
            { label: "Source", sub: "GitHub / CloudWatch / API", color: "#64748b" },
            { label: "Kafka", sub: "Event Bus (10 topics)", color: "#1e40af" },
            { label: "Agent", sub: "LangGraph State Machine", color: "#7c3aed" },
            { label: "Action", sub: "Jira / Notion / Slack", color: "#16a34a" },
            { label: "Storage", sub: "DynamoDB / S3 / Neo4j", color: "#0891b2" },
          ].map((step, i) => (
            <div key={step.label} className="flex items-center gap-6">
              <div className="text-center">
                <div
                  className="w-16 h-16 rounded-xl flex items-center justify-center mb-2 mx-auto border"
                  style={{ borderColor: step.color + "40", backgroundColor: step.color + "08" }}
                >
                  <Zap className="w-5 h-5" style={{ color: step.color }} />
                </div>
                <p className="text-[12px] font-semibold text-[#0f172a]">{step.label}</p>
                <p className="text-[10px] text-[#94a3b8]">{step.sub}</p>
              </div>
              {i < 4 && <ArrowRight className="w-5 h-5 text-[#cbd5e1] -mt-6" />}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
