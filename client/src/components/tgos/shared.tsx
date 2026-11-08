import { Tgo as TgoModel } from "../../api/liberationApi";
import SplitLines from "../splitlines/SplitLines";
import { Icon, Point } from "leaflet";
import ms from "milsymbol";
import { Tooltip } from "react-leaflet";

export function iconForTgo(tgo: TgoModel) {
  const symbol = new ms.Symbol(tgo.sidc, { size: 24 });
  return new Icon({
    iconUrl: symbol.toDataURL(),
    iconAnchor: new Point(symbol.getAnchor().x, symbol.getAnchor().y),
  });
}

/** Fog of war: unconfirmed reports are faint, estimated positions dimmed. */
export function opacityForTgo(tgo: TgoModel): number {
  if (tgo.known === false) {
    return 0.35;
  }
  return tgo.estimated ? 0.7 : 1.0;
}

export function intelLabel(tgo: TgoModel): string | null {
  if (tgo.known === false) {
    return "Unconfirmed report";
  }
  if (tgo.estimated) {
    const km = Math.round((tgo.uncertainty_m ?? 0) / 100) / 10;
    return `Estimated position (±${km} km), not confirmed`;
  }
  return null;
}

export function TgoTooltip(props: { tgo: TgoModel }) {
  const label = intelLabel(props.tgo);
  return (
    <Tooltip>
      {`${props.tgo.name} (${props.tgo.control_point_name})`}
      <br />
      {label ? <i>{label}</i> : <SplitLines items={props.tgo.units} />}
      {props.tgo.detection && (
        <>
          <br />
          <i>{props.tgo.detection}</i>
        </>
      )}
    </Tooltip>
  );
}
