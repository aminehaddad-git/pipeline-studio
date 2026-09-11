import React, { useState, useEffect } from 'react';
import Login from './Login';
import PipelineBuilder from './PipelineBuilder';
import './ModalTheme.css';

function App() {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Restore session on page load
  useEffect(() => {
    const savedToken = window.sessionStorage.getItem('biat_token');
    const savedUser = window.sessionStorage.getItem('biat_user');
    if (savedToken && savedUser) {
      setToken(savedToken);
      setUser(JSON.parse(savedUser));
    }
    setLoading(false);
  }, []);

  const handleLogin = (newToken, newUser) => {
    setToken(newToken);
    setUser(newUser);
    window.sessionStorage.setItem('biat_token', newToken);
    window.sessionStorage.setItem('biat_user', JSON.stringify(newUser));
  };

  const handleLogout = () => {
    setToken(null);
    setUser(null);
    window.sessionStorage.removeItem('biat_token');
    window.sessionStorage.removeItem('biat_user');
  };

  if (loading) return null;

  if (!token) {
    return <Login onLogin={handleLogin} />;
  }

  return <PipelineBuilder token={token} user={user} onLogout={handleLogout} />;
}

export default App;