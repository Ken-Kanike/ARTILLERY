"use client";

import {
  ArrowRight,
  CheckCircle2,
  Clock,
  Code2,
  Copy,
  ExternalLink,
  GitBranch,
  GitMerge,
  GitPullRequest,
  Link2,
  MessageSquare,
  Shield,
  Terminal,
  User,
  XCircle,
} from "lucide-react";
import { useState } from "react";

const webhookEndpoint = "http://localhost:8001/webhook/github";

const pullRequests = [
  {
    number: 47,
    title: "Fix transaction timeout in PaymentService checkout flow",
    author: "swarnim-bane",
    branch: "fix/ART-3-payment-timeout",
    base: "main",
    status: "open",
    reviewState: "pending",
    service: "PaymentService",
    jiraKey: "ART-3",
    created: "2 hours ago",
    reviewers: ["arjun.mehta"],
    checks: { passed: 12, failed: 0 },
  },
  {
    number: 46,
    title: "Add rate limiting to AuthService login endpoint",
    author: "arjun-mehta",
    branch: "feat/ART-2-rate-limiting",
    base: "main",
    status: "merged",
    reviewState: "approved",
    service: "AuthService",
    jiraKey: "ART-2",
    created: "1 day ago",
    reviewers: ["swarnim.bane", "rohan.desai"],
    checks: { passed: 12, failed: 0 },
  },
  {
    number: 45,
    title: "Refactor UserService profile API response schema",
    author: "ananya-iyer",
    branch: "refactor/user-profile-schema",
    base: "main",
    status: "closed",
    reviewState: "changes_requested",
    service: "UserService",
    jiraKey: null,
    created: "3 days ago",
    reviewers: ["priya.sharma"],
    checks: { passed: 11, failed: 1 },
  },
  {
    number: 44,
    title: "Update APIGateway CORS policy for new frontend",
    author: "rohan-desai",
    branch: "fix/cors-policy-update",
    base: "main",
    status: "merged",
    reviewState: "approved",
    service: "APIGateway",
    jiraKey: null,
    created: "5 days ago",
    reviewers: ["swarnim.bane"],
    checks: { passed: 12, failed: 0 },
  },
];

const webhookEvents = [
  { event: "pull_request", action: "opened", topic: "pr.opened", description: "New PR opened or updated" },
  { event: "pull_request", action: "closed (merged)", topic: "pr.approved", description: "PR merged into base branch" },
  { event: "pull_request_review", action: "submitted (approved)", topic: "pr.approved", description: "Reviewer approved the PR" },
  { event: "pull_request_review", action: "submitted (changes_requested)", topic: "pr.reviewed", description: "Reviewer requested changes" },
  { event: "ping", action: "—", topic: "—", description: "Webhook configuration verification" },
];

