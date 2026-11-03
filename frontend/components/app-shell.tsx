"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { BarChart3, LayoutDashboard, Moon, PlusCircle, Sun, Users, Target } from "lucide-react";
import { useSyncExternalStore } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/leads", label: "Leads", icon: Users },
  { href: "/leads/new", label: "Add lead", icon: PlusCircle },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
];

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(() => () => {}, () => true, () => false);
  const dark = mounted && resolvedTheme === "dark";
  return (
    <Button variant="ghost" size="icon" aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => setTheme(dark ? "light" : "dark")}>
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const active = (href: string) =>
    href === "/" ? path === "/" : href === "/leads" ? path === "/leads" || /^\/leads\/\d+/.test(path) : path.startsWith(href);
  return (
    <div className="md:grid md:grid-cols-[232px_1fr] min-h-screen">
      <aside className="hidden md:flex flex-col border-r border-line bg-surface px-4 py-5 sticky top-0 h-screen">
        <Link href="/" className="flex items-center gap-2 px-2 mb-8">
          <span className="grid size-8 place-items-center rounded-lg bg-accent text-accent-ink"><Target className="size-4" /></span>
          <span className="text-lg font-bold tracking-tight">LeadIQ</span>
        </Link>
        <nav className="flex flex-col gap-1" aria-label="Main">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}
              className={cn("flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active(href) ? "bg-soft text-ink" : "text-muted hover:bg-soft hover:text-ink")}>
              <Icon className="size-4" aria-hidden /> {label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto flex items-center justify-between px-2 text-xs text-muted">
          <span>Scores are rule-based.<br />AI only explains.</span>
          <ThemeToggle />
        </div>
      </aside>
      <div className="min-w-0">
        <header className="md:hidden sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-line bg-surface px-3 py-2">
          <nav className="flex gap-1 overflow-x-auto" aria-label="Main">
            {NAV.map(({ href, label, icon: Icon }) => (
              <Link key={href} href={href} aria-label={label} aria-current={active(href) ? "page" : undefined}
                className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-2 text-[13px] font-medium whitespace-nowrap",
                  active(href) ? "bg-soft text-ink" : "text-muted")}>
                <Icon className="size-4" aria-hidden /> <span className={active(href) ? "" : "sr-only"}>{label}</span>
              </Link>
            ))}
          </nav>
          <ThemeToggle />
        </header>
        <main className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8 md:py-8">{children}</main>
      </div>
    </div>
  );
}
