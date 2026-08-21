import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

import App from './App';
import { AuthProvider } from './hooks/useAuth';
import { retryPolicy } from './hooks/queries';
import './index.css';

/**
 * Every read in this app comes from stored data the backend refreshes on
 * its own schedule, so aggressive refetching buys nothing: opening a
 * screen never triggers an external call (rule 23), and the numbers do
 * not move between two renders a second apart.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: retryPolicy,
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
