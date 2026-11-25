// Componentes JS incluidos. Un editor (Python) los pide con `ui.custom("<nombre>", **props)`.
// Firma: (props, ctx) => HTMLElement. Las props son JSON y NO son de confianza: usar textContent.
import { analogClock } from "./analog-clock.js";
import { cartwall } from "./cartwall.js";
import { digitalClock } from "./digital-clock.js";
import { fmDial } from "./fm-dial.js";
import { vuMeter } from "./vu-meter.js";

export const COMPONENTS = {
  "vu-meter": vuMeter,
  "analog-clock": analogClock,
  "digital-clock": digitalClock,
  "fm-dial": fmDial,
  cartwall,
};
