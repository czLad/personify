import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import Image from "next/image";
import NavLinks from "@/components/NavLinks";

export const metadata: Metadata = {
  title: "Personify",
  description: "Agentic AI for job application personal statements.",
  icons: {
    icon: "/logo.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="topnav">
          <Link href="/" className="brand">
            <Image src="/logo.png" alt="Personify" width={24} height={24} style={{ verticalAlign: "middle", marginRight: 8 }} />
            Personify
          </Link>
          <NavLinks />
        </nav>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
