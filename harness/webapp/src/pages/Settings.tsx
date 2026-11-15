import { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { api } from '../api/client';

export default function Settings() {
  const { user, logout, refreshUser } = useAuth();
  const [consent, setConsent] = useState<boolean>(!!user?.training_consent);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setConsent(!!user?.training_consent);
  }, [user?.training_consent]);

  async function saveConsent(value: boolean) {
    setSaving(true);
    setErr(null);
    setMsg(null);
    try {
      await api.setTrainingConsent(value);
      setConsent(value);
      setMsg(value ? 'Training telemetry enabled.' : 'Training telemetry disabled.');
      await refreshUser();
    } catch (e: any) {
      setErr(e?.message || 'Could not save consent');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="settings">
      <section className="card">
        <h2>Profile</h2>
        <dl className="kv">
          <dt>Name</dt>
          <dd>{user?.name}</dd>
          <dt>Email</dt>
          <dd>{user?.email}</dd>
          <dt>Role</dt>
          <dd>{user?.role}</dd>
          <dt>Verified</dt>
          <dd>{user?.email_verified ? 'yes' : 'no'}</dd>
          <dt>Course</dt>
          <dd>{user?.course_id || 'none'}</dd>
        </dl>
      </section>

      <section className="card">
        <h2>Telemetry</h2>
        <p className="muted">
          Training-consent telemetry (lesson views, practice answers) is opt-in and only collected when enabled. It is never
          used to infer attention from activity.
        </p>
        <label className="check">
          <input
            type="checkbox"
            checked={consent}
            disabled={saving}
            onChange={(e) => saveConsent(e.target.checked)}
          />
          Share training telemetry with Luminest
        </label>
        {msg && <p className="muted small">{msg}</p>}
        {err && <div className="error">{err}</div>}
      </section>

      <section className="card">
        <h2>Session</h2>
        <button className="ghost" onClick={logout}>
          Sign out
        </button>
      </section>
    </div>
  );
}
