import {
  useOpenNewTgoPackageDialogMutation,
  useOpenTgoInfoDialogMutation,
} from "../../api/liberationApi";
import { Tgo as TgoModel } from "../../api/liberationApi";
import {
  selectHighlightEmitters,
  selectHoveredEmitter,
  setHoveredEmitter,
} from "../../api/mapSlice";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import MobileTgo from "./MobileTgo";
import { TgoTooltip, iconForTgo, opacityForTgo } from "./shared";
import { Circle, Marker } from "react-leaflet";
import { StrikeMark } from "../strikemark/StrikeMark";

interface TgoProps {
  tgo: TgoModel;
}

function StaticTgo(props: TgoProps) {
  const [openNewPackageDialog] = useOpenNewTgoPackageDialogMutation();
  const [openInfoDialog] = useOpenTgoInfoDialogMutation();
  const dispatch = useAppDispatch();
  // Raised above other icons while this emitter (or its ring) is hovered.
  const raised = useAppSelector(
    (state) =>
      selectHighlightEmitters(state) &&
      selectHoveredEmitter(state) === props.tgo.id,
  );
  // Fog of war: where we think it is, and how sure we are.
  const uncertainty = props.tgo.estimated ? (props.tgo.uncertainty_m ?? 0) : 0;
  return (
    <>
      {uncertainty > 0 && (
        <Circle
          center={props.tgo.position}
          radius={uncertainty}
          interactive={false}
          pathOptions={{
            color: props.tgo.blue ? "#0084ff" : "#c85050",
            weight: 1,
            dashArray: "6",
            fillOpacity: 0.05,
          }}
        />
      )}
      <StrikeMark position={props.tgo.position} strikes={props.tgo.strikes} />
      <Marker
        position={props.tgo.position}
        icon={iconForTgo(props.tgo)}
        opacity={opacityForTgo(props.tgo)}
        zIndexOffset={raised ? 10000 : 0}
        eventHandlers={{
          click: () => {
            openInfoDialog({ tgoId: props.tgo.id });
          },
          contextmenu: () => {
            openNewPackageDialog({ tgoId: props.tgo.id });
          },
          // Hovering the emitter highlights its ring (and vice versa).
          mouseover: () =>
            dispatch(
              setHoveredEmitter({ id: props.tgo.id, source: "emitter" }),
            ),
          mouseout: () => dispatch(setHoveredEmitter(null)),
        }}
      >
        <TgoTooltip tgo={props.tgo} />
      </Marker>
    </>
  );
}

export default function Tgo(props: TgoProps) {
  if (props.tgo.mobile) {
    return <MobileTgo tgo={props.tgo} />;
  }
  return <StaticTgo tgo={props.tgo} />;
}
