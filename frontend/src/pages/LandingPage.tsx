import { Header } from "@/components/Header";
import { Hero } from "@/components/Hero";
import { Categories } from "@/components/Categories";
import { Features } from "@/components/Features";
import { HowItWorks } from "@/components/HowItWorks";
import { CallToAction } from "@/components/CallToAction";
import { Footer } from "@/components/Footer";

export default function LandingPage() {
  return (
    <>
      <Header />
      <main>
        <Hero />
        {/* <FeaturedListings /> */}
        <Categories />
        <Features />
        <HowItWorks />
        <CallToAction />
      </main>
      <Footer />
    </>
  );
}
