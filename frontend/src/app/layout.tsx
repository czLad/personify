import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Personify",
  description: "Agentic AI for job application personal statements.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="topnav">
          <a href="/" className="brand">Personify</a>
          <div className="links">
            <a href="/upload">Upload</a>
            <a href="/history">History</a>
            <a href="/settings">Settings</a>
          </div>
        </nav>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
