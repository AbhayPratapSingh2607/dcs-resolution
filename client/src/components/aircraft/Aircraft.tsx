import { Flight } from "../../api/liberationApi";
import { Icon, LatLng, Marker as LMarker, Point } from "leaflet";
import ms from "milsymbol";
import { memo, useEffect, useMemo, useRef } from "react";
import { Marker } from "react-leaflet";

function iconForFlight(sidc: string) {
  const symbol = new ms.Symbol(sidc, {
    size: 20,
  });

  return new Icon({
    iconUrl: symbol.toDataURL(),
    iconAnchor: new Point(symbol.getAnchor().x, symbol.getAnchor().y),
  });
}

/** Longest glide between two updates (ms); a slower update just arrives. */
const MAX_GLIDE_MS = 500;
/** A jump this far (m) is a respawn or a new turn, not movement: no glide. */
const TELEPORT_M = 50000;

interface AircraftProps {
  flight: Flight;
  /**
   * Glide to each new position over the time since the last one, instead of
   * jumping: while the whole turn is fast-forwarded, positions arrive a few
   * times a second and the sim's pace varies with the fighting.
   */
  glide?: boolean;
}

function Aircraft(props: AircraftProps) {
  const position = props.flight.position;
  const glide = props.glide ?? false;
  const sidc = props.flight.sidc;
  const icon = useMemo(() => iconForFlight(sidc), [sidc]);
  const markerRef = useRef<LMarker | null>(null);
  // The position given to react-leaflet, which moves the marker whenever it
  // changes. While gliding it stays put and the glide moves the marker.
  const placed = useRef(position);
  if (!glide || placed.current == null) {
    placed.current = position;
  }
  const lastUpdate = useRef(0);
  const frame = useRef(0);

  useEffect(() => {
    const now = performance.now();
    const interval = Math.min(now - lastUpdate.current, MAX_GLIDE_MS);
    lastUpdate.current = now;
    cancelAnimationFrame(frame.current);
    const marker = markerRef.current;
    if (!glide || marker == null || position == null) {
      return;
    }
    const from = marker.getLatLng();
    const to = new LatLng(position.lat, position.lng);
    if (interval <= 0 || from.distanceTo(to) > TELEPORT_M) {
      marker.setLatLng(to);
      return;
    }
    const step = (time: number) => {
      const k = Math.min(Math.max((time - now) / interval, 0), 1);
      marker.setLatLng([
        from.lat + (to.lat - from.lat) * k,
        from.lng + (to.lng - from.lng) * k,
      ]);
      if (k < 1) {
        frame.current = requestAnimationFrame(step);
      }
    };
    frame.current = requestAnimationFrame(step);
  }, [position?.lat, position?.lng, glide]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  if (position == null || placed.current == null) {
    return <></>;
  }

  return <Marker ref={markerRef} position={placed.current} icon={icon} />;
}

// Only this aircraft's symbol, position and glide redraw it: while fast
// forwarding, every other flight's position changes several times a second.
export default memo(
  Aircraft,
  (prev, next) =>
    prev.glide === next.glide &&
    prev.flight.sidc === next.flight.sidc &&
    prev.flight.position?.lat === next.flight.position?.lat &&
    prev.flight.position?.lng === next.flight.position?.lng
);
