/**
 * Sign in, or create the account the rest of the app needs.
 *
 * One form for both, because the backend takes the same two fields
 * either way and a second screen would be a second place for the
 * password rules to drift out of date.
 */

import { useState, type FormEvent } from 'react';
import { TrendingUp } from 'lucide-react';

import { ErrorNote } from '@/components/ui';
import { useAuth } from '@/hooks/useAuth';

const MIN_PASSWORD = 8;

export function LoginPage() {
  const { signIn, register } = useAuth();
  const [mode, setMode] = useState<'signin' | 'register'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === 'signin') await signIn(email, password);
      else await register(email, password);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  const tooShort = mode === 'register' && password.length > 0 && password.length < MIN_PASSWORD;

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2 text-sky-400">
          <TrendingUp className="h-6 w-6" />
          <span className="text-lg font-semibold text-slate-100">
            Investment Assistant
          </span>
        </div>

        <form
          onSubmit={submit}
          className="rounded-xl border border-slate-800 bg-slate-900/60 p-6"
        >
          <h1 className="text-sm font-semibold text-slate-200">
            {mode === 'signin' ? 'Entrar' : 'Criar conta'}
          </h1>

          <label className="mt-5 block text-xs text-slate-400">
            E-mail
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="mt-4 block text-xs text-slate-400">
            Senha
            <input
              type="password"
              required
              minLength={mode === 'register' ? MIN_PASSWORD : undefined}
              autoComplete={
                mode === 'signin' ? 'current-password' : 'new-password'
              }
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-500"
            />
          </label>
          {tooShort && (
            <p className="mt-1 text-xs text-amber-500">
              Mínimo de {MIN_PASSWORD} caracteres.
            </p>
          )}

          {error !== null && (
            <div className="mt-4">
              <ErrorNote error={error} />
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="mt-5 w-full rounded-md bg-sky-500 px-3 py-2 text-sm font-medium text-slate-950 hover:bg-sky-400 disabled:opacity-50"
          >
            {busy ? 'Aguarde…' : mode === 'signin' ? 'Entrar' : 'Criar conta'}
          </button>

          <button
            type="button"
            onClick={() => {
              setMode(mode === 'signin' ? 'register' : 'signin');
              setError(null);
            }}
            className="mt-3 w-full text-center text-xs text-slate-500 hover:text-slate-300"
          >
            {mode === 'signin'
              ? 'Não tenho conta'
              : 'Já tenho conta'}
          </button>
        </form>
      </div>
    </div>
  );
}
