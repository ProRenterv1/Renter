import { ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';

interface OperatorLayoutProps {
  children: ReactNode;
  darkMode: boolean;
  onToggleTheme: () => void;
  operatorName: string;
  operatorRole: string;
  operatorEmail: string;
  onLogout: () => void;
  operatorAvatarUrl?: string | null;
}

export function OperatorLayout({
  children,
  darkMode,
  onToggleTheme,
  operatorName,
  operatorRole,
  operatorEmail,
  onLogout,
  operatorAvatarUrl,
}: OperatorLayoutProps) {
  const location = useLocation();
  const navigate = useNavigate();

  // Extract current view from path
  const pathParts = location.pathname.split('/').filter(Boolean);
  const currentView = pathParts[1] || 'dashboard'; // operator/[view]

  const handleNavigate = (view: string) => {
    navigate(`/operator/${view}`);
  };

  return (
    <div className="flex h-screen bg-background">
      <Sidebar
        currentView={currentView}
        onNavigate={handleNavigate}
        operatorName={operatorName}
        operatorEmail={operatorEmail}
        operatorAvatarUrl={operatorAvatarUrl}
      />
      <div className="flex flex-col flex-1 overflow-hidden">
        <TopBar 
          currentView={currentView} 
          darkMode={darkMode} 
          onToggleTheme={onToggleTheme}
          operatorName={operatorName}
          operatorRole={operatorRole}
          operatorEmail={operatorEmail}
          onLogout={onLogout}
        />
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
