import { Search, Calendar, Key, RotateCcw } from "lucide-react";

const steps = [
  {
    icon: Search,
    step: "1",
    title: "Search & Browse",
    description: "Find the perfect tool from hundreds of verified listings in Edmonton.",
  },
  {
    icon: Calendar,
    step: "2",
    title: "Book Instantly",
    description: "Choose your dates, review pricing, and confirm your rental in seconds.",
  },
  {
    icon: Key,
    step: "3",
    title: "Pick Up & Use",
    description: "Meet your neighbour, grab your tool, and get to work on your project.",
  },
  {
    icon: RotateCcw,
    step: "4",
    title: "Return & Review",
    description: "Drop off the tool and leave a review to help the community grow.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="py-5 px-4 sm:px-6 lg:px-8 bg-card">
      <div className="mx-auto max-w-7xl">
        <div className="text-center space-y-4 mb-16">
          <h2 className="text-3xl sm:text-4xl lg:text-5xl">
            How it works
          </h2>
          <p className="text-lg sm:text-xl max-w-2xl mx-auto" style={{ color: 'var(--text-muted)' }}>
            Get the tools you need in four simple steps.
          </p>
        </div>
        
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-8">
          {steps.map((item, index) => {
            const Icon = item.icon;
            return (
              <div key={index} className="relative">
                {index < steps.length - 1 && (
                  <div className="hidden lg:block absolute top-16 left-[60%] w-full h-0.5 bg-border -z-10" />
                )}
                
                <div className="flex flex-col items-center text-center space-y-4">
                  <div className="relative">
                    <div 
                      className="w-24 h-24 rounded-2xl flex items-center justify-center"
                      style={{ backgroundColor: 'var(--info-bg)' }}
                    >
                      <Icon className="w-10 h-10" style={{ color: 'var(--primary)' }} />
                    </div>
                    <div 
                      className="absolute -top-2 -right-2 w-8 h-8 rounded-full flex items-center justify-center text-sm"
                      style={{ 
                        backgroundColor: 'var(--primary)',
                        color: 'var(--primary-foreground)'
                      }}
                    >
                      {item.step}
                    </div>
                  </div>
                  
                  <div className="space-y-2">
                    <h3>{item.title}</h3>
                    <p style={{ color: 'var(--text-muted)' }}>
                      {item.description}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
