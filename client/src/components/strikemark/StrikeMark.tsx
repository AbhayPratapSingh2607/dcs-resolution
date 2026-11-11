import { LatLng } from "../../api/_liberationApi";
import { Circle } from "react-leaflet";

/**
 * A planned strike at a target (the opening salvo on turn 0, fire missions
 * after that): a red crosshair ring around it. Not interactive, so the
 * target's own marker stays clickable.
 */
export function StrikeMark(props: { position: LatLng; strikes?: string[] }) {
  if (!props.strikes || props.strikes.length === 0) {
    return null;
  }
  return (
    <>
      <Circle
        center={props.position}
        radius={2500}
        interactive={false}
        pathOptions={{
          color: "#ff3b30",
          weight: 2,
          dashArray: "4 6",
          fillOpacity: 0.08,
        }}
      />
      <Circle
        center={props.position}
        radius={900}
        interactive={false}
        pathOptions={{ color: "#ff3b30", weight: 2, fillOpacity: 0 }}
      />
    </>
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
