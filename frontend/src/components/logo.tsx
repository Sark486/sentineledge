export function Logo({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Shield background */}
      <path
        d="M24 2L8 8V18C8 30 24 44 24 44C24 44 40 30 40 18V8L24 2Z"
        fill="url(#gradient1)"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Top accent line */}
      <line x1="14" y1="18" x2="34" y2="18" stroke="currentColor" strokeWidth="1.5" />

      {/* Sensor/data points - left side */}
      <circle cx="19" cy="26" r="1.5" fill="currentColor" />
      <circle cx="18" cy="32" r="1.5" fill="currentColor" />
      <circle cx="20" cy="38" r="1.5" fill="currentColor" />

      {/* Sensor/data points - right side */}
      <circle cx="29" cy="26" r="1.5" fill="currentColor" />
      <circle cx="30" cy="32" r="1.5" fill="currentColor" />
      <circle cx="28" cy="38" r="1.5" fill="currentColor" />

      {/* Connection lines - wave pattern for environment */}
      <path
        d="M19 26 Q24 28 29 26"
        stroke="currentColor"
        strokeWidth="1"
        fill="none"
        opacity="0.6"
      />
      <path
        d="M18 32 Q24 34 30 32"
        stroke="currentColor"
        strokeWidth="1"
        fill="none"
        opacity="0.6"
      />

      {/* Center accent element */}
      <circle cx="24" cy="28" r="3" fill="none" stroke="currentColor" strokeWidth="1" />

      <defs>
        <linearGradient id="gradient1" x1="8" y1="8" x2="40" y2="44">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.15" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.05" />
        </linearGradient>
      </defs>
    </svg>
  );
}
