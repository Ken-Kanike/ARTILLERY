"use client";

import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Bot,
  CheckCircle2,
  Clock,
  GitPullRequest,
  MessageSquare,
  Server,
  Ticket,
  Zap,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
} from "recharts";

/* ── Static data for dashboard ──────────────────────────────────────── */

const kpis = [
  {
    label: "Events Processed",
    value: "2,847",
    change: "+12.4%",
    trend: "up" as const,
    icon: Activity,
    color: "#1e40af",
    bg: "#eff6ff",
  },
  {
    label: "Tickets Created",
    value: "156",
    change: "+8.2%",
    trend: "up" as const,
    icon: Ticket,
    color: "#16a34a",
    bg: "#f0fdf4",
  },
  {
    label: "Avg. Triage Time",
    value: "1.4s",
    change: "-23%",
    trend: "down" as const,
    icon: Clock,
    color: "#7c3aed",
    bg: "#f5f3ff",
  },
  {
    label: "Agent Uptime",
    value: "99.97%",
    change: "+0.02%",
    trend: "up" as const,
    icon: Server,
    color: "#0891b2",
    bg: "#ecfeff",
  },
];

const eventVolumeData = [
  { time: "00:00", bugs: 12, prs: 8, deploys: 3 },
  { time: "04:00", bugs: 5, prs: 3, deploys: 1 },
  { time: "08:00", bugs: 24, prs: 18, deploys: 7 },
  { time: "10:00", bugs: 31, prs: 22, deploys: 12 },
  { time: "12:00", bugs: 28, prs: 25, deploys: 15 },
  { time: "14:00", bugs: 35, prs: 30, deploys: 18 },
  { time: "16:00", bugs: 42, prs: 28, deploys: 14 },
  { time: "18:00", bugs: 38, prs: 20, deploys: 9 },
  { time: "20:00", bugs: 18, prs: 12, deploys: 5 },
  { time: "22:00", bugs: 10, prs: 6, deploys: 2 },
];

const agentPerformance = [
  { name: "Triage", processed: 156, failed: 3, latency: 1.4 },
  { name: "Review", processed: 89, failed: 1, latency: 2.1 },
  { name: "Ops", processed: 67, failed: 2, latency: 3.8 },
  { name: "Chatbot", processed: 234, failed: 0, latency: 0.9 },
];

const severityDistribution = [
  { name: "Critical", value: 12, color: "#dc2626" },
  { name: "High", value: 34, color: "#f97316" },
  { name: "Medium", value: 68, color: "#eab308" },
  { name: "Low", value: 42, color: "#22c55e" },
];

const recentEvents = [
  {
    id: "EVT-001",
    type: "bug.ingested",
    service: "PaymentService",
    status: "processed",
    time: "2 min ago",
    agent: "Triage",
  },
  {
    id: "EVT-002",
    type: "pr.opened",
    service: "AuthService",
    status: "processed",
    time: "5 min ago",
    agent: "Review",
  },
  {
    id: "EVT-003",
    type: "deploy.succeeded",
    service: "UserService",
    status: "processed",
    time: "8 min ago",
    agent: "Ops",
  },
  {
    id: "EVT-004",
    type: "deploy.failed",
    service: "NotificationService",
    status: "escalated",
    time: "12 min ago",
    agent: "Ops",
  },
  {
    id: "EVT-005",
    type: "pr.approved",
    service: "APIGateway",
    status: "processed",
    time: "15 min ago",
    agent: "Review",
  },
  {
    id: "EVT-006",
    type: "bug.ingested",
    service: "PaymentService",
    status: "processed",
    time: "18 min ago",
    agent: "Triage",
  },
];

const topicStats = [
  { topic: "bug.ingested", count: 156, dlq: 3 },
  { topic: "ticket.created", count: 153, dlq: 0 },
  { topic: "pr.opened", count: 89, dlq: 1 },
  { topic: "pr.approved", count: 76, dlq: 0 },
  { topic: "deploy.triggered", count: 67, dlq: 0 },
  { topic: "deploy.failed", count: 8, dlq: 2 },
  { topic: "deploy.succeeded", count: 59, dlq: 0 },
];

/* ── Page ──────────────────────────────────────────────────────────── */

