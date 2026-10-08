import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom'
import { CurvesPage } from './pages/CurvesPage'
import { DataPage } from './pages/DataPage'
import './styles.css'

const qc = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <div className="layout">
          <nav className="sidebar">
            <h2>Nutun AC</h2>
            <Link to="/data">Data &amp; Refresh</Link>
            <Link to="/curves">Curve Workbench</Link>
          </nav>
          <main>
            <Routes>
              <Route path="/" element={<Navigate to="/data" replace />} />
              <Route path="/data" element={<DataPage />} />
              <Route path="/curves" element={<CurvesPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
