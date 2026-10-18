import type { ReactNode } from "react";

// A line-art robot holding the login board: head and arms behind the board, gripper hands in
// front of its edges. Both drawings share one coordinate box (440 x 290) whose board area starts
// 44px in from the left and 118px down, so the hands land exactly on the board's sides.
// Colours come from the fabric theme (styles/fabric.css); motion is CSS and stops for
// prefers-reduced-motion.

const BOX = "pointer-events-none absolute -left-[44px] -top-[118px] h-[290px] w-[440px]";

function Arm({ d }: { d: string }) {
  // An outlined tube: a thick ink stroke with a thinner board-coloured stroke on top.
  return (
    <>
      <path d={d} strokeWidth="15" />
      <path d={d} strokeWidth="11.5" className="stroke-(--te-linen-card)" />
    </>
  );
}

function Hand({ flip }: { flip?: boolean }) {
  return (
    <g transform={flip ? "translate(440 0) scale(-1 1)" : undefined}>
      <rect x="25" y="224" width="22" height="38" rx="7" />
      <path d="M29 234h14" strokeWidth="1" opacity=".5" />
      {/* three fingers wrapped round the front of the board */}
      <rect x="39" y="229" width="21" height="8" rx="4" />
      <rect x="39" y="239" width="22" height="8" rx="4" />
      <rect x="39" y="249" width="20" height="8" rx="4" />
    </g>
  );
}

export function LoginRobot({ children }: { children: ReactNode }) {
  return (
    <div className="relative isolate mt-[124px]">
      {/* behind the board: torso, arms, neck and head */}
      <svg
        viewBox="0 0 440 290"
        aria-hidden="true"
        className={`${BOX} te-robot-rise z-0 fill-(--te-linen-card) stroke-(--te-ink-soft)`}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M150 150V122q0-18 20-18h100q20 0 20 18v28z" />
        <path d="M204 112h32" strokeWidth="1.2" opacity=".6" />
        <g fill="none">
          <Arm d="M156 116L31 152L37 232" />
          <Arm d="M284 116L409 152L403 232" />
          <path d="M33 206l9 -1M407 206l-9 -1" strokeWidth="1" opacity=".55" />
        </g>
        <circle cx="31" cy="152" r="8" />
        <circle cx="409" cy="152" r="8" />
        <circle cx="156" cy="116" r="10" />
        <circle cx="284" cy="116" r="10" />
        <rect x="206" y="90" width="28" height="18" rx="3" />
        <path d="M206 96h28M206 102h28" strokeWidth="1" opacity=".5" />

        <g className="te-robot-head">
          <rect x="161" y="50" width="11" height="30" rx="4" />
          <rect x="268" y="50" width="11" height="30" rx="4" />
          <path d="M220 28V12" fill="none" />
          <circle cx="220" cy="9" r="5" className="te-robot-led fill-[#5eead4]" />
          <rect x="170" y="26" width="100" height="72" rx="20" />
          {/* visor with glowing eyes that scan, blink, and a small smile */}
          <rect x="182" y="40" width="76" height="44" rx="13" className="fill-(--te-visor)" />
          <g className="te-robot-scan">
            <g className="te-robot-blink">
              <rect x="196" y="55" width="14" height="12" rx="6" className="fill-[#5eead4]" stroke="none" />
              <rect x="230" y="55" width="14" height="12" rx="6" className="fill-[#5eead4]" stroke="none" />
            </g>
          </g>
          <path d="M210 75q10 5 20 0" fill="none" stroke="#5eead4" strokeWidth="1.6" opacity=".8" />
          <circle cx="180" cy="92" r="1.6" className="fill-(--te-ink-soft)" stroke="none" />
          <circle cx="260" cy="92" r="1.6" className="fill-(--te-ink-soft)" stroke="none" />
        </g>
      </svg>

      <div className="relative z-[1]">{children}</div>

      {/* in front of the board: the gripper hands */}
      <svg
        viewBox="0 0 440 290"
        aria-hidden="true"
        className={`${BOX} te-robot-rise z-[2] fill-(--te-linen-card) stroke-(--te-ink-soft)`}
        strokeWidth="1.6"
        strokeLinejoin="round"
      >
        <Hand />
        <Hand flip />
      </svg>
    </div>
  );
}
