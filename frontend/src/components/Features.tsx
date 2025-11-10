import { Shield, Users, Clock, MapPin } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SectionHeading } from "@/components/SectionHeading";
import { FadeIn } from "@/components/FadeIn";

const features = [
  {
    icon: Shield,
    title: "Fully Insured",
    description: "Every rental is covered by comprehensive insurance. Rent with confidence knowing you're protected.",
    color: "var(--success-bg)",
    iconColor: "var(--success-text)",
  },
  {
    icon: Users,
    title: "Verified Community",
    description: "All users are verified through ID checks and reviews. Rent from trusted neighbours you can rely on.",
    color: "var(--info-bg)",
    iconColor: "var(--info-text)",
  },
  {
    icon: Clock,
    title: "Book in Minutes",
    description: "Find, book, and arrange pickup in just a few clicks. Skip the big-box stores and save time.",
    color: "var(--warning-bg)",
    iconColor: "var(--warning-text)",
  },
  {
    icon: MapPin,
    title: "Local to Edmonton",
    description: "Connect with tool owners in your neighbourhood. Quick pickup, easy returns, community support.",
    color: "var(--accent)",
    iconColor: "var(--accent-foreground)",
  },
];

export function Features() {
  return (
    <section id="about" className="py-20 px-4 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="text-center space-y-4 mb-16">
          <h2 className="text-2xl sm:text-3xl lg:text-4xl">
            Why rent with us?
          </h2>
          <p className="text-base sm:text-lg max-w-2xl mx-auto" style={{ color: 'var(--text-muted)' }}>
            Trusted peer-to-peer rentals designed for safety, simplicity, and community.
          </p>
        </div>
        
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((feature, index) => {
            const Icon = feature.icon;
            return (
              <Card key={index} className="p-6 hover:shadow-lg transition-shadow duration-300 relative">
                {feature.title === "Fully Insured" && (
                  <Badge 
                    className="absolute top-4 right-4 text-xs"
                    style={{ 
                      backgroundColor: 'var(--promoted-badge)',
                      color: 'var(--warning-text)',
                      border: 'none'
                    }}
                  >
                    Coming Soon
                  </Badge>
                )}
                <div 
                  className="w-14 h-14 rounded-xl flex items-center justify-center mb-4"
                  style={{ backgroundColor: feature.color }}
                >
                  <Icon className="w-7 h-7" style={{ color: feature.iconColor }} />
                </div>
                <h3 className="mb-2">{feature.title}</h3>
                <p style={{ color: 'var(--text-muted)' }}>
                  {feature.description}
                </p>
              </Card>
            );
          })}
        </div>
      </div>
    </section>
  );
}
