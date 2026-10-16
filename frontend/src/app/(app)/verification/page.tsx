import { Placeholder } from "@/components/Placeholder";

export default function Page() {
  return (
    // Background sketch in the bottom-right corner, with room kept for it below the card.
    <div className="relative z-[1] md:min-h-[calc(100vh-9rem)] md:pb-[21rem]">
      <div
        aria-hidden="true"
        className="te-sketch-stamp pointer-events-none absolute bottom-0 right-0 -z-10 hidden h-80 w-[330px] bg-contain bg-right-bottom bg-no-repeat opacity-30 md:block"
      />
      <Placeholder titleKey="nav.verification" bodyKey="placeholder.verification" milestone="M4" />
    </div>
  );
}
