import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Artilery — Autonomous CI/CD Orchestration",
  description: "AI-powered event-driven CI/CD platform with multi-agent orchestration",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="flex min-h-screen bg-white">
        <Sidebar />
        <main className="flex-1 ml-[260px] min-h-screen">
          {children}
        </main>
      </body>
    </html>
  );
}
