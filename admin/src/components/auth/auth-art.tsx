const NIGHT = "#070d2b";

const mix = (color: string, amount: number, other: string) => `color-mix(in srgb, ${color} ${amount}%, ${other})`;

const BRAND = "var(--brand)";
const ACCENT = "var(--brand-accent)";
/** Keeps blue from passing through green on its way to gold. */
const DAWN = "#d9805f";

/** The wave that divides the scene from the quiet side. Each ribbon is the same curve, moved left. */
const wave = (shift: number) =>
  `M${930 + shift} 0C${1090 + shift} 170 ${690 + shift} 320 ${800 + shift} 520S${1040 + shift} 760 ${890 + shift} 900H1600V0Z`;

/** Sunrise over a village: the sign-in scene until the organization uploads its own image. */
export function AuthArt() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 1600 900"
      preserveAspectRatio="xMinYMax slice"
      className="absolute inset-0 size-full"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="auth-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" style={{ stopColor: mix(BRAND, 18, NIGHT) }} />
          <stop offset="0.3" style={{ stopColor: mix(BRAND, 45, NIGHT) }} />
          <stop offset="0.47" style={{ stopColor: mix(BRAND, 50, DAWN) }} />
          <stop offset="0.6" style={{ stopColor: DAWN }} />
          <stop offset="0.68" style={{ stopColor: mix(ACCENT, 75, "white") }} />
        </linearGradient>
        <radialGradient id="auth-glow" cx="440" cy="500" r="430" gradientUnits="userSpaceOnUse">
          <stop offset="0" style={{ stopColor: mix(ACCENT, 60, "white"), stopOpacity: 0.85 }} />
          <stop offset="0.45" style={{ stopColor: DAWN, stopOpacity: 0.4 }} />
          <stop offset="1" style={{ stopColor: DAWN, stopOpacity: 0 }} />
        </radialGradient>
        <linearGradient id="auth-gold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: mix(ACCENT, 80, "white") }} />
          <stop offset="1" style={{ stopColor: ACCENT }} />
        </linearGradient>
        <linearGradient id="auth-field" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" style={{ stopColor: mix(BRAND, 30, "#1c5a3a") }} />
          <stop offset="1" style={{ stopColor: mix(BRAND, 28, NIGHT) }} />
        </linearGradient>
        <linearGradient id="auth-ground" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" style={{ stopColor: mix(BRAND, 26, NIGHT) }} />
          <stop offset="1" style={{ stopColor: mix(BRAND, 10, NIGHT) }} />
        </linearGradient>
        <radialGradient id="auth-tint" cx="1600" cy="0" r="900" gradientUnits="userSpaceOnUse">
          <stop offset="0" style={{ stopColor: BRAND, stopOpacity: 0.1 }} />
          <stop offset="1" style={{ stopColor: BRAND, stopOpacity: 0 }} />
        </radialGradient>
      </defs>

      <rect width="1600" height="900" fill="url(#auth-sky)" />

      <g fill="white">
        {[
          [90, 90, 1.6],
          [230, 170, 1.2],
          [360, 70, 1.8],
          [520, 140, 1.2],
          [640, 60, 1.5],
          [760, 190, 1.1],
          [150, 250, 1.1],
          [470, 280, 1],
          [690, 300, 1.2],
        ].map(([cx, cy, r]) => (
          <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={r} opacity="0.7" />
        ))}
      </g>

      <g transform="translate(0 -110)">
