import { LatLng } from "../../api/_liberationApi";
import { divIcon } from "leaflet";
import { Marker } from "react-leaflet";

const COLOR = "#ff3b30";
const SIZE = 44;

/** A target crosshair: a ring with four ticks and a center dot, drawn in
 * screen pixels so it reads the same at every zoom. */
const CROSSHAIR_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" width="${SIZE}" height="${SIZE}" viewBox="0 0 44 44">
  <g fill="none" stroke="#000" stroke-opacity="0.55" stroke-width="5" stroke-linecap="round">
    <circle cx="22" cy="22" r="14"/>
    <path d="M22 2v10M22 32v10M2 22h10M32 22h10"/>
  </g>
  <g fill="none" stroke="${COLOR}" stroke-width="2.5" stroke-linecap="round">
    <circle cx="22" cy="22" r="14"/>
    <path d="M22 2v10M22 32v10M2 22h10M32 22h10"/>
  </g>
  <circle cx="22" cy="22" r="2" fill="${COLOR}"/>
</svg>`;

const crosshairIcon = divIcon({
  html: CROSSHAIR_SVG,
  className: "strike-crosshair",
  iconSize: [SIZE, SIZE],
  iconAnchor: [SIZE / 2, SIZE / 2],
});

/**
 * A planned strike at a target (the opening salvo on turn 0, fire missions
 * after that): a red target crosshair over it. Not interactive, so the
 * target's own marker stays clickable.
 */
export function StrikeMark(props: { position: LatLng; strikes?: string[] }) {
  if (!props.strikes || props.strikes.length === 0) {
    return null;
  }
  return (
    <Marker
      position={props.position}
      icon={crosshairIcon}
      interactive={false}
      keyboard={false}
      zIndexOffset={1000}
    />
  );
}

/** The strike lines for a tooltip. */
export function StrikeLines(props: { strikes?: string[] }) {
  if (!props.strikes || props.strikes.length === 0) {
    return null;
  }
  return (
    <>
      {props.strikes.map((line) => (
        <span key={line}>
          <br />
          <b style={{ color: "#ff3b30" }}>{line}</b>
        </span>
      ))}
    </>
  );
}
