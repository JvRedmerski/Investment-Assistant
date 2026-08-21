/**
 * The route table, and the gate in front of it.
 *
 * Everything except the login screen is behind `RequireAuth`, so a
 * screen never has to wonder whether there is a user. The check waits
 * for `/auth/me` rather than trusting the stored token, and shows
 * nothing while it waits: flashing the login screen at somebody who is
 * signed in is worse than a moment of blank.
 */

import { Navigate, Route, Routes } from 'react-router-dom';

import { Spinner } from '@/components/ui';
import { useAuth } from '@/hooks/useAuth';
import { AppLayout } from '@/layouts/AppLayout';
import { AssetPage } from '@/pages/AssetPage';
import { AssetsPage } from '@/pages/AssetsPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { LoginPage } from '@/pages/LoginPage';
import { PortfolioPage } from '@/pages/PortfolioPage';

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <Spinner label="Verificando sessão…" />
      </div>
    );
  }
  if (user === null) return <Navigate to="/entrar" replace />;
  return <>{children}</>;
}

function RedirectSignedIn({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user !== null) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      <Route
        path="/entrar"
        element={
          <RedirectSignedIn>
            <LoginPage />
          </RedirectSignedIn>
        }
      />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="carteira" element={<PortfolioPage />} />
        <Route path="ativos" element={<AssetsPage />} />
        <Route path="ativos/:ticker" element={<AssetPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
