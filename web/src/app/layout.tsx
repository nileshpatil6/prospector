import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { Providers } from "@/components/Providers";

const geist = Geist({
  variable: "--font-geist",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
  style: ["italic", "normal"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Prospector",
  description: "Radar for your next customers: plan, act, observe, learn.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`motion-ok ${geist.variable} ${geistMono.variable} ${instrumentSerif.variable} h-full`}
    >
      <body className="min-h-full flex flex-col bg-bg text-text font-sans antialiased">
        <Providers>
          <Nav />
          <main className="flex-1 w-full">{children}</main>
          <footer className="border-t border-hairline">
            <div className="max-w-[1440px] mx-auto px-4 sm:px-6 py-4 text-xs text-muted font-mono">
              prospector -- plan / act / observe / learn
            </div>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
