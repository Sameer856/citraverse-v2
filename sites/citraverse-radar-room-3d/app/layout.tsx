import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Citraverse · Radar Room",
  description: "Live 3D radar room and experimental fall monitoring.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
