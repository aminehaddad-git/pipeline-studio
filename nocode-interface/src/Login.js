import React, { useState } from 'react';
import { LogIn, AlertCircle, Loader2 } from 'lucide-react';
import appLogo from './logo-light.png';
import './Login.css';

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!username || !password) {
      setError('Please enter your username and password');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await fetch('http://localhost:8000/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(typeof data.detail === 'string' ? data.detail : 'Login failed');
        setLoading(false);
        return;
      }
      const data = await res.json();
      onLogin(data.access_token, data.user);
    } catch {
      setError('Could not connect to the server');
    }
    setLoading(false);
  };

  const onKey = (e) => { if (e.key === 'Enter') handleSubmit(); };

  return (
    <div className="login-container">
      <div className="login-bg-glow login-glow-1" />
      <div className="login-bg-glow login-glow-2" />

      <div className="login-card">
        <div className="login-logo">
                    <img src={appLogo} alt="PIPELINE STUDIO" className="logo-img" />
          <h1>PIPELINE STUDIO</h1>
          <p>No-Code Data Pipeline Platform</p>
        </div>

        <div className="login-form">
          <div className="login-field">
            <label>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyPress={onKey}
              placeholder="Enter your username"
              autoFocus
            />
          </div>

          <div className="login-field">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyPress={onKey}
              placeholder="Enter your password"
            />
          </div>

          {error && (
            <div className="login-error">
              <AlertCircle size={15} />
              <span>{error}</span>
            </div>
          )}

          <button className="login-btn" onClick={handleSubmit} disabled={loading}>
            {loading
              ? <><Loader2 size={16} className="spin" /><span>Signing in…</span></>
              : <><LogIn size={16} /><span>Sign In</span></>}
          </button>
        </div>

        <div className="login-footer">
          <p>No-Code ETL Studio · Secure Access</p>
        </div>
      </div>
    </div>
  );
}