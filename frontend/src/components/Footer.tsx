const columns = [
  {
    title: "Company",
    links: ["About", "Careers", "Press", "Contact"],
  },
  {
    title: "Renters",
    links: ["Browse tools", "Insurance", "Community", "Support"],
  },
  {
    title: "Owners",
    links: ["List a tool", "Safety tips", "Pricing", "Owner portal"],
  },
];

export function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-border/60 bg-card">
      <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-2xl font-heading font-semibold">Renter.</p>
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
                {column.links.map((link) => (
                  <li key={link}>
                    <a href="#" className="text-muted-foreground transition hover:text-foreground">
                      {link}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-10 text-xs text-muted-foreground">
          © {year} Renter. Operated by RentForge Inc. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
