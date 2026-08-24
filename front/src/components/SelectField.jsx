import React, { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

export default function SelectField({
  value,
  onChange,
  options = [],
  placeholder = "请选择",
  ariaLabel,
  className = "",
  disabled = false,
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  const selected = options.find((item) => item.value === value);

  useEffect(() => {
    if (!open) return undefined;
    function handleClick(event) {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    function handleKey(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  function pick(nextValue) {
    if (disabled) return;
    onChange(nextValue);
    setOpen(false);
  }

  return (
    <div className={`ui-select-wrap ${className}`.trim()} ref={wrapRef}>
      <button
        type="button"
        className={`ui-select-trigger${open ? " open" : ""}`}
        onClick={() => !disabled && setOpen((v) => !v)}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
      >
        <span className="ui-select-value">{selected?.label || placeholder}</span>
        <ChevronDown size={16} className="ui-select-chevron" aria-hidden="true" />
      </button>
      {open ? (
        <ul className="ui-select-menu" role="listbox" aria-label={ariaLabel}>
          {options.map((option) => (
            <li key={option.value}>
              <button
                type="button"
                role="option"
                aria-selected={option.value === value}
                className={`ui-select-option${option.value === value ? " active" : ""}`}
                onClick={() => pick(option.value)}
              >
                <span>{option.label}</span>
                {option.hint ? <small>{option.hint}</small> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