<rect width="1000" height="900" fill="url(#auth-glow)" style={{ mixBlendMode: "screen" }} />
      <circle cx="440" cy="610" r="92" style={{ fill: mix(ACCENT, 55, "white") }} />
      <g
        stroke="white"
        strokeOpacity="0.28"
        strokeWidth="2"
        strokeLinecap="round"
        transform="translate(440 610)"
      >
        {Array.from({ length: 13 }).map((_, i) => {
          const angle = (Math.PI * (i + 1)) / 14;
          const round = (value: number) => Math.round(value * 10) / 10;
          return (
            <line
              key={i}
              x1={round(-Math.cos(angle) * 128)}
              y1={round(-Math.sin(angle) * 128)}
              x2={round(-Math.cos(angle) * (i % 2 ? 176 : 214))}
              y2={round(-Math.sin(angle) * (i % 2 ? 176 : 214))}
            />
          );
        })}
      </g>

      {/* Far hills, then the village along the ridge. */}
      <path
        d="M0 640C120 590 230 610 340 628S560 590 700 620 900 600 1000 640V900H0Z"
        style={{ fill: mix(BRAND, 48, NIGHT) }}
      />
      <g style={{ fill: mix(BRAND, 22, NIGHT) }}>
        {/* Temple */}
        <path d="M566 640V596h8v-10h6v-12l6-6v-14l8-24 2-16 2 16 8 24v14l6 6v12h6v10h8v44Z" />
        <path d="M596 514v-22l18 7-18 7" />
        {/* Houses */}
        <path d="M120 660v-34l32-24 32 24v34Z" />
        <path d="M176 664v-26l24-18 24 18v26Z" />
        <path d="M660 662v-30l28-21 28 21v30Z" />
        <path d="M708 664v-24l22-16 22 16v24Z" />
        {/* Trees */}
        <circle cx="62" cy="606" r="34" />
        <circle cx="96" cy="622" r="24" />
        <rect x="58" y="620" width="8" height="46" />
        <circle cx="280" cy="620" r="26" />
        <rect x="277" y="630" width="6" height="34" />
        <circle cx="812" cy="616" r="30" />
        <circle cx="782" cy="630" r="20" />
        <rect x="808" y="628" width="7" height="38" />
      </g>
      </g>

      {/* Fields running down into the dark ground the words sit on. */}
      <path d="M0 556C170 530 330 576 520 558S860 532 1000 566V900H0Z" fill="url(#auth-field)" />
      <path
        d="M452 556C490 572 420 590 462 612S640 640 690 690L640 694C590 650 400 634 396 604S430 572 452 556Z"
        style={{ fill: mix(ACCENT, 50, "white") }}
        opacity="0.5"
      />
      <g fill="none" strokeWidth="2" strokeLinecap="round" style={{ stroke: mix(BRAND, 35, "#7fd0a0") }} opacity="0.3">
        <path d="M0 590C90 584 190 592 300 612" />
        <path d="M0 626C70 622 150 630 240 650" />
        <path d="M640 590C720 584 800 592 880 616" />
        <path d="M720 640C770 636 820 646 860 668" />
      </g>
      <path d="M0 650C150 626 300 690 480 700S780 700 980 742V900H0Z" fill="url(#auth-ground)" />

      {/* Milk cans, waiting by the road. */}
      <g transform="translate(40 -36)">
        <g fill="none" strokeWidth="4" style={{ stroke: mix(BRAND, 34, NIGHT) }}>
          <path d="M638 752c-10 0-10 18 2 18" />
          <path d="M694 752c10 0 10 18-2 18" />
          <path d="M698 772c-8 0-8 15 2 15" />
          <path d="M746 772c8 0 8 15-2 15" />
        </g>
        <path
          d="M640 800v-52c0-8 8-10 12-16v-10h28v10c4 6 12 8 12 16v52Z"
          style={{ fill: mix(BRAND, 14, "#dfe7f0") }}
        />
        <path
          d="M700 806v-42c0-7 7-9 10-13v-9h24v9c3 4 10 6 10 13v42Z"
          style={{ fill: mix(BRAND, 24, "#c5d2e0") }}
        />
        <g style={{ fill: mix(BRAND, 34, NIGHT) }}>
          <rect x="642" y="712" width="48" height="10" />
          <rect x="702" y="734" width="40" height="9" />
          <rect x="640" y="770" width="52" height="3" opacity="0.35" />
          <rect x="700" y="780" width="44" height="3" opacity="0.35" />
        </g>
      </g>

      {/* The wave, and the quiet side the card rests on. */}
      <path d={wave(-58)} fill="url(#auth-gold)" opacity="0.92" />
      <path d={wave(-30)} style={{ fill: mix(ACCENT, 60, "white") }} />
      <path d={wave(-12)} style={{ fill: mix(BRAND, 72, "white") }} />
      <path d={wave(0)} style={{ fill: "var(--background)" }} />
      <path d={wave(0)} fill="url(#auth-tint)" />

      <g fill="none" style={{ stroke: BRAND }} strokeOpacity="0.09" strokeWidth="1.5">
        {[70, 120, 170, 220].map((r) => (
          <circle key={r} cx="1600" cy="0" r={r} />
        ))}
        {[70, 120, 170].map((r) => (
          <circle key={r} cx="1600" cy="900" r={r} />
        ))}
      </g>
    </svg>
  );
}
