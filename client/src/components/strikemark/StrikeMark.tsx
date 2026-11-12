import { LatLng } from "../../api/_liberationApi";
import { divIcon } from "leaflet";
import { Marker } from "react-leaflet";

const COLOR = "#ff5a4f";
const SIZE = 30;

/** A minimal target crosshair: a thin ring and four short ticks off its
 * edge, drawn in screen pixels so it reads the same at every zoom. A faint
 * dark halo keeps it legible on bright terrain. */
const TICKS = "M15 1.5v5M15 23.5v5M1.5 15h5M23.5 15h5";
const CROSSHAIR_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" width="${SIZE}" height="${SIZE}" viewBox="0 0 30 30">
  <g fill="none" stroke="#000" stroke-opacity="0.35" stroke-width="3" stroke-linecap="round">
    <circle cx="15" cy="15" r="7.5"/>
    <path d="${TICKS}"/>
  </g>
  <g fill="none" stroke="${COLOR}" stroke-opacity="0.9" stroke-width="1.25" stroke-linecap="round">
    <circle cx="15" cy="15" r="7.5"/>
    <path d="${TICKS}"/>
  </g>
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
