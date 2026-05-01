import { useEffect, useState } from 'react'
import './App.css'

const apiGet = async (path) => {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json()
}

function App() {
  const [health, setHealth] = useState(null)
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const [healthData, dashboardData] = await Promise.all([
          apiGet('/api/health'),
          apiGet('/api/dashboard'),
        ])
        if (!cancelled) {
          setHealth(healthData)
          setDashboard(dashboardData)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err))
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="app-shell">
      <section className="hero-card">
        <p className="eyebrow">Cloudflare migration</p>
        <h1>IIT JEE Question Bank</h1>
        <p className="subtitle">
          React/Vite frontend on Cloudflare Pages, Worker API, D1 database, and R2 file storage.
        </p>
      </section>

      {loading && <div className="panel">Loading Cloudflare API status...</div>}
      {error && <div className="panel error">{error}</div>}

      <section className="grid">
        <article className="panel">
          <h2>API health</h2>
          <dl>
            <dt>Status</dt>
            <dd>{health?.ok ? 'OK' : 'Not loaded'}</dd>
            <dt>D1</dt>
            <dd>{health?.services?.d1 || '-'}</dd>
            <dt>R2</dt>
            <dd>{health?.services?.r2 || '-'}</dd>
          </dl>
        </article>

        <article className="panel">
          <h2>Question bank</h2>
          <dl>
            <dt>Total questions</dt>
            <dd>{dashboard?.stats?.totalQuestions ?? 0}</dd>
            <dt>Chapters</dt>
            <dd>{dashboard?.stats?.totalChapters ?? 0}</dd>
            <dt>Magazines</dt>
            <dd>{dashboard?.stats?.uniqueMagazines ?? 0}</dd>
          </dl>
        </article>
      </section>
    </main>
  )
}

export default App
