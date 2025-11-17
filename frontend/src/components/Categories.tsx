import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { SectionHeading } from "@/components/SectionHeading";
import { FadeIn } from "@/components/FadeIn";
import { jsonFetch } from "@/lib/api";
import { CategoryCard, type ListingCategory } from "@/components/CategoryCard";

const MAX_DISPLAYED_CATEGORIES = 6;

export function Categories() {
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

  const displayedCategories = useMemo(
    () => categories.slice(0, MAX_DISPLAYED_CATEGORIES),
    [categories],
  );

  const handleCategoryClick = (slug: string | undefined) => {
    if (!slug) {
      navigate("/feed");
      return;
    }
    navigate(`/feed?category=${encodeURIComponent(slug)}`);
  };

  return (
    <section className="py-5" id="categories" aria-labelledby="categories-heading">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-0">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <SectionHeading
            title="Browse by category"
            description="Find exactly what you need for your next project."
          />
          <button
            type="button"
            className="text-sm font-semibold text-link transition-colors hover:text-link-hover"
            onClick={() => navigate("/categories")}
          >
            View all categories &rarr;
          </button>
        </div>
        {displayedCategories.length === 0 ? (
          <div className="mt-10 text-muted-foreground">
            {loading ? "Loading categories..." : "Categories are coming soon."}
          </div>
        ) : (
          <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {displayedCategories.map((category, index) => (
              <FadeIn key={category.id} delay={0.05 * index}>
                <CategoryCard
                  category={category}
                  highlight={index === 0}
                  onClick={() => handleCategoryClick(category.slug)}
                />
              </FadeIn>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
