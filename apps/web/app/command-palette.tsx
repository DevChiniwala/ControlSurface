"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Search, X } from "lucide-react";

export type CommandDestination = {
  id: string;
  label: string;
  section: string;
};

export function CommandPalette({
  destinations,
  onSelect,
  onClose,
}: {
  destinations: CommandDestination[];
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const filtered = useMemo(
    () =>
      destinations.filter((item) =>
        `${item.label} ${item.section}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [destinations, query],
  );

  useEffect(() => {
    input.current?.focus();
  }, []);

  return (
    <div className="modal-backdrop command-backdrop" onMouseDown={onClose}>
      <section
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Navigate ControlSurface"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="command-input-row">
          <Search size={18} />
          <input
            ref={input}
            aria-label="Find a view"
            placeholder="Jump to a view…"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") onClose();
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive((value) => Math.min(value + 1, filtered.length - 1));
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((value) => Math.max(value - 1, 0));
              }
              if (event.key === "Enter" && filtered[active]) {
                onSelect(filtered[active].id);
              }
            }}
          />
          <button
            className="icon-button"
            aria-label="Close navigation search"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>
        <div className="command-list" role="listbox" aria-label="Views">
          {filtered.length ? (
            filtered.map((item, index) => (
              <button
                key={item.id}
                role="option"
                aria-selected={index === active}
                className={index === active ? "active" : ""}
                onMouseEnter={() => setActive(index)}
                onClick={() => onSelect(item.id)}
              >
                <span>
                  {item.label}
                  <small>{item.section}</small>
                </span>
                <ArrowRight size={15} />
              </button>
            ))
          ) : (
            <p>
              No matching view. Search currently covers navigation, not
              telemetry records.
            </p>
          )}
        </div>
        <div className="command-footer">
          Navigate with ↑ ↓ · Open with Enter · Close with Esc
        </div>
      </section>
    </div>
  );
}
