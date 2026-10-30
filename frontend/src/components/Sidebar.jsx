import React from 'react'
import { NavLink } from 'react-router-dom'
import '../styles/dashboard.css'

const navItems = [
  { path: '/', label: 'Dashboard', icon: '📊' },
  { path: '/results', label: 'Results', icon: '📈' },
  { path: '/connect', label: 'Connect', icon: '🔗' },
  { path: '/guide', label: 'Guide', icon: '📚' },
  { path: '/settings', label: 'Settings', icon: '⚙️' },
]

function Sidebar({ open }) {
  return (
    <aside className={`app-sidebar${open ? ' app-sidebar--open' : ''}`}>
      <nav className="app-nav">
        {navItems.map(item => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `app-nav__link${isActive ? ' app-nav__link--active' : ''}`
            }
            end={item.path === '/'}
          >
            <span style={{ fontSize: '18px' }}>{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

export default Sidebar
