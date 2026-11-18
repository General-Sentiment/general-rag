import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const areal = localFont({
  src: "../public/fonts/ABCArealVariable.woff2",
  display: "swap",
  variable: "--font-areal",
});

export const metadata: Metadata = {
  title: "Quarter",
  description: "Turn Markdown and articles into quiet, printable reading copies.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={areal.variable}>
      <body>{children}</body>
    </html>
  );
}
