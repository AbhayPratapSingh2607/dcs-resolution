import { FarpSiteCheck } from "../../api/_liberationApi";
import backend from "../../api/backend";
import "./FarpPlacement.css";
import L, { LatLng } from "leaflet";
import { useCallback, useEffect, useRef, useState } from "react";
import { CircleMarker, Tooltip, useMap, useMapEvents } from "react-leaflet";

type FarpKind = "frontline" | "covert";

const KIND_LABELS: Record<FarpKind, string> = {
  frontline: "Wet Wing FARP",
  covert: "Fat Cow FARP",
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
 * Map control and placement mode for establishing player FARPs.
 *
 * Choosing a FARP type from the control enters placement mode. The site under
 * the cursor is validated by the server as the mouse moves; clicking a valid
 * site establishes the FARP.
 */
export default function FarpPlacement() {
  const map = useMap();
  const [kind, setKind] = useState<FarpKind | null>(null);
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastCheck = useRef<number>(0);
  const pending = useRef<number | null>(null);
  const setKindRef = useRef(setKind);
  setKindRef.current = setKind;

  const cancel = useCallback(() => {
    setKind(null);
    setCandidate(null);
    setError(null);
  }, []);

  // The leaflet control with the mode buttons. Created once.
  useEffect(() => {
    const control = new L.Control({ position: "topleft" });
    control.onAdd = () => {
      const container = L.DomUtil.create(
        "div",
        "leaflet-bar leaflet-control farp-placement-control",
      );
      L.DomEvent.disableClickPropagation(container);
      (Object.keys(KIND_LABELS) as FarpKind[]).forEach((k) => {
        const button = L.DomUtil.create(
          "a",
          "farp-placement-button",
          container,
        );
        button.href = "#";
        button.title =
          k === "frontline"
            ? "Establish a Wet Wing FARP (set up by a C-130): more helicopters, costs more"
            : "Establish a Fat Cow FARP (set up by a CH-47): 2 helicopters, cheaper";
        button.innerText = k === "frontline" ? "Wet Wing" : "Fat Cow";
        L.DomEvent.on(button, "click", (e) => {
          L.DomEvent.preventDefault(e);
          setKindRef.current((current) => (current === k ? null : k));
        });
      });
      return container;
    };
    control.addTo(map);
    return () => {
      control.remove();
    };
  }, [map]);

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
