import React, { useState, useEffect } from 'react';
import './UserManagement.css';
import { Users, X, Plus, UserPlus, AlertCircle, CheckCircle2 } from 'lucide-react';

export default function UserManagement({ token, onClose }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [newUser, setNewUser] = useState({ username: '', full_name: '', password: '', role: 'viewer' });
  const [message, setMessage] = useState(null);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/users', {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (data.users) setUsers(data.users);
    } catch (e) {
      setMessage({ error: 'Could not load users' });
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreate = async () => {
    if (!newUser.username || !newUser.password || !newUser.full_name) {
      setMessage({ error: 'Please fill all fields' });
      return;
    }
    try {
      const res = await fetch('http://localhost:8000/users', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(newUser),
      });
      const data = await res.json();
      if (res.ok) {
        setMessage({ success: data.message });
        setNewUser({ username: '', full_name: '', password: '', role: 'viewer' });
        setShowForm(false);
        fetchUsers();
      } else {
        setMessage({ error: data.detail || 'Failed to create user' });
      }
    } catch (e) {
      setMessage({ error: 'Could not create user' });
    }
  };

  return (
    <div className="users-overlay" onClick={onClose}>
      <div className="users-modal" onClick={(e) => e.stopPropagation()}>

        <div className="users-header">
          <div>
            <h2><Users size={18} /> User Management</h2>
            <p>Manage platform access and roles</p>
          </div>
          <button className="users-close" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="users-body">
          {message && (
            <div className={`users-message ${message.error ? 'error' : 'success'}`}>
              {message.error
                ? <><AlertCircle size={15} /> {message.error}</>
                : <><CheckCircle2 size={15} /> {message.success}</>}
            </div>
          )}

          <div className="users-toolbar">
            <span className="users-count">{users.length} users</span>
            <button className="users-add-btn" onClick={() => setShowForm(!showForm)}>
              {showForm ? <><X size={14} /> Cancel</> : <><Plus size={14} /> New User</>}
            </button>
          </div>

          {showForm && (
            <div className="users-form">
              <div className="users-form-row">
                <input
                  placeholder="Username"
                  value={newUser.username}
                  onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                />
                <input
                  placeholder="Full Name"
                  value={newUser.full_name}
                  onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })}
                />
              </div>
              <div className="users-form-row">
                <input
                  type="password"
                  placeholder="Password"
                  value={newUser.password}
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                />
                <select
                  value={newUser.role}
                  onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                >
                  <option value="viewer">Viewer</option>
                  <option value="operator">Operator</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <button className="users-create-btn" onClick={handleCreate}>
                <UserPlus size={15} /> Create User
              </button>
            </div>
          )}

          {loading ? (
            <div className="users-loading">Loading users...</div>
          ) : (
            <div className="users-table-wrap">
              <table className="users-table">
                <thead>
                  <tr>
                    <th>Username</th>
                    <th>Full Name</th>
                    <th>Role</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>{u.username}</td>
                      <td>{u.full_name}</td>
                      <td>
                        <span className={`users-role-badge role-${u.role}`}>{u.role}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}