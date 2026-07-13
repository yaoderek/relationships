import { useEffect, useState } from "react";

export type SpineSection = { id: string; label: string };

export default function Spine({ sections }: { sections: SpineSection[] }) {
  const [active, setActive] = useState(sections[0]?.id);

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActive(e.target.id);
        }
      },
      { rootMargin: "-15% 0px -70% 0px" },
    );
    for (const s of sections) {
      const el = document.getElementById(s.id);
      if (el) obs.observe(el);
    }
    return () => obs.disconnect();
  }, [sections]);

  return (
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
    </nav>
  );
}
