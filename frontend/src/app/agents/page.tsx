"use client";

import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock,
  Code2,
  GitPullRequest,
  MessageSquare,
  RefreshCw,
  Search,
  Server,
  Shield,
  Ticket,
  Zap,
} from "lucide-react";

const agents = [
  {
    name: "Triage Agent",
    description: "Autonomous bug triage — ingests bug reports, queries the knowledge graph for service owners, creates Jira tickets, mirrors to Notion, and sends Slack notifications.",
    status: "running",
    icon: Shield,
    color: "#1e40af",
    bg: "#eff6ff",
    kafkaIn: ["bug.ingested"],
    kafkaOut: ["ticket.created"],
    tools: ["Jira API", "Notion API", "Slack SDK", "Neo4j"],
    stats: { processed: 156, failed: 3, avgLatency: "1.4s", uptime: "99.98%" },
    stateNodes: ["classify_severity", "lookup_owner", "create_jira", "create_notion", "send_slack"],
  },
  {
    name: "Review Agent",
    description: "Automated PR review lifecycle — assigns reviewers based on skill-matching from the knowledge graph, tracks review state, and coordinates approval flow.",
    status: "running",
    icon: Code2,
    color: "#7c3aed",
    bg: "#f5f3ff",
    kafkaIn: ["pr.opened", "pr.reviewed", "pr.approved"],
    kafkaOut: ["pr.review.requested"],
    tools: ["GitHub API", "Neo4j", "Slack SDK", "DynamoDB"],
    stats: { processed: 89, failed: 1, avgLatency: "2.1s", uptime: "99.99%" },
    stateNodes: ["validate_pr", "match_reviewer", "assign_reviewer", "notify_reviewer", "track_state"],
  },
  {
    name: "Ops Agent",
    description: "Deployment monitoring and auto-resolution — triggers deployments, diagnoses failures with AI, performs auto-rollback, and resolves tickets on success.",
    status: "running",
    icon: Server,
    color: "#0891b2",
    bg: "#ecfeff",
    kafkaIn: ["deploy.triggered", "deploy.failed", "deploy.succeeded"],
    kafkaOut: ["ticket.resolved"],
    tools: ["CodeDeploy", "CloudWatch", "Gemini 2.5 Flash", "Slack SDK"],
    stats: { processed: 67, failed: 2, avgLatency: "3.8s", uptime: "99.95%" },
    stateNodes: ["check_deployment", "diagnose_failure", "rollback", "resolve_ticket", "notify_team"],
  },
  {
    name: "Chatbot Agent",
    description: "RAG-powered Q&A — classifies user intent, retrieves context from Neo4j, DynamoDB, and ChromaDB, then synthesizes answers with Gemini 2.5 Flash.",
    status: "running",
    icon: MessageSquare,
    color: "#16a34a",
    bg: "#f0fdf4",
    kafkaIn: [],
    kafkaOut: [],
    tools: ["Gemini 2.5 Flash", "Neo4j", "ChromaDB", "DynamoDB"],
    stats: { processed: 234, failed: 0, avgLatency: "0.9s", uptime: "100%" },
    stateNodes: ["classify_intent", "route_retrieval", "retrieve_context", "generate_answer"],
  },
];

export default function AgentsPage() {
  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[#0f172a] tracking-tight">AI Agents</h1>
        <p className="text-sm text-[#64748b] mt-1">
          Four autonomous LangGraph state machines processing events in real-time
        </p>
      </div>

      <div className="space-y-5">
        {agents.map((agent) => (
          <div key={agent.name} className="border border-[#e2e8f0] rounded-xl bg-white overflow-hidden">
            {/* Agent Header */}
            <div className="p-6 border-b border-[#f1f5f9]">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ backgroundColor: agent.bg }}>
                    <agent.icon className="w-5 h-5" style={{ color: agent.color }} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2.5">
                      <h2 className="text-[16px] font-semibold text-[#0f172a]">{agent.name}</h2>
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#16a34a] bg-[#f0fdf4] border border-[#bbf7d0] px-2 py-0.5 rounded-full">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#16a34a]" />
                        Running
                      </span>
                    </div>
                    <p className="text-[13px] text-[#64748b] mt-1 max-w-2xl">{agent.description}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Agent Body */}
            <div className="grid grid-cols-4 divide-x divide-[#f1f5f9]">
              {/* Stats */}
              <div className="p-5">
                <p className="text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider mb-3">Metrics</p>
                <div className="space-y-2.5">
                  <div className="flex justify-between">
                    <span className="text-[12px] text-[#64748b]">Processed</span>
                    <span className="text-[13px] font-semibold text-[#0f172a]">{agent.stats.processed}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[12px] text-[#64748b]">Failed</span>
                    <span className={`text-[13px] font-semibold ${agent.stats.failed > 0 ? "text-[#dc2626]" : "text-[#16a34a]"}`}>
                      {agent.stats.failed}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[12px] text-[#64748b]">Avg Latency</span>
                    <span className="text-[13px] font-semibold text-[#0f172a]">{agent.stats.avgLatency}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[12px] text-[#64748b]">Uptime</span>
                    <span className="text-[13px] font-semibold text-[#16a34a]">{agent.stats.uptime}</span>
                  </div>
                </div>
              </div>

              {/* Kafka Topics */}
              <div className="p-5">
                <p className="text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider mb-3">Kafka Topics</p>
                {agent.kafkaIn.length > 0 && (
                  <div className="mb-3">
                    <p className="text-[11px] text-[#94a3b8] mb-1.5">Consumes</p>
                    <div className="flex flex-wrap gap-1.5">
                      {agent.kafkaIn.map((t) => (
                        <span key={t} className="text-[11px] font-mono bg-[#f8fafc] border border-[#e2e8f0] px-2 py-0.5 rounded text-[#475569]">
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {agent.kafkaOut.length > 0 && (
                  <div>
                    <p className="text-[11px] text-[#94a3b8] mb-1.5">Produces</p>
                    <div className="flex flex-wrap gap-1.5">
                      {agent.kafkaOut.map((t) => (
                        <span key={t} className="text-[11px] font-mono bg-[#f8fafc] border border-[#e2e8f0] px-2 py-0.5 rounded text-[#475569]">
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {agent.kafkaIn.length === 0 && agent.kafkaOut.length === 0 && (
                  <p className="text-[12px] text-[#94a3b8] italic">API-only (no Kafka)</p>
                )}
              </div>

              {/* Tools */}
              <div className="p-5">
                <p className="text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider mb-3">Integrations</p>
                <div className="flex flex-wrap gap-1.5">
                  {agent.tools.map((tool) => (
                    <span key={tool} className="text-[11px] bg-[#f8fafc] border border-[#e2e8f0] px-2 py-1 rounded text-[#475569]">
                      {tool}
                    </span>
                  ))}
                </div>
              </div>

              {/* State Machine */}
              <div className="p-5">
                <p className="text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider mb-3">LangGraph Nodes</p>
                <div className="space-y-1.5">
                  {agent.stateNodes.map((node, i) => (
                    <div key={node} className="flex items-center gap-2">
                      <div className="w-5 h-5 rounded-full border border-[#e2e8f0] bg-[#f8fafc] flex items-center justify-center">
                        <span className="text-[9px] font-semibold text-[#64748b]">{i + 1}</span>
                      </div>
                      <span className="text-[12px] font-mono text-[#475569]">{node}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
