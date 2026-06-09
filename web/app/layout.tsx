import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Statiz Dry-run Results",
  description: "Public dashboard for finalized KBO win prediction results."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
