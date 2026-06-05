export default function ExtensionPage() {
  return (
    <>
      <h1>Install the Extension</h1>
      <p className="subtitle">Add Personify to Chrome to start autofilling job applications.</p>

      <div className="card">
        <h2>Download</h2>
        <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 16 }}>
          Download the Personify Chrome extension and load it manually in Developer mode.
        </p>
        <a href="/personify-extension.zip" download className="btn">
          ↓ Download Extension
        </a>
      </div>

      <div className="card">
        <h2>Installation steps</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: 14 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <span style={{ background: "var(--accent)", color: "white", borderRadius: "50%", width: 22, height: 22, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0 }}>1</span>
            <span>Unzip the downloaded file</span>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <span style={{ background: "var(--accent)", color: "white", borderRadius: "50%", width: 22, height: 22, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0 }}>2</span>
            <span>Open Chrome and go to <code style={{ background: "var(--bg)", padding: "1px 6px", borderRadius: 4 }}>chrome://extensions</code></span>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <span style={{ background: "var(--accent)", color: "white", borderRadius: "50%", width: 22, height: 22, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0 }}>3</span>
            <span>Toggle <strong>Developer mode</strong> on (top right)</span>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <span style={{ background: "var(--accent)", color: "white", borderRadius: "50%", width: 22, height: 22, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0 }}>4</span>
            <span>Click <strong>Load unpacked</strong> and select the unzipped folder</span>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <span style={{ background: "var(--accent)", color: "white", borderRadius: "50%", width: 22, height: 22, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0 }}>5</span>
            <span>Pin Personify to your toolbar and you&apos;re ready to go!</span>
          </div>
        </div>
      </div>
    </>
  );
}