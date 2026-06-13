import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Y-wins KBO Forecast",
  description: "Public dashboard for finalized Y-wins KBO prediction results."
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
