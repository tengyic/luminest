import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export default function Register() {
  const { register, loading } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [invite, setInvite] = useState('');
  const [age, setAge] = useState(true);
  const [terms, setTerms] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await register({
        name: name.trim(),
        email: email.trim(),
        password,
        age_confirmed: age,
        accept_terms: terms,
        invite_code: invite.trim() || undefined,
      });
      navigate('/');
    } catch (err: any) {
      setError(err?.message || 'Registration failed');
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <h1>Create your account</h1>
        <p className="muted">Luminest builds a course from what you paste in.</p>
        {error && <div className="error">{error}</div>}
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password <span className="muted small">(10+ characters)</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={10}
          />
        </label>
        <label>
          Share code <span className="muted small">(required for the closed beta)</span>
          <input value={invite} onChange={(e) => setInvite(e.target.value)}
                 placeholder="LUMINEST-XXXX-XXXX" required autoComplete="off" spellCheck={false} />
          <span className="muted small">Issued by the operator. Email is only an identifier — there is no
          verification email or magic link, and no payment details are collected.</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={age} onChange={(e) => setAge(e.target.checked)} />I confirm I am 13 or older.
        </label>
        <label className="check">
          <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} />I accept the Terms and
          Privacy Policy.
        </label>
        <button className="primary" disabled={loading} type="submit">
          {loading ? 'Creating…' : 'Create account'}
        </button>
        <p className="muted small">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
