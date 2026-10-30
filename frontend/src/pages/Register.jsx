import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import '../styles/auth.css'

function Register() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/v1/users/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          password
        })
      })
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(txt || 'Registration failed')
      }
      navigate('/login', { replace: true })
    } catch {
      setError('회원가입 실패: 이미 존재하는 이메일인지 확인하세요')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-logo">U</div>
          <h1 className="auth-title">회원가입</h1>
          <p className="auth-subtitle">UEBA 시스템을 시작해보세요</p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {/* 이메일 */}
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

          {/* 비밀번호 */}
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
                가입 중...
              </span>
            ) : (
              '가입하기'
            )}
          </button>
        </form>

        <div className="auth-footer">
          <Link to="/login" className="auth-link">
            이미 계정이 있으신가요? 로그인
          </Link>
        </div>
      </div>
    </div>
  )
}

export default Register
