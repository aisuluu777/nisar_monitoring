const base = {
  width: 22,
  height: 22,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export const IconMap = () => (
  <svg {...base}>
    <path d="M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z" />
    <path d="M9 4v14M15 6v14" />
  </svg>
);
export const IconSummary = () => (
  <svg {...base}>
    <circle cx="12" cy="12" r="8" />
    <path d="M12 4v8l6 4" />
  </svg>
);
export const IconInfo = () => (
  <svg {...base}>
    <rect x="4" y="4" width="16" height="16" rx="3" />
    <path d="M12 11v5M12 8h.01" />
  </svg>
);
export const IconSystem = () => (
  <svg {...base}>
    <path d="M4 7h16M4 12h16M4 17h16" />
    <circle cx="8" cy="7" r="1.2" />
    <circle cx="14" cy="12" r="1.2" />
    <circle cx="10" cy="17" r="1.2" />
  </svg>
);
export const IconLogout = () => (
  <svg {...base}>
    <path d="M14 4h4a2 2 0 012 2v12a2 2 0 01-2 2h-4" />
    <path d="M10 16l-4-4 4-4M6 12h10" />
  </svg>
);
export const IconLogin = () => (
  <svg {...base}>
    <path d="M10 4H6a2 2 0 00-2 2v12a2 2 0 002 2h4" />
    <path d="M14 8l4 4-4 4M18 12H8" />
  </svg>
);
export const Logo = () => (
  <svg viewBox="0 0 40 40" className="logo" aria-hidden="true">
    <rect x="1" y="1" width="38" height="38" rx="8" fill="#011425" stroke="var(--neon-dim)" />
    <path d="M6 30 L15 15 L21 22 L26 16 L34 30 Z" fill="rgba(25,227,255,.12)" stroke="var(--neon)" strokeWidth="1.6" strokeLinejoin="round" />
    <circle cx="26" cy="11" r="2" fill="var(--neon)" />
  </svg>
);
