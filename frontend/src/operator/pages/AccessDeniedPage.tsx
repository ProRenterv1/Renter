import { ShieldAlert } from 'lucide-react';
import { Button } from '../../components/ui/button';

export function AccessDeniedPage() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="max-w-md w-full text-center">
        <div className="mb-6 flex justify-center">
          <div className="w-20 h-20 rounded-full bg-destructive/10 flex items-center justify-center">
            <ShieldAlert className="w-10 h-10 text-destructive" />
          </div>
        </div>
        
        <h1 className="mb-3">Access Denied</h1>
        <p className="text-muted-foreground mb-8">
          You don't have permission to access the Kitoro Ops console. This area is restricted to authorized staff members only.
        </p>
        
        <div className="space-y-3">
          <Button 
            className="w-full"
            onClick={() => window.location.href = '/'}
          >
            Return to Main Site
          </Button>
          <Button 
            variant="outline" 
            className="w-full"
            onClick={() => window.location.reload()}
          >
            Try Again
          </Button>
        </div>
        
        <div className="mt-8 p-4 bg-muted rounded-lg">
          <p className="text-sm text-muted-foreground m-0">
            Need access? Contact your system administrator or email{' '}
            <a href="mailto:support@kitoro.com" className="text-[var(--alt-action)] hover:underline">
              support@kitoro.com
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
