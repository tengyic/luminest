import type { ReactNode } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate('/login');
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">Luminest</div>
        <nav className="nav">
          <NavLink to="/" end>
            Today
          </NavLink>
          <NavLink to="/quiz">Practice</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <div className="who">
          {user ? (
            <>
              <span className="who-name">{user.name}</span>
              <button className="ghost" onClick={handleLogout}>
                Sign out
              </button>
            </>
          ) : null}
        </div>
      </header>
      <main className="content">{children}</main>
    </div>
  );
}
