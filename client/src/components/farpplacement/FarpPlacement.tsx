import { FarpSiteCheck } from "../../api/_liberationApi";
import {
  FarpKind,
  farpPlacementEnded,
  selectFarpPlacementKind,
} from "../../api/farpPlacementSlice";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import backend from "../../api/backend";
import "./FarpPlacement.css";
import { LatLng } from "leaflet";
import { useCallback, useEffect, useRef, useState } from "react";
import { CircleMarker, Tooltip, useMap, useMapEvents } from "react-leaflet";

const KIND_LABELS: Record<FarpKind, string> = {
  wet_wing: "Wet Wing FARP",
  fat_cow: "Fat Cow FARP",
};

const CHECK_INTERVAL_MS = 150;

interface Candidate {
  position: LatLng;
  check: FarpSiteCheck | null;
}

function tooltipLines(
  kind: FarpKind,
  candidate: Candidate,
  error: string | null,
): string[] {
  if (error) {
    return [error];
  }
  if (!candidate.check) {
    return ["Checking site..."];
  }
  const header = `${KIND_LABELS[kind]} ($${candidate.check.cost}M)`;
  if (candidate.check.valid) {
    return [header, "Click to establish. Right click or Esc to cancel."];
  }
  return [header, ...candidate.check.reasons];
}

/**
 * Placement mode for establishing player FARPs.
 *
 * Choosing a FARP type from the FARP buttons in the main window's top bar
 * enters placement mode. The site under
 * the cursor is validated by the server as the mouse moves; clicking a valid
 * site establishes the FARP.
 */
export default function FarpPlacement() {
  const map = useMap();
  const dispatch = useAppDispatch();
  const kind = useAppSelector(selectFarpPlacementKind);
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastCheck = useRef<number>(0);
  const pending = useRef<number | null>(null);

  const cancel = useCallback(() => {
    dispatch(farpPlacementEnded());
  }, [dispatch]);

  // Start each placement (or a switch of FARP type) with a clean marker.
  useEffect(() => {
    setCandidate(null);
    setError(null);
  }, [kind]);

  useEffect(() => {
    const container = map.getContainer();
    if (kind) {
      container.classList.add("farp-placement-active");
    } else {
      container.classList.remove("farp-placement-active");
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        cancel();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      container.classList.remove("farp-placement-active");
      window.removeEventListener("keydown", onKey);
    };
  }, [map, kind, cancel]);

  const checkSite = useCallback((position: LatLng, siteKind: FarpKind) => {
    lastCheck.current = Date.now();
    backend
      .get(
        `/control-points/farp-site-check?lat=${position.lat}&lng=${position.lng}&kind=${siteKind}`,
      )
      .then((response) => {
        setCandidate((current) =>
          current && current.position.equals(position)
            ? { position, check: response.data }
            : current,
        );
      })
      .catch(() => setError("Could not check FARP site."));
  }, []);

  useMapEvents({
    mousemove: (e) => {
      if (!kind) {
        return;
      }
      setError(null);
      setCandidate({ position: e.latlng, check: null });
      if (pending.current !== null) {
        window.clearTimeout(pending.current);
      }
      const wait = Math.max(
        0,
        CHECK_INTERVAL_MS - (Date.now() - lastCheck.current),
      );
      pending.current = window.setTimeout(() => {
        pending.current = null;
        checkSite(e.latlng, kind);
      }, wait);
    },
    click: (e) => {
      if (!kind) {
        return;
      }
      backend
        .post(`/control-points/farps`, {
          position: { lat: e.latlng.lat, lng: e.latlng.lng },
          kind: kind,
        })
        .then(() => cancel())
        .catch((err) => {
          const detail = err?.response?.data?.detail;
          setCandidate({ position: e.latlng, check: null });
          setError(
            typeof detail === "string" ? detail : "Could not establish FARP.",
          );
        });
    },
    contextmenu: () => {
      if (kind) {
        cancel();
      }
    },
  });

  if (!kind || !candidate) {
    return null;
  }

  const valid = candidate.check?.valid && !error;
  const color =
    candidate.check === null && !error
      ? "#cccccc"
      : valid
        ? "#2ecc71"
        : "#e74c3c";
  return (
    <CircleMarker
      center={candidate.position}
      radius={10}
      pathOptions={{ color, fillColor: color, fillOpacity: 0.4 }}
      interactive={false}
    >
      <Tooltip permanent direction="right" offset={[12, 0]}>
        {tooltipLines(kind, candidate, error).map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </Tooltip>
    </CircleMarker>
  );
}
