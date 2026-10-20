import { Check, Pencil, X } from "lucide-react";

type PreviewKind = "draw" | "inline" | "floating";

const gray = "#a8b0bc";
const blue = "#2458a6";
const red = "#e52b22";

export function TableToolImage({ source }: { source: string }) {
  return (
    <svg viewBox="72 52 368 304" width="100%" height="100%" aria-hidden="true" focusable="false">
      <image href={source} x="0" y="0" width="512" height="512" />
    </svg>
  );
}

export function TableToolPreview({ kind }: { kind: PreviewKind }) {
  return (
    <svg viewBox="72 78 368 304" width="100%" height="100%" aria-hidden="true" focusable="false">
      {kind === "draw" ? (
        <>
          <g fill="none" stroke={gray} strokeWidth="5">
            <rect x="116" y="146" width="280" height="222" />
            <path d="M256 146V368M116 257H396" />
          </g>
          <path d="M116 257H256V368" fill="none" stroke={blue} strokeWidth="9" />
          <rect x="326" y="95" width="94" height="94" fill="white" />
          <Pencil x="336" y="105" width="74" height="74" color={blue} strokeWidth="2.5" />
        </>
      ) : (
        <>
          {kind === "inline" ? (
            <>
              <path d="M116 157H342M116 202H396M116 306H161M351 306H396M116 351H396" fill="none" stroke={gray} strokeWidth="7" />
              <g fill="#e3ebf8" stroke={blue} strokeWidth="5">
                <rect x="181" y="241" width="150" height="65" />
                <path d="M256 241V306M181 273H331" fill="none" />
              </g>
            </>
          ) : (
            <>
              <g fill="#e3ebf8" stroke={gray} strokeWidth="5">
                <rect x="152" y="146" width="208" height="124" />
                <path d="M256 146V270M152 208H360" fill="none" />
              </g>
              <path d="M116 315H396M116 360H396" fill="none" stroke={gray} strokeWidth="7" />
            </>
          )}
          <circle cx="388" cy="116" r="26" fill={kind === "inline" ? blue : red} />
          {kind === "inline" ? (
            <Check x="369" y="97" width="38" height="38" color="white" strokeWidth="3.5" />
          ) : (
            <X x="372" y="100" width="32" height="32" color="white" strokeWidth="3.5" />
          )}
        </>
      )}
    </svg>
  );
}
