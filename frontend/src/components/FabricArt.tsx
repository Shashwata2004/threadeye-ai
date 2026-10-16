// Decorative line art for the fabric skin. Purely visual: hidden from assistive technology.

// Faces filled with the page colour so front shapes hide the lines behind them, in either theme.
const LINEN_FILL = { fill: "var(--te-linen)" };

/** Line-art sketch of a hand loom, drawn in currentColor so callers set tint and opacity. */
export function LoomSketch({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 260 220" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      {/* back posts and top beam */}
      <path d="M40 200V40M200 180V30M30 40h180M30 30l10 10M210 30l-10 10" />
      {/* front posts and breast beam */}
      <path d="M70 212V95M232 196V85M60 95l172-10M60 103l172-10" />
      {/* side rails */}
      <path d="M40 120l30-10M200 110l32-12M40 196l30 12M200 178l32 14" />
      {/* heddle frame hanging from the top beam */}
      <path d="M95 40v28M175 40v24M88 68h94M88 92h94M88 68v24M182 68v24" />
      {/* warp threads */}
      <path d="M100 40l-6 58M110 40l-5 58M120 40l-4 58M130 40l-3 58M140 40l-2 58M150 40l-1 58M160 40v58M170 40l1 58" />
      {/* woven cloth on the breast beam */}
      <path d="M92 99l-4 26h112l-4-28M90 108h108M89 116h110" />
      {/* bench */}
      <path d="M20 170l70-8 30 6-70 9zM20 170v24M50 177v26M90 162v22M120 168v24" />
    </svg>
  );
}

/** Wooden thread spool with a loose thread tail, for the bottom of the sidebar. */
export function ThreadSpool({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 96 110" aria-hidden="true" className={className}>
      <defs>
        <linearGradient id="te-wood" x1="0" x2="1">
          <stop offset="0" stopColor="#7a5230" />
          <stop offset=".45" stopColor="#c89a62" />
          <stop offset="1" stopColor="#6b4526" />
        </linearGradient>
        <linearGradient id="te-thread" x1="0" x2="1">
          <stop offset="0" stopColor="#bfb3a0" />
          <stop offset=".45" stopColor="#f3ece0" />
          <stop offset="1" stopColor="#a99c87" />
        </linearGradient>
        <pattern id="te-wind" width="4" height="3" patternUnits="userSpaceOnUse">
          <path d="M0 2.5L4 .5" stroke="#8f8370" strokeWidth=".6" opacity=".55" />
        </pattern>
      </defs>
      {/* thread tail */}
      <path d="M22 62C8 70 4 88 14 100s-6 8-12 6" fill="none" stroke="#e8dfcf" strokeWidth="1.4" strokeLinecap="round" />
      {/* bottom flange */}
      <ellipse cx="50" cy="86" rx="32" ry="9" fill="#5a3a1f" />
      <rect x="18" y="78" width="64" height="8" fill="url(#te-wood)" />
      <ellipse cx="50" cy="78" rx="32" ry="9" fill="#d3a76f" />
      {/* wound thread */}
      <rect x="25" y="30" width="50" height="46" fill="url(#te-thread)" />
      <rect x="25" y="30" width="50" height="46" fill="url(#te-wind)" />
      {/* top flange */}
      <ellipse cx="50" cy="30" rx="32" ry="9" fill="#5a3a1f" />
      <rect x="18" y="22" width="64" height="8" fill="url(#te-wood)" />
      <ellipse cx="50" cy="22" rx="32" ry="9" fill="#d9ae76" />
      <ellipse cx="50" cy="22" rx="6" ry="2" fill="#4a2f18" />
    </svg>
  );
}

/** Line-art sketch of a cloth roll with a length of fabric unrolled in front, in currentColor. */
export function FabricRollSketch({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 260 190" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      {/* roll body and back end */}
      <path d="M62 30h150M62 110h150M62 30c-9 0-15 18-15 40s6 40 15 40" />
      {/* front end with wound layers and core */}
      <ellipse cx="212" cy="70" rx="15" ry="40" />
      <ellipse cx="212" cy="70" rx="11" ry="29" />
      <ellipse cx="212" cy="70" rx="7" ry="17" />
      <ellipse cx="212" cy="70" rx="3.5" ry="7" />
      {/* folds along the roll */}
      <path d="M80 34c-4 12-4 60 0 72M120 32c-3 14-3 62 0 76M160 32c-3 14-3 62 0 76" opacity=".55" />
      {/* unrolled length of cloth */}
      <path d="M62 110L28 172c30 6 60-6 92 0s62 6 92 0l-0-62" />
      <path d="M52 128h160M44 143h168M36 158h176" opacity=".5" />
      <path d="M95 110l-14 64M135 110l-6 64M175 110l2 63" opacity=".4" />
      {/* loose selvedge thread */}
      <path d="M227 82c14 8 20 30 8 48s4 28 16 30" opacity=".7" />
    </svg>
  );
}

/** Line-art stack of taped delivery cartons. Faces are filled with the linen colour so the boxes in
 *  front hide the edges behind them; set opacity on the element to fade the whole drawing at once. */
export function DeliveryBoxesSketch({ className }: { className?: string }) {
  return (
    <svg viewBox="36 44 212 226" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      {/* back carton */}
      <path d="M170 95L239.3 135L178.7 170L109.4 130ZM109.4 130V190L178.7 230L239.3 195V135M178.7 170V230" style={LINEN_FILL} />
      <path d="M204.6 115L144 150" opacity=".6" />
      {/* carton stacked on top */}
      <path d="M178 56L231.7 87L186.7 113L133 82ZM133 82V127L186.7 158L231.7 132V87M186.7 113V158" style={LINEN_FILL} />
      <path d="M204.8 71.5L159.8 97.5V113.2" opacity=".6" />
      {/* front carton with "this side up" arrows */}
      <path d="M105 128L174.3 168L113.7 203L44.4 163ZM44.4 163V223L113.7 263L174.3 228V168M113.7 203V263" style={LINEN_FILL} />
      <path d="M139.6 148L79 183V204" opacity=".6" />
      <path d="M131.8 225.5v-18m-4 5l4-5 4 5M144 218.5v-18m-4 5l4-5 4 5" opacity=".6" />
    </svg>
  );
}

/** Brand mark: a sewing needle whose eye is an eye, with thread passing through it. */
export function ThreadEyeMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      {/* needle shaft running to a point at the lower left */}
      <path d="M31 9L7 33" strokeWidth="2.2" />
      {/* the needle's eye, drawn as an eye with its pupil */}
      <path d="M33.5 6.5c-3.6-.6-7.4 1.7-9 5.4 3.6.6 7.4-1.7 9-5.4z" strokeWidth="1.6" style={LINEN_FILL} />
      <circle cx="29" cy="9.2" r="1.5" fill="currentColor" stroke="none" />
      {/* thread through the eye, looping away */}
      <path d="M36 4c-4 3-6 4-9 9-2 4 1 8 5 8 3 0 4 3 2 5" strokeWidth="1.1" opacity=".7" pathLength={1} className="te-thread-draw" />
    </svg>
  );
}
