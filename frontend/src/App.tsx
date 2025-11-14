import { useState } from "react";
import { Routes, Route } from "react-router-dom";
import { Header } from "@/components/Header";
import { Hero } from "@/components/Hero";
import { FeaturedListings } from "@/components/FeaturedListings";
import { Categories } from "@/components/Categories";
import { Features } from "@/components/Features";
import { HowItWorks } from "@/components/HowItWorks";
import { CallToAction } from "@/components/CallToAction";
import { Footer } from "@/components/Footer";
import { Toaster } from "sonner";
import UserProfile from "@/pages/UserProfile";
import Messages from "@/pages/Messages";
import Feed from "@/pages/Feed";

type Page = "landing" | "profile" | "messages";

export default function App() {
    const [currentPage, setCurrentPage] = useState<Page>("landing"); // Change to "landing" for the landing page

  const handleNavigateToMessages = () => {
    setCurrentPage("messages");
  };

  const handleNavigateToProfile = () => {
    setCurrentPage("profile");
  };

  const handleLogout = () => {
    setCurrentPage("landing");
  };

  if (currentPage === "profile") {
    return (
      <UserProfile 
        onNavigateToMessages={handleNavigateToMessages}
        onNavigateToProfile={handleNavigateToProfile}
        onLogout={handleLogout}
      />
    );
  }

  if (currentPage === "messages") {
    return (
      <Messages 
        onNavigateToMessages={handleNavigateToMessages}
        onNavigateToProfile={handleNavigateToProfile}
        onLogout={handleLogout}
      />
    );
  }
  const landingContent = (
    <>
      <Hero />
      {/* <FeaturedListings /> */}
      <Categories />
      <Features />
      <HowItWorks />
      <CallToAction />
    </>
  );

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header 
        onNavigateToMessages={handleNavigateToMessages}
        onNavigateToProfile={handleNavigateToProfile}
        onLogout={handleLogout}
      />
      <main>
        <Routes>
          <Route path="/" element={landingContent} />
          <Route path="/feed" element={<Feed />} />
        </Routes>
      </main>
      <Footer />
      <Toaster richColors expand position="top-center" />
    </div>
  );
}
