import { Header } from "@/components/Header";
import { Hero } from "@/components/Hero";
import { FeaturedListings } from "@/components/FeaturedListings";
import { Categories } from "@/components/Categories";
import { Features } from "@/components/Features";
import { HowItWorks } from "@/components/HowItWorks";
import { CallToAction } from "@/components/CallToAction";
import { Footer } from "@/components/Footer";
import { Toaster } from "sonner";

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />
      <main>
        <Hero />
        <FeaturedListings />
        <Categories />
        <Features />
        <HowItWorks />
        <CallToAction />
      </main>
      <Footer />
      <Toaster richColors expand position="top-center" />
    </div>
  );
}
