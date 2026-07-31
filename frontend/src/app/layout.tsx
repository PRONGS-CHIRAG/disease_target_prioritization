import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import { Suspense } from "react";

import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";
import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

const bodyFont = IBM_Plex_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const headingFont = Source_Serif_4({
  variable: "--font-heading",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

const dataFont = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Disease–Target Prioritization",
  description:
    "Ranks candidate therapeutic targets for a disease from integrated public evidence — a research-support prototype, not for medical decisions.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${bodyFont.variable} ${headingFont.variable} ${dataFont.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="h-full">
        <Providers>
          {/* AppShell's disease picker and nav also read useSearchParams
              via nuqs (useDiseaseId) — one boundary here covers the shell
              itself; each page additionally wraps its own content so only
              the inner region re-suspends on navigation, not the sidebar. */}
          <Suspense fallback={null}>
            <AppShell>{children}</AppShell>
          </Suspense>
          <Toaster />
        </Providers>
      </body>
    </html>
  );
}