export default function GitHubPage() {
  const [copied, setCopied] = useState(false);

  const copyUrl = () => {
    navigator.clipboard.writeText(webhookEndpoint);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[#0f172a] tracking-tight">GitHub Integration</h1>
        <p className="text-sm text-[#64748b] mt-1">
          Webhook-driven PR lifecycle management with HMAC-SHA256 validation
        </p>
      </div>

      {/* Webhook Setup */}
      <div className="border border-[#e2e8f0] rounded-xl bg-white mb-8 overflow-hidden">
        <div className="px-6 pt-5 pb-3 border-b border-[#f1f5f9]">
          <h2 className="text-[15px] font-semibold text-[#0f172a]">Webhook Configuration</h2>
          <p className="text-[12px] text-[#94a3b8] mt-0.5">
            Add this webhook to your GitHub repository: Settings &gt; Webhooks &gt; Add Webhook
          </p>
        </div>
        <div className="p-6">
          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider block mb-2">
                Payload URL
              </label>
              <div className="flex items-center gap-2">
                <div className="flex-1 bg-[#f8fafc] border border-[#e2e8f0] rounded-lg px-3 py-2.5 font-mono text-[13px] text-[#475569]">
                  {webhookEndpoint}
                </div>
                <button
                  onClick={copyUrl}
                  className="w-9 h-9 flex items-center justify-center border border-[#e2e8f0] rounded-lg hover:bg-[#f8fafc] transition-colors"
                >
                  {copied ? (
                    <CheckCircle2 className="w-4 h-4 text-[#16a34a]" />
                  ) : (
                    <Copy className="w-4 h-4 text-[#64748b]" />
                  )}
                </button>
              </div>
            </div>
            <div>
              <label className="text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider block mb-2">
                Details
              </label>
              <div className="space-y-2">
                <div className="flex items-center justify-between bg-[#f8fafc] border border-[#e2e8f0] rounded-lg px-3 py-2">
                  <span className="text-[12px] text-[#64748b]">Content Type</span>
                  <span className="text-[12px] font-mono text-[#0f172a]">application/json</span>
                </div>
                <div className="flex items-center justify-between bg-[#f8fafc] border border-[#e2e8f0] rounded-lg px-3 py-2">
                  <span className="text-[12px] text-[#64748b]">Security</span>
                  <span className="text-[12px] font-medium text-[#0f172a] flex items-center gap-1">
                    <Shield className="w-3 h-3 text-[#16a34a]" />
                    HMAC-SHA256
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Webhook Event Mapping */}
      <div className="border border-[#e2e8f0] rounded-xl bg-white mb-8">
        <div className="px-6 pt-5 pb-3 border-b border-[#f1f5f9]">
          <h2 className="text-[15px] font-semibold text-[#0f172a]">Event Mapping</h2>
          <p className="text-[12px] text-[#94a3b8] mt-0.5">GitHub events mapped to Kafka topics</p>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#e2e8f0] bg-[#fafbfc]">
              <th className="text-left px-6 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">GitHub Event</th>
              <th className="text-left px-6 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Action</th>
              <th className="text-left px-6 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider"></th>
              <th className="text-left px-6 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Kafka Topic</th>
              <th className="text-left px-6 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Description</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#f8fafc]">
            {webhookEvents.map((we, i) => (
              <tr key={i} className="hover:bg-[#fafbfc]">
                <td className="px-6 py-3">
                  <span className="text-[12px] font-mono text-[#475569]">{we.event}</span>
                </td>
                <td className="px-6 py-3">
                  <span className="text-[12px] text-[#64748b]">{we.action}</span>
                </td>
                <td className="px-6 py-3">
                  <ArrowRight className="w-4 h-4 text-[#cbd5e1]" />
                </td>
                <td className="px-6 py-3">
                  <span className="text-[12px] font-mono font-medium text-[#1e40af] bg-[#eff6ff] px-2 py-0.5 rounded">
                    {we.topic}
                  </span>
                </td>
                <td className="px-6 py-3">
                  <span className="text-[12px] text-[#64748b]">{we.description}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* PR List */}
      <div className="border border-[#e2e8f0] rounded-xl bg-white">
        <div className="px-6 pt-5 pb-3 border-b border-[#f1f5f9]">
          <h2 className="text-[15px] font-semibold text-[#0f172a]">Pull Requests</h2>
          <p className="text-[12px] text-[#94a3b8] mt-0.5">Tracked by the Review Agent</p>
        </div>
        <div className="divide-y divide-[#f8fafc]">
          {pullRequests.map((pr) => (
            <div key={pr.number} className="px-6 py-4 hover:bg-[#fafbfc] transition-colors">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center mt-0.5 ${
                    pr.status === "merged"
                      ? "bg-[#f5f3ff]"
                      : pr.status === "open"
                        ? "bg-[#f0fdf4]"
                        : "bg-[#f8fafc]"
                  }`}>
                    {pr.status === "merged" ? (
                      <GitMerge className="w-4 h-4 text-[#7c3aed]" />
                    ) : pr.status === "open" ? (
                      <GitPullRequest className="w-4 h-4 text-[#16a34a]" />
                    ) : (
                      <XCircle className="w-4 h-4 text-[#94a3b8]" />
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[14px] font-medium text-[#0f172a]">{pr.title}</span>
                      <span className="text-[11px] text-[#94a3b8]">#{pr.number}</span>
                    </div>
                    <div className="flex items-center gap-3 mt-1.5">
                      <span className="text-[11px] text-[#64748b] flex items-center gap-1">
                        <User className="w-3 h-3" />
                        {pr.author}
                      </span>
                      <span className="text-[11px] text-[#64748b] flex items-center gap-1">
                        <GitBranch className="w-3 h-3" />
                        {pr.branch}
                      </span>
                      <span className="text-[11px] text-[#94a3b8]">{pr.created}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {pr.jiraKey && (
                    <span className="text-[11px] font-medium text-[#1e40af] bg-[#eff6ff] border border-[#bfdbfe] px-2 py-0.5 rounded">
                      {pr.jiraKey}
                    </span>
                  )}
                  <span className="text-[11px] font-medium text-[#64748b] bg-[#f8fafc] border border-[#e2e8f0] px-2 py-0.5 rounded">
                    {pr.service}
                  </span>
                  <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${
                    pr.status === "merged"
                      ? "text-[#7c3aed] bg-[#f5f3ff] border border-[#ddd6fe]"
                      : pr.status === "open"
                        ? "text-[#16a34a] bg-[#f0fdf4] border border-[#bbf7d0]"
                        : "text-[#64748b] bg-[#f8fafc] border border-[#e2e8f0]"
                  }`}>
                    {pr.status === "merged" ? "Merged" : pr.status === "open" ? "Open" : "Closed"}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
