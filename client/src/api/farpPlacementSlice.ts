import { RootState } from "../app/store";
import { gameUnloaded } from "./actions";
import { PayloadAction, createSlice } from "@reduxjs/toolkit";

export type FarpKind = "wet_wing" | "fat_cow" | "rescue_king";

interface FarpPlacementState {
  kind: FarpKind | null;
}

const initialState: FarpPlacementState = {
  kind: null,
};

/**
 * The FARP type being placed on the map, if any. Placement is started from the
 * FARP buttons in the main window's top bar.
 */
export const farpPlacementSlice = createSlice({
  name: "farpPlacement",
  initialState,
  reducers: {
    // Choosing the type already being placed turns placement off.
    requested: (state, action: PayloadAction<FarpKind>) => {
      state.kind = state.kind === action.payload ? null : action.payload;
    },
    ended: (state) => {
      state.kind = null;
    },
  },
  extraReducers: (builder) => {
    builder.addCase(gameUnloaded, (state) => {
      state.kind = null;
    });
  },
});

export const { requested: farpPlacementRequested, ended: farpPlacementEnded } =
  farpPlacementSlice.actions;

export const selectFarpPlacementKind = (state: RootState) =>
  state.farpPlacement.kind;

export default farpPlacementSlice.reducer;
