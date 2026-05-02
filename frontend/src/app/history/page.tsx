"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type HistoryItem = {
  company_name: string;
  question: string;
  generated_response: string;
  created_at: string;
};

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.history()
      .then((data) => setItems(data.items ?? []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <h1>Autofill History</h1>
      <p className="subtitle">Every personal statement Personify has filled on your behalf.</p>

      {loading && <div className="card empty">Loading…</div>}
      {!loading && items.length === 0 && (
        <div className="card empty">
          No autofill history yet. Install the extension and try it on a job application.
        </div>
      )}
      {items.map((item, i) => (
        <div className="card" key={i}>
          <h2>{item.company_name}</h2>
          <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 8 }}>{item.question}</p>
          <p>{item.generated_response}</p>
        </div>
      ))}
    </>
  );
}
