import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/auth.js'

function UserProfile() {
  const [isOpen, setIsOpen] = useState(false)
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleToggle = () => setIsOpen(prev => !prev)
  const goToSettings = () => {
    navigate('/settings')
    setIsOpen(false) // 드롭다운 닫기 (선택 사항)
  }

  return (
    <div className="user-profile">
      <button
        className="user-profile__button"
        onClick={handleToggle}
        aria-label="User profile"
        type="button"
      >
        <div className="user-profile__avatar">
          <span className="user-profile__initials">{user?.email?.[0]?.toUpperCase() || 'U'}</span>
        </div>
        <span className="user-profile__name">{user?.email || 'User'}</span>
        <svg className="user-profile__arrow" width="12" height="12" viewBox="0 0 12 12">
          <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.5" fill="none" />
        </svg>
      </button>

      {isOpen && (
        <div className="user-profile__dropdown">
          <div className="user-profile__header">
            <div className="user-profile__avatar">
              <span className="user-profile__initials">{user?.email?.[0]?.toUpperCase() || 'U'}</span>
            </div>
            <div className="user-profile__info">
              <div className="user-profile__fullname">{user?.email || 'User Name'}</div>
              <div className="user-profile__email">{user?.email || 'user@example.com'}</div>
            </div>
          </div>
          <div className="user-profile__menu">
            <button
              className="user-profile__menu-item"
              onClick={goToSettings}
            >
              AWS Credentials
            </button>
            <hr className="user-profile__divider" />
            <button className="user-profile__menu-item user-profile__menu-item--logout" onClick={logout}>Sign Out</button>
          </div>
        </div>
      )}
    </div>
  )
}

export default UserProfile

