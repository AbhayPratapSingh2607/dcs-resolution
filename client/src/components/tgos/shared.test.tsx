import { Tgo } from "../../api/liberationApi";
import { intelLabel, opacityForTgo } from "./shared";

const base: Tgo = {
  id: "1",
  name: "SAM",
  control_point_name: "Base",
  category: "aa",
  blue: false,
  position: { lat: 0, lng: 0 },
  units: ["SA-6 STR"],
  threat_ranges: [],
  detection_ranges: [],
  dead: false,
  sidc: "10061000001300000000",
  mobile: false,
};

describe("fog of war display", () => {
  it("shows confirmed sites normally", () => {
    expect(opacityForTgo(base)).toBe(1.0);
    expect(intelLabel(base)).toBeNull();
  });

  it("dims estimated sites and labels the uncertainty", () => {
    const tgo = { ...base, estimated: true, uncertainty_m: 4200 };
    expect(opacityForTgo(tgo)).toBeLessThan(1.0);
    expect(intelLabel(tgo)).toContain("±4.2 km");
  });

  it("makes unconfirmed reports faint", () => {
    const tgo = { ...base, known: false, estimated: true };
    expect(opacityForTgo(tgo)).toBeLessThan(0.5);
    expect(intelLabel(tgo)).toBe("Unconfirmed report");
  });
});
