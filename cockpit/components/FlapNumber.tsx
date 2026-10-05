"use client";

import { useEffect, useState } from "react";

/** A number on split-flap tiles, like the website's board: each digit turns over once when it first shows or changes. */
export function FlapNumber({ value, label }: { value: number; label?: string }) {
  const text = String(value);
  const [shown, setShown] = useState(text);
  const [turn, setTurn] = useState(0);
  useEffect(() => {
    setShown(text);
    setTurn((t) => t + 1);
  }, [text]);
  return (
    <span className="flap" role="img" aria-label={label ? `${value} ${label}` : String(value)}>
      {shown.split("").map((d, i) => (
        <span key={`${turn}-${i}`} className="d flip" style={{ animationDelay: `${i * 70}ms` }} aria-hidden="true">{d}</span>
      ))}
    </span>
  );
}
