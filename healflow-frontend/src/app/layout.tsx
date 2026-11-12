import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HealFlow AI",
  description: "Omnichannel patient communication platform",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
