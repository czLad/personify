import type { Metadata } from "next";
import "./globals.css";
import NavLinks from "@/components/NavLinks";

export const metadata: Metadata = {
  title: "Personify",
  description: "Agentic AI for job application personal statements.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="topnav">
          <a href="/" className="brand">
            <img src="/logo.png" alt="Personify" style={{ width: 24, height: 24, marginRight: 8, verticalAlign: "middle" }} />
            Personify
          </a>
          <NavLinks />
        </nav>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}