import React, { useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Results from './pages/Results'
import Connect from './pages/Connect'
import Login from './pages/Login'
import Register from './pages/Register'
import Guide from './pages/Guide'
import Settings from './pages/Settings'
import { AuthProvider, ProtectedRoute } from './auth/AuthContext'
import './App.css'

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const handleToggleSidebar = () => setSidebarOpen(prev => !prev)
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/*"
            element={(
              <ProtectedRoute>
                <div className="app-container">
                  <Header onToggleSidebar={handleToggleSidebar} />
                  <div className="app-body">
                    <Sidebar open={sidebarOpen} />
                    <main className="app-content">
                      <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/results" element={<Results />} />
                        <Route path="/connect" element={<Connect />} />
                        <Route path="/guide" element={<Guide />} />
                        <Route path="/settings" element={<Settings />} />
                      </Routes>
                    </main>
                  </div>
                </div>
              </ProtectedRoute>
            )}
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
