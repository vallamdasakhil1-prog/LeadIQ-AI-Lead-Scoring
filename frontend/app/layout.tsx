import type { Metadata } from "next";
import { Suspense } from "react";
import "@fontsource-variable/figtree";
import "./globals.css";
import { ThemeProvider } from "next-themes";
import { AppShell } from "@/components/app-shell";

export const metadata: Metadata = {
  title: "LeadIQ – explainable lead scoring",
  description: "Deterministic lead scoring with AI-written explanations.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <Suspense fallback={null}>
            <AppShell>{children}</AppShell>
          </Suspense>
        </ThemeProvider>
      </body>
    </html>
  );
}
