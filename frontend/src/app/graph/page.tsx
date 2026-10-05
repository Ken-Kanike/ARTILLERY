"use client";

import { useEffect, useState } from "react";
import {
  ArrowRight,
  Box,
  Database,
  GitFork,
  Loader2,
  Network,
  RefreshCw,
  Shield,
  User,
  Users,
} from "lucide-react";

interface GraphNode {
  id: string;
  label: string;
  name: string;
  properties: Record<string, string>;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const API = "http://localhost:8001";

const labelColors: Record<string, { bg: string; border: string; text: string }> = {
  Service: { bg: "#eff6ff", border: "#bfdbfe", text: "#1e40af" },
  Team: { bg: "#f0fdf4", border: "#bbf7d0", text: "#16a34a" },
  Developer: { bg: "#f5f3ff", border: "#ddd6fe", text: "#7c3aed" },
  Skill: { bg: "#fff7ed", border: "#fed7aa", text: "#c2410c" },
};

const defaultColor = { bg: "#f8fafc", border: "#e2e8f0", text: "#475569" };

/* ── Simple Force-Directed Layout ──────────────────────────────────── */

function computeLayout(nodes: GraphNode[], edges: GraphEdge[], width: number, height: number) {
  const positions: Record<string, { x: number; y: number }> = {};

  // Group nodes by label
  const groups: Record<string, GraphNode[]> = {};
  nodes.forEach((n) => {
    const g = n.label || "Other";
    if (!groups[g]) groups[g] = [];
    groups[g].push(n);
  });

  const groupNames = Object.keys(groups);
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;

  groupNames.forEach((group, gi) => {
    const angle = (2 * Math.PI * gi) / groupNames.length - Math.PI / 2;
    const groupCx = cx + radius * Math.cos(angle);
    const groupCy = cy + radius * Math.sin(angle);
    const members = groups[group];
    const spread = Math.min(80, 200 / members.length);

    members.forEach((node, ni) => {
      const memberAngle = (2 * Math.PI * ni) / members.length;
      const memberRadius = members.length === 1 ? 0 : spread;
      positions[node.id] = {
        x: groupCx + memberRadius * Math.cos(memberAngle),
        y: groupCy + memberRadius * Math.sin(memberAngle),
      };
    });
  });

  return positions;
}

/* ── Graph Visualization Component ─────────────────────────────────── */

function GraphVisualization({ data }: { data: GraphData }) {
  const width = 900;
  const height = 500;
  const positions = computeLayout(data.nodes, data.edges, width, height);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ maxHeight: 500 }}>
      {/* Edges */}
      {data.edges.map((edge, i) => {
        const from = positions[edge.source];
        const to = positions[edge.target];
        if (!from || !to) return null;

        const midX = (from.x + to.x) / 2;
        const midY = (from.y + to.y) / 2 - 10;

        return (
          <g key={`edge-${i}`}>
            <line
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke="#e2e8f0"
              strokeWidth={1.5}
              markerEnd="url(#arrowhead)"
            />
            <text
              x={midX}
              y={midY}
              textAnchor="middle"
              fill="#94a3b8"
              fontSize={8}
              fontFamily="ui-monospace, monospace"
            >
              {edge.type}
            </text>
          </g>
        );
      })}

      {/* Arrow marker */}
      <defs>
        <marker
          id="arrowhead"
          viewBox="0 0 10 7"
          refX="10"
          refY="3.5"
          markerWidth="8"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <polygon points="0 0, 10 3.5, 0 7" fill="#cbd5e1" />
        </marker>
      </defs>

      {/* Nodes */}
      {data.nodes.map((node) => {
        const pos = positions[node.id];
        if (!pos) return null;
        const colors = labelColors[node.label] || defaultColor;
        const isHovered = hoveredNode === node.id;

        return (
          <g
            key={node.id}
            onMouseEnter={() => setHoveredNode(node.id)}
            onMouseLeave={() => setHoveredNode(null)}
            style={{ cursor: "pointer" }}
          >
            <circle
              cx={pos.x}
              cy={pos.y}
              r={isHovered ? 28 : 24}
              fill={colors.bg}
              stroke={colors.border}
              strokeWidth={isHovered ? 2 : 1.5}
              style={{ transition: "r 0.15s ease, stroke-width 0.15s ease" }}
            />
            <text
              x={pos.x}
              y={pos.y - 1}
              textAnchor="middle"
              dominantBaseline="central"
              fill={colors.text}
              fontSize={9}
              fontWeight={600}
              fontFamily="Inter, system-ui, sans-serif"
            >
              {node.name.length > 10 ? node.name.slice(0, 9) + ".." : node.name}
            </text>
            <text
              x={pos.x}
              y={pos.y + 34}
              textAnchor="middle"
              fill="#94a3b8"
              fontSize={8}
              fontFamily="Inter, system-ui, sans-serif"
            >
              {node.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ── Page ──────────────────────────────────────────────────────────── */

export default function GraphPage() {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [services, setServices] = useState<any[]>([]);
  const [teams, setTeams] = useState<any[]>([]);
  const [oncall, setOncall] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [graphRes, svcRes, teamRes, oncallRes] = await Promise.all([
        fetch(`${API}/graph/full`),
        fetch(`${API}/graph/services`),
        fetch(`${API}/graph/teams`),
        fetch(`${API}/graph/oncall`),
      ]);

      if (!graphRes.ok) throw new Error("API unavailable");

      const [graph, svcs, tms, oc] = await Promise.all([
        graphRes.json(),
        svcRes.json(),
        teamRes.json(),
        oncallRes.json(),
      ]);

      setGraphData(graph);
      setServices(svcs.services || []);
      setTeams(tms.teams || []);
      setOncall(oc.oncall || []);
    } catch {
      setError("Unable to connect to the API. Run: uvicorn api.main:app --reload");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const graphStats = [
    { label: "Teams", value: teams.length || "—", icon: Users },
    { label: "Developers", value: oncall.length || "—", icon: User },
    { label: "Services", value: services.length || "—", icon: Box },
    { label: "Relationships", value: graphData?.edges.length || "—", icon: GitFork },
  ];

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-[#0f172a] tracking-tight">Knowledge Graph</h1>
          <p className="text-sm text-[#64748b] mt-1">
            Live Neo4j property graph — team structure, service ownership, and dependencies
          </p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-2 px-3 py-2 text-[13px] font-medium text-[#475569] border border-[#e2e8f0] rounded-lg hover:bg-[#f8fafc] transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-96">
          <Loader2 className="w-6 h-6 text-[#94a3b8] animate-spin" />
        </div>
      ) : error ? (
        <div className="border border-[#fde68a] bg-[#fffbeb] rounded-xl p-6 text-center">
          <p className="text-[14px] text-[#92400e] font-medium">{error}</p>
          <p className="text-[12px] text-[#b45309] mt-1">Start the backend API to load live data from Neo4j</p>
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-4 gap-5 mb-8">
            {graphStats.map((stat) => (
              <div key={stat.label} className="border border-[#e2e8f0] rounded-xl p-5 bg-white">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-[#f8fafc] flex items-center justify-center">
                    <stat.icon className="w-[18px] h-[18px] text-[#64748b]" />
                  </div>
                  <div>
                    <p className="text-xl font-semibold text-[#0f172a]">{stat.value}</p>
                    <p className="text-[12px] text-[#94a3b8]">{stat.label}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Interactive Graph */}
          <div className="border border-[#e2e8f0] rounded-xl bg-white mb-8 overflow-hidden">
            <div className="px-6 pt-5 pb-3 border-b border-[#f1f5f9] flex items-center justify-between">
              <div>
                <h2 className="text-[15px] font-semibold text-[#0f172a]">Interactive Graph</h2>
                <p className="text-[12px] text-[#94a3b8] mt-0.5">
                  {graphData?.nodes.length} nodes, {graphData?.edges.length} relationships
                </p>
              </div>
              <div className="flex items-center gap-3">
                {Object.entries(labelColors).map(([label, colors]) => (
                  <div key={label} className="flex items-center gap-1.5 text-[11px]">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: colors.bg, border: `1.5px solid ${colors.border}` }} />
                    <span className="text-[#64748b]">{label}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="p-4">
              {graphData && <GraphVisualization data={graphData} />}
            </div>
          </div>

          {/* Service Dependency Map */}
          <div className="border border-[#e2e8f0] rounded-xl bg-white mb-8">
            <div className="px-6 pt-5 pb-3 border-b border-[#f1f5f9]">
              <h2 className="text-[15px] font-semibold text-[#0f172a]">Service Dependencies</h2>
              <p className="text-[12px] text-[#94a3b8] mt-0.5">
                MATCH (a:Service)-[:DEPENDS_ON]-&gt;(b:Service) RETURN a, b
              </p>
            </div>
            <div className="p-6">
              <div className="space-y-4">
                {services
                  .filter((s) => s.dependencies && s.dependencies.length > 0)
                  .map((svc) => (
                    <div key={svc.name} className="flex items-center gap-4">
                      <div className="w-44 text-right">
                        <span className="text-[13px] font-semibold text-[#0f172a] bg-[#f8fafc] border border-[#e2e8f0] px-3 py-1.5 rounded-lg inline-block">
                          {svc.name}
                        </span>
                      </div>
                      <ArrowRight className="w-4 h-4 text-[#cbd5e1]" />
                      <div className="flex gap-2">
                        {svc.dependencies.map((dep: string) => (
                          <span
                            key={dep}
                            className="text-[12px] font-medium text-[#475569] bg-[#eff6ff] border border-[#bfdbfe] px-3 py-1.5 rounded-lg"
                          >
                            {dep}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          </div>

          {/* Service Registry Table */}
          <div className="border border-[#e2e8f0] rounded-xl bg-white mb-8">
            <div className="px-6 pt-5 pb-3 border-b border-[#f1f5f9]">
              <h2 className="text-[15px] font-semibold text-[#0f172a]">Service Registry</h2>
              <p className="text-[12px] text-[#94a3b8] mt-0.5">All microservices with ownership and on-call assignments</p>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-[#e2e8f0] bg-[#fafbfc]">
                  <th className="text-left px-6 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Service</th>
                  <th className="text-left px-6 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Team</th>
                  <th className="text-left px-6 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">On-Call</th>
                  <th className="text-left px-6 py-3 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">Dependencies</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f8fafc]">
                {services.map((svc) => (
                  <tr key={svc.name} className="hover:bg-[#fafbfc] transition-colors">
                    <td className="px-6 py-3.5">
                      <div className="flex items-center gap-2">
                        <Box className="w-4 h-4 text-[#94a3b8]" />
                        <span className="text-[13px] font-medium text-[#0f172a]">{svc.name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-3.5">
                      <span className="text-[12px] text-[#475569]">{svc.teams?.join(", ") || "—"}</span>
                    </td>
                    <td className="px-6 py-3.5">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-[#f1f5f9] flex items-center justify-center">
                          <User className="w-3 h-3 text-[#64748b]" />
                        </div>
                        <span className="text-[12px] text-[#475569]">{svc.oncall?.join(", ") || "—"}</span>
                      </div>
                    </td>
                    <td className="px-6 py-3.5">
                      <div className="flex gap-1.5">
                        {svc.dependencies?.length > 0 ? svc.dependencies.map((d: string) => (
                          <span key={d} className="text-[10px] bg-[#f1f5f9] px-1.5 py-0.5 rounded text-[#64748b]">{d}</span>
                        )) : <span className="text-[11px] text-[#94a3b8]">None</span>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Team Directory */}
          <div>
            <h2 className="text-[13px] font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">
              Team Directory
            </h2>
            <div className="grid grid-cols-3 gap-5">
              {teams.map((team) => (
                <div key={team.name} className="border border-[#e2e8f0] rounded-xl bg-white overflow-hidden">
                  <div className="px-5 py-4 border-b border-[#f1f5f9] flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Users className="w-4 h-4 text-[#64748b]" />
                      <h3 className="text-[14px] font-semibold text-[#0f172a]">Team {team.name}</h3>
                    </div>
                    <span className="text-[11px] text-[#94a3b8]">{team.members?.length || 0} members</span>
                  </div>
                  <div className="divide-y divide-[#f8fafc]">
                    {team.members?.map((member: any) => (
                      <div key={member.name} className="px-5 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-full bg-[#f1f5f9] flex items-center justify-center">
                            <User className="w-3.5 h-3.5 text-[#64748b]" />
                          </div>
                          <div>
                            <p className="text-[13px] font-medium text-[#0f172a]">{member.name}</p>
                            <p className="text-[11px] text-[#94a3b8]">{member.email}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="px-5 py-3 bg-[#fafbfc] border-t border-[#f1f5f9]">
                    <p className="text-[11px] text-[#94a3b8]">
                      Owns: {team.services?.join(", ") || "—"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
