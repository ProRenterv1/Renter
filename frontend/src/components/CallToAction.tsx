import { ShieldCheck, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FadeIn } from "@/components/FadeIn";

export function CallToAction() {
  return (
    <section id="call-to-action" className="py-10 px-4 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <div 
          className="rounded-3xl p-6 sm:p-8 text-center space-y-8"
          style={{ backgroundColor: 'var(--primary)' }}
        >
          <h2 
            className="text-3xl sm:text-4xl lg:text-5xl"
            style={{ color: 'var(--primary-foreground)' }}
          >
            Ready to unlock your neighbourhood's tools?
          </h2>
          
          <p 
            className="text-lg sm:text-xl max-w-2xl mx-auto"
            style={{ color: 'var(--primary-foreground)', opacity: 0.9 }}
          >
            Join hundreds of Edmontonians renting and sharing tools safely. 
            Sign up in minutes and start browsing today.
          </p>
          
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Button 
              size="lg"
              className="h-14 px-8 bg-background hover:bg-background/90"
              style={{ color: 'var(--primary)' }}
            >
              Sign Up
            </Button>
            <Button 
              size="lg"
              variant="outline"
              className="h-14 px-8 border-2 bg-transparent hover:bg-white/10 dark:hover:bg-black/10"
              style={{ 
                color: 'var(--primary-foreground)',
                borderColor: 'var(--primary-foreground)'
              }}
            >
              List Your Tools
            </Button>
          </div>
          
          <div className="pt-8 flex flex-wrap justify-center gap-8 sm:gap-12">
            <div>
              <p 
                className="text-3xl sm:text-4xl"
                style={{ color: 'var(--primary-foreground)' }}
              >
                500+
              </p>
              <p 
                className="text-sm sm:text-base"
                style={{ color: 'var(--primary-foreground)', opacity: 0.8 }}
              >
                Active Users
              </p>
            </div>
            <div>
              <p 
                className="text-3xl sm:text-4xl"
                style={{ color: 'var(--primary-foreground)' }}
              >
                1,200+
              </p>
              <p 
                className="text-sm sm:text-base"
                style={{ color: 'var(--primary-foreground)', opacity: 0.8 }}
              >
                Tools Available
              </p>
            </div>
            <div>
              <p 
                className="text-3xl sm:text-4xl"
                style={{ color: 'var(--primary-foreground)' }}
              >
                4.8/5
              </p>
              <p 
                className="text-sm sm:text-base"
                style={{ color: 'var(--primary-foreground)', opacity: 0.8 }}
              >
                Average Rating
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
