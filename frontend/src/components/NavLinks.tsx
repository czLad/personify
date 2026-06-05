"use client";

import { usePathname, useRouter } from "next/navigation";

export default function NavLinks() {
  const pathname = usePathname();
  const router = useRouter();

  function handleUploadClick(e: React.MouseEvent) {
    e.preventDefault();
    if (pathname === "/") {
      document.getElementById("upload")?.scrollIntoView({ behavior: "smooth" });
    } else {
      router.push("/#upload");
    }
  }

  return (
    <div className="links">
      <a href="#upload" onClick={handleUploadClick}>⇧ Upload</a>
      <a href="/install">↓ Install</a>
      <a href="/settings">𖠋 Account</a>
    </div>
  );
}
