import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Personify",
  description: "Agentic AI for job application personal statements.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="topnav">
          <Link href="/" className="brand">Personify</Link>
          <div className="links">
            <Link href="/upload">Upload</Link>
            <Link href="/history">History</Link>
            <Link href="/settings">Settings</Link>
          </div>
        </nav>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
