import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Quarter",
  description: "Turn Markdown and articles into quiet, printable reading copies.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
