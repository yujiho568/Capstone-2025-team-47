import React, { useState } from 'react'
import { useLocation, useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../auth/auth.js'
import '../styles/auth.css'

function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from?.pathname || '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch {
      setError('로그인 실패: 이메일 또는 비밀번호를 확인하세요')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-logo">U</div>
          <h1 className="auth-title">로그인</h1>
          <p className="auth-subtitle">UEBA 시스템에 오신 것을 환영합니다</p>
        </div>
        
        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label className="auth-label">이메일</label>
            <input 
              type="email" 
              value={email} 
              onChange={(e) => setEmail(e.target.value)} 
              required 
              className="auth-input"
              placeholder="이메일을 입력하세요"
            />
          </div>
          
          <div className="auth-field">
            <label className="auth-label">비밀번호</label>
            <input 
              type="password" 
              value={password} 
              onChange={(e) => setPassword(e.target.value)} 
              required 
              className="auth-input"
              placeholder="비밀번호를 입력하세요"
            />
          </div>
          
          {error && <div className="auth-error">{error}</div>}
          
          <button type="submit" disabled={loading} className="auth-button">
            {loading ? (
              <span className="auth-loading">
                <span className="auth-spinner"></span>
                로그인 중...
              </span>
            ) : (
              '로그인'
            )}
          </button>
        </form>
        
        <div className="auth-footer">
          <Link to="/register" className="auth-link">계정이 없으신가요? 회원가입</Link>
        </div>
      </div>
    </div>
  )
}

export default Login
