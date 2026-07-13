import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

export type SpineSection = { id: string; label: string };

export default function Spine({ sections }: { sections: SpineSection[] }) {
  const [active, setActive] = useState(sections[0]?.id);
  const [slot, setSlot] = useState<Element | null>(null);

  useEffect(() => {
    setSlot(document.getElementById("spine-slot"));
  }, []);

  useEffect(() => {
    if (sections.length < 2) return;
    // Active section = the last one whose top has passed a line 25% down the
    // viewport; pinned to the final section once scrolled to the bottom.
    const onScroll = () => {
      const line = window.innerHeight * 0.25;
      let current = sections[0].id;
      for (const s of sections) {
        const el = document.getElementById(s.id);
        if (el && el.getBoundingClientRect().top <= line) current = s.id;
      }
      const atBottom = window.innerHeight + window.scrollY
        >= document.documentElement.scrollHeight - 4;
      if (atBottom) current = sections[sections.length - 1].id;
      setActive(current);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [sections]);

  if (!slot || sections.length < 2) return null;
  return createPortal(
    <nav className="spine" aria-label="Page sections">
      {sections.map((s) => (
        <a key={s.id} href={`#${s.id}`}
           className={active === s.id ? "spine-active" : ""}
           onClick={(e) => {
             e.preventDefault();
             document.getElementById(s.id)?.scrollIntoView(
               { behavior: "smooth", block: "start" });
           }}>
          {s.label}
        </a>
      ))}
    </nav>,
    slot,
  );
}
