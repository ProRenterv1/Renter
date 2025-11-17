import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { SectionHeading } from "@/components/SectionHeading";
import { FadeIn } from "@/components/FadeIn";
import { CategoryCard, type ListingCategory } from "@/components/CategoryCard";
import { jsonFetch } from "@/lib/api";

export default function AllCategoriesPage() {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<ListingCategory[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    jsonFetch<ListingCategory[]>("/listings/categories/")
      .then((data) => {
        if (!active) return;
        setCategories(Array.isArray(data) ? data : []);
      })
      .catch((err) => {
        if (!active) return;
        console.error("Failed to load categories", err);
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const handleCategoryClick = (slug?: string) => {
    if (!slug) {
      navigate("/feed");
      return;
    }
    navigate(`/feed?category=${encodeURIComponent(slug)}`);
  };

  return (
    <>
      <Header />
      <main>
        <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-0">
          <SectionHeading
            title="All categories"
            description="Browse every rental category to find the right fit for your project."
          />
          {categories.length === 0 ? (
            <div className="mt-10 text-muted-foreground">
              {loading ? "Loading categories..." : "Categories are coming soon."}
            </div>
          ) : (
            <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {categories.map((category, index) => (
                <FadeIn key={category.id} delay={0.05 * index}>
                  <CategoryCard
                    category={category}
                    highlight={index === 0}
                    onClick={handleCategoryClick}
                  />
                </FadeIn>
              ))}
            </div>
          )}
        </div>
      </main>
      <Footer />
    </>
  );
}
