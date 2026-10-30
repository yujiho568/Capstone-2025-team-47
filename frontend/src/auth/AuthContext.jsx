import React, { useEffect, useMemo, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { AuthContext, useAuth } from './auth.js'

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('access_token') || '')
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(!!token)

  useEffect(() => {
    let ignore = false
    async function fetchMe() {
      if (!token) return
      setLoading(true)
      try {
        const res = await fetch('/api/v1/users/me', {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) throw new Error('unauthorized')
        const data = await res.json()
        if (!ignore) setUser(data)
      } catch {
        if (!ignore) {
          setUser(null)
          setToken('')
          localStorage.removeItem('access_token')
        }
      } finally {
        if (!ignore) setLoading(false)
      }
    }
    fetchMe()
    return () => { ignore = true }
  }, [token])

  const login = async (email, password) => {
    const body = new URLSearchParams()
    body.append('username', email)
    body.append('password', password)
    const res = await fetch('/api/v1/users/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    })
    if (!res.ok) {
      const msg = await res.text()
      throw new Error(msg || 'Login failed')
    }
    const data = await res.json()
    const accessToken = data?.access_token
    if (!accessToken) throw new Error('No access token')
    localStorage.setItem('access_token', accessToken)
    setToken(accessToken)
    return accessToken
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    setUser(null)
    setToken('')
  }

  const value = useMemo(() => ({ token, user, loading, login, logout }), [token, user, loading])

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function ProtectedRoute({ children }) {
  const { token, loading } = useAuth()
  const location = useLocation()
  if (loading) return null
  if (!token) return <Navigate to="/login" state={{ from: location }} replace />
  return children
}
