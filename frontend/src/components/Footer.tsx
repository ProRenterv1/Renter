import { Link } from "react-router-dom";

type FooterLink = {
  label: string;
  to?: string;
  href?: string;
};

type FooterColumn = {
  title: string;
  links: FooterLink[];
};

const supportEmail = "support@kitoro.com";

const columns: FooterColumn[] = [
  {
    title: "Company",
    links: [
      { label: "About", to: "/about" },
      { label: "Pricing", to: "/pricing" },
      { label: `Contact: ${supportEmail}`, href: `mailto:${supportEmail}` },
    ],
  },
  {
    title: "Renters",
    links: [
      { label: "Browse tools", to: "/feed" },
      { label: "Safety tips", to: "/safety" },
      { label: "Support", href: `mailto:${supportEmail}` },
    ],
  },
  {
    title: "Owners",
    links: [
      { label: "List a tool", to: "/profile?tab=add-listing" },
      { label: "Owner portal", to: "/profile?tab=listings" },
      { label: "Safety tips", to: "/safety" },
      { label: "Pricing", to: "/pricing" },
    ],
  },
];

export function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-border/60 bg-card">
      <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-2xl font-heading font-semibold">Kitoro.</p>
            <p className="mt-3 text-sm text-muted-foreground">
              Peer-to-peer rentals for Edmonton. Build projects faster with tools that live down the
              block.
            </p>
          </div>
          {columns.map((column) => (
            <div key={column.title}>
              <h4 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                {column.title}
              </h4>
              <ul className="mt-4 space-y-2 text-sm">
                {column.links.map((link) => {
                  if (link.to) {
                    return (
                      <li key={link.label}>
                        <Link
                          to={link.to}
                          className="text-muted-foreground transition hover:text-foreground"
                        >
                          {link.label}
                        </Link>
                      </li>
                    );
                  }
                  return (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        className="text-muted-foreground transition hover:text-foreground"
                      >
                        {link.label}
                      </a>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-10 text-xs text-muted-foreground">
          © {year} Kitoro. Operated by RentForge Inc. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