export default function DashboardPage() {
  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[#0f172a] tracking-tight">Dashboard</h1>
        <p className="text-sm text-[#64748b] mt-1">
          Real-time overview of the Artilery autonomous orchestration platform
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-5 mb-8">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="border border-[#e2e8f0] rounded-xl p-5 bg-white">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[13px] font-medium text-[#64748b]">{kpi.label}</span>
              <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: kpi.bg }}>
                <kpi.icon className="w-[18px] h-[18px]" style={{ color: kpi.color }} />
              </div>
            </div>
            <p className="text-[28px] font-semibold text-[#0f172a] tracking-tight">{kpi.value}</p>
            <div className="flex items-center gap-1 mt-1">
              {kpi.trend === "up" ? (
                <ArrowUp className="w-3.5 h-3.5 text-[#16a34a]" />
              ) : (
                <ArrowDown className="w-3.5 h-3.5 text-[#16a34a]" />
              )}
              <span className="text-[12px] font-medium text-[#16a34a]">{kpi.change}</span>
              <span className="text-[12px] text-[#94a3b8] ml-1">vs last week</span>
            </div>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-3 gap-5 mb-8">
        {/* Event Volume Chart */}
        <div className="col-span-2 border border-[#e2e8f0] rounded-xl p-5 bg-white">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-[15px] font-semibold text-[#0f172a]">Event Volume</h2>
              <p className="text-[12px] text-[#94a3b8] mt-0.5">Events processed by type over 24h</p>
            </div>
            <div className="flex items-center gap-4 text-[12px]">
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-[#1e40af]" />
                <span className="text-[#64748b]">Bugs</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-[#7c3aed]" />
                <span className="text-[#64748b]">PRs</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-[#0891b2]" />
                <span className="text-[#64748b]">Deploys</span>
              </div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={eventVolumeData}>
              <defs>
                <linearGradient id="bugFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#1e40af" stopOpacity={0.08} />
                  <stop offset="100%" stopColor="#1e40af" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="prFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#7c3aed" stopOpacity={0.08} />
                  <stop offset="100%" stopColor="#7c3aed" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  background: "#fff",
                  border: "1px solid #e2e8f0",
                  borderRadius: "8px",
                  fontSize: "12px",
                  boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.05)",
                }}
              />
              <Area type="monotone" dataKey="bugs" stroke="#1e40af" strokeWidth={2} fill="url(#bugFill)" />
              <Area type="monotone" dataKey="prs" stroke="#7c3aed" strokeWidth={2} fill="url(#prFill)" />
              <Area type="monotone" dataKey="deploys" stroke="#0891b2" strokeWidth={1.5} fill="transparent" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Severity Distribution */}
        <div className="border border-[#e2e8f0] rounded-xl p-5 bg-white">
          <h2 className="text-[15px] font-semibold text-[#0f172a] mb-1">Bug Severity</h2>
          <p className="text-[12px] text-[#94a3b8] mb-4">Distribution across active tickets</p>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie
                data={severityDistribution}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={75}
                paddingAngle={3}
                dataKey="value"
                stroke="none"
              >
                {severityDistribution.map((entry) => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "#fff",
                  border: "1px solid #e2e8f0",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 justify-center mt-2">
            {severityDistribution.map((s) => (
              <div key={s.name} className="flex items-center gap-1.5 text-[11px]">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: s.color }} />
                <span className="text-[#64748b]">{s.name}</span>
                <span className="font-medium text-[#0f172a]">{s.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-5 gap-5">
        {/* Agent Performance */}
        <div className="col-span-2 border border-[#e2e8f0] rounded-xl p-5 bg-white">
          <h2 className="text-[15px] font-semibold text-[#0f172a] mb-1">Agent Performance</h2>
          <p className="text-[12px] text-[#94a3b8] mb-5">Events processed per agent</p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={agentPerformance} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  background: "#fff",
                  border: "1px solid #e2e8f0",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
              <Bar dataKey="processed" fill="#1e40af" radius={[4, 4, 0, 0]} />
              <Bar dataKey="failed" fill="#fca5a5" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Recent Events */}
        <div className="col-span-3 border border-[#e2e8f0] rounded-xl bg-white">
          <div className="px-5 pt-5 pb-3 border-b border-[#f1f5f9]">
            <h2 className="text-[15px] font-semibold text-[#0f172a]">Recent Events</h2>
            <p className="text-[12px] text-[#94a3b8] mt-0.5">Live feed from Apache Kafka</p>
          </div>
          <div className="divide-y divide-[#f8fafc]">
            {recentEvents.map((event) => (
              <div key={event.id} className="flex items-center justify-between px-5 py-3 hover:bg-[#fafbfc] transition-colors">
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                    event.status === "escalated" ? "bg-[#fef2f2]" : "bg-[#f0fdf4]"
                  }`}>
                    {event.status === "escalated" ? (
                      <AlertTriangle className="w-4 h-4 text-[#dc2626]" />
                    ) : (
                      <CheckCircle2 className="w-4 h-4 text-[#16a34a]" />
                    )}
                  </div>
                  <div>
                    <p className="text-[13px] font-medium text-[#0f172a]">{event.type}</p>
                    <p className="text-[11px] text-[#94a3b8]">{event.service}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-[11px] font-medium text-[#64748b] bg-[#f8fafc] px-2 py-0.5 rounded">
                    {event.agent}
                  </span>
                  <span className="text-[11px] text-[#94a3b8] w-16 text-right">{event.time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Kafka Topics */}
      <div className="mt-8 border border-[#e2e8f0] rounded-xl bg-white">
        <div className="px-5 pt-5 pb-3 border-b border-[#f1f5f9]">
          <h2 className="text-[15px] font-semibold text-[#0f172a]">Kafka Topic Health</h2>
          <p className="text-[12px] text-[#94a3b8] mt-0.5">Message throughput and dead letter queue status</p>
        </div>
        <div className="grid grid-cols-7 gap-0 divide-x divide-[#f1f5f9]">
          {topicStats.map((t) => (
            <div key={t.topic} className="p-4 text-center">
              <p className="text-[11px] font-medium text-[#64748b] truncate mb-2">{t.topic}</p>
              <p className="text-xl font-semibold text-[#0f172a]">{t.count}</p>
              <div className={`mt-1 text-[11px] font-medium ${t.dlq > 0 ? "text-[#dc2626]" : "text-[#16a34a]"}`}>
                {t.dlq > 0 ? `${t.dlq} in DLQ` : "DLQ clear"}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
