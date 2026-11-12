import { selectFlights } from "../../api/flightsSlice";
import { useAppSelector } from "../../app/hooks";
import Aircraft from "../aircraft";
import { LayerGroup } from "react-leaflet";

export default function AircraftLayer() {
  const state = useAppSelector(selectFlights);
  const flights = state.flights;
  const glide = state.glide ?? false;
  return (
    <LayerGroup>
      {Object.values(flights).map((flight) => {
        return <Aircraft key={flight.id} flight={flight} glide={glide} />;
      })}
    </LayerGroup>
  );
}
