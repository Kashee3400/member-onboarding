import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Noto_Sans_Devanagari } from "next/font/google";
import type { ReactNode } from "react";

import { Providers } from "@/components/providers";
import { brandingCss, getBranding } from "@/lib/branding";

import "./globals.css";

const sans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-mono-face", subsets: ["latin"] });
const devanagari = Noto_Sans_Devanagari({ variable: "--font-devanagari", subsets: ["devanagari"] });

export const metadata: Metadata = {
  title: { default: "Member Onboarding", template: "%s · Member Onboarding" },
  description: "Staff portal for member onboarding",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#14181f" },
  ],
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const branding = await getBranding(process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION);
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${sans.variable} ${mono.variable} ${devanagari.variable} h-full antialiased`}
    >
      <head>
        <style>{brandingCss(branding)}</style>
      </head>
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
