import { Figtree, Syne } from "next/font/google";
import "./globals.css";

const sans = Figtree({
  subsets: ["latin"],
  variable: "--font-asante-sans",
  display: "swap"
});

const display = Syne({
  subsets: ["latin"],
  variable: "--font-asante-display",
  display: "swap"
});

export const metadata = {
  title: "Asante Review Dashboard",
  description: "Human review and publishing controls for Asante stories."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${display.variable}`}>
      <body>{children}</body>
    </html>
  );
}
