import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = "https://y-wins-kbo-forecast.vercel.app";
const SITE_TITLE = "Y-wins KBO Forecast";
const SITE_DESCRIPTION = "KBO submitted forecast dashboard with game cards, finalized ledger, and model metrics.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  openGraph: {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    url: SITE_URL,
    siteName: SITE_TITLE,
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        alt: "Y-wins KBO Forecast dashboard preview",
      },
    ],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: ["/opengraph-image"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
