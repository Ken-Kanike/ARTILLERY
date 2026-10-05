"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Bot,
  Activity,
  MessageSquare,
  GitBranch,
  Settings,
  Boxes,
  Network,
  Zap,
} from "lucide-react";

const navigation = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard },
  { name: "Agents", href: "/agents", icon: Bot },
  { name: "Event Pipeline", href: "/events", icon: Activity },
  { name: "Knowledge Graph", href: "/graph", icon: Network },
  { name: "Chatbot", href: "/chatbot", icon: MessageSquare },
  { name: "Integrations", href: "/integrations", icon: Boxes },
  { name: "GitHub", href: "/github", icon: GitBranch },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 h-screen w-[260px] border-r border-[#e2e8f0] bg-white flex flex-col z-50">
      {/* Logo */}
      <div className="h-16 flex items-center gap-3 px-6 border-b border-[#e2e8f0]">
        <div className="w-8 h-8 bg-[#1e40af] rounded-lg flex items-center justify-center">
          <Zap className="w-4 h-4 text-white" />
        </div>
        <div>
          <h1 className="text-[15px] font-semibold text-[#0f172a] tracking-tight">Artilery</h1>
          <p className="text-[11px] text-[#94a3b8] font-medium tracking-wide uppercase">KAOS Platform</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        <p className="px-3 mb-2 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">
          Overview
        </p>
        {navigation.slice(0, 2).map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium transition-colors ${
                isActive
                  ? "bg-[#eff6ff] text-[#1e40af]"
                  : "text-[#475569] hover:bg-[#f8fafc] hover:text-[#0f172a]"
              }`}
            >
              <item.icon className={`w-[18px] h-[18px] ${isActive ? "text-[#1e40af]" : "text-[#94a3b8]"}`} />
              {item.name}
            </Link>
          );
        })}

        <p className="px-3 mt-6 mb-2 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">
          Operations
        </p>
        {navigation.slice(2, 5).map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium transition-colors ${
                isActive
                  ? "bg-[#eff6ff] text-[#1e40af]"
                  : "text-[#475569] hover:bg-[#f8fafc] hover:text-[#0f172a]"
              }`}
            >
              <item.icon className={`w-[18px] h-[18px] ${isActive ? "text-[#1e40af]" : "text-[#94a3b8]"}`} />
              {item.name}
            </Link>
          );
        })}

        <p className="px-3 mt-6 mb-2 text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wider">
          Integrations
        </p>
        {navigation.slice(5).map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium transition-colors ${
                isActive
                  ? "bg-[#eff6ff] text-[#1e40af]"
                  : "text-[#475569] hover:bg-[#f8fafc] hover:text-[#0f172a]"
              }`}
            >
              <item.icon className={`w-[18px] h-[18px] ${isActive ? "text-[#1e40af]" : "text-[#94a3b8]"}`} />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-[#e2e8f0]">
        <div className="flex items-center gap-2 px-2">
          <div className="w-2 h-2 rounded-full bg-[#16a34a] animate-pulse" />
          <span className="text-[12px] text-[#64748b]">All systems operational</span>
        </div>
      </div>
    </aside>
  );
}
