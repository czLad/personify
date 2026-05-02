export default function SettingsPage() {
  return (
    <>
      <h1>Settings</h1>
      <p className="subtitle">Configure how Personify generates responses.</p>

      <div className="card">
        <h2>Tone</h2>
        <p style={{ color: "var(--muted)", fontSize: 14 }}>
          Coming soon: choose Formal, Balanced, or Conversational.
        </p>
      </div>

      <div className="card">
        <h2>Length</h2>
        <p style={{ color: "var(--muted)", fontSize: 14 }}>
          Coming soon: target ~50, 100, or 150 words per response.
        </p>
      </div>
    </>
  );
}
