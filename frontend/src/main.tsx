import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import AppRoutes from './routes';
import { Providers } from './providers';
import AuthGuard from './features/auth/AuthGuard';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <Providers>
    <BrowserRouter>
      <AuthGuard>
        <AppRoutes />
      </AuthGuard>
    </BrowserRouter>
  </Providers>,
);
