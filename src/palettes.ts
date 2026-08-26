export type PaletteName =
  | "emerald"
  | "navy"
  | "purple"
  | "teal"
  | "indigo"
  | "plum"
  | "forest"
  | "slate";

export type Palette = {
  name: PaletteName;
  background: string;
  prayerBackground: string;
  accent: string;
  hairline: string;
  canvas: string;
};

export const PALETTES: Record<PaletteName, Palette> = {
  emerald: {
    name: "emerald",
    background: "radial-gradient(120% 75% at 50% 0%, rgba(52,211,153,0.52) 0%, rgba(6,78,59,0.12) 48%, rgba(2,20,18,0) 76%), linear-gradient(180deg, #064E3B 0%, #022C22 52%, #031713 100%)",
    prayerBackground: "radial-gradient(110% 75% at 50% 8%, rgba(110,231,183,0.38) 0%, rgba(6,78,59,0.08) 58%, rgba(2,20,18,0) 82%), linear-gradient(180deg, #064E3B 0%, #022C22 52%, #031713 100%)",
    accent: "#A7F3D0",
    hairline: "rgba(167,243,208,0.34)",
    canvas: "#031713",
  },
  navy: {
    name: "navy",
    background: "radial-gradient(120% 75% at 50% 0%, rgba(96,165,250,0.46) 0%, rgba(30,58,138,0.18) 50%, rgba(5,15,35,0) 78%), linear-gradient(180deg, #172554 0%, #0F1B3D 52%, #050F23 100%)",
    prayerBackground: "radial-gradient(110% 75% at 50% 8%, rgba(147,197,253,0.34) 0%, rgba(30,58,138,0.1) 58%, rgba(5,15,35,0) 82%), linear-gradient(180deg, #172554 0%, #0F1B3D 52%, #050F23 100%)",
    accent: "#BFDBFE",
    hairline: "rgba(191,219,254,0.34)",
    canvas: "#050F23",
  },
  purple: {
    name: "purple",
    background: "radial-gradient(120% 75% at 50% 0%, rgba(192,132,252,0.52) 0%, rgba(88,28,135,0.18) 50%, rgba(24,8,44,0) 78%), linear-gradient(180deg, #581C87 0%, #321052 54%, #170925 100%)",
    prayerBackground: "radial-gradient(110% 75% at 50% 8%, rgba(216,180,254,0.4) 0%, rgba(88,28,135,0.1) 58%, rgba(24,8,44,0) 82%), linear-gradient(180deg, #581C87 0%, #321052 54%, #170925 100%)",
    accent: "#E9D5FF",
    hairline: "rgba(233,213,255,0.34)",
    canvas: "#170925",
  },
  teal: {
    name: "teal",
    background: "radial-gradient(120% 75% at 50% 0%, rgba(45,212,191,0.5) 0%, rgba(17,94,89,0.18) 50%, rgba(3,25,28,0) 78%), linear-gradient(180deg, #115E59 0%, #0B3F42 54%, #03191C 100%)",
    prayerBackground: "radial-gradient(110% 75% at 50% 8%, rgba(94,234,212,0.38) 0%, rgba(17,94,89,0.1) 58%, rgba(3,25,28,0) 82%), linear-gradient(180deg, #115E59 0%, #0B3F42 54%, #03191C 100%)",
    accent: "#99F6E4",
    hairline: "rgba(153,246,228,0.34)",
    canvas: "#03191C",
  },
  indigo: {
    name: "indigo",
    background: "radial-gradient(120% 75% at 50% 0%, rgba(129,140,248,0.5) 0%, rgba(49,46,129,0.18) 50%, rgba(12,12,40,0) 78%), linear-gradient(180deg, #312E81 0%, #1E1B5B 54%, #0C0C28 100%)",
    prayerBackground: "radial-gradient(110% 75% at 50% 8%, rgba(165,180,252,0.38) 0%, rgba(49,46,129,0.1) 58%, rgba(12,12,40,0) 82%), linear-gradient(180deg, #312E81 0%, #1E1B5B 54%, #0C0C28 100%)",
    accent: "#C7D2FE",
    hairline: "rgba(199,210,254,0.34)",
    canvas: "#0C0C28",
  },
  plum: {
    name: "plum",
    background: "radial-gradient(120% 75% at 50% 0%, rgba(244,114,182,0.42) 0%, rgba(157,23,77,0.2) 50%, rgba(40,8,28,0) 78%), linear-gradient(180deg, #831843 0%, #4A1231 54%, #28081C 100%)",
    prayerBackground: "radial-gradient(110% 75% at 50% 8%, rgba(249,168,212,0.34) 0%, rgba(157,23,77,0.1) 58%, rgba(40,8,28,0) 82%), linear-gradient(180deg, #831843 0%, #4A1231 54%, #28081C 100%)",
    accent: "#FBCFE8",
    hairline: "rgba(251,207,232,0.34)",
    canvas: "#28081C",
  },
  forest: {
    name: "forest",
    background: "radial-gradient(120% 75% at 50% 0%, rgba(163,230,53,0.36) 0%, rgba(54,83,20,0.2) 50%, rgba(13,28,8,0) 78%), linear-gradient(180deg, #365314 0%, #1E360F 54%, #0D1C08 100%)",
    prayerBackground: "radial-gradient(110% 75% at 50% 8%, rgba(190,242,100,0.3) 0%, rgba(54,83,20,0.1) 58%, rgba(13,28,8,0) 82%), linear-gradient(180deg, #365314 0%, #1E360F 54%, #0D1C08 100%)",
    accent: "#D9F99D",
    hairline: "rgba(217,249,157,0.34)",
    canvas: "#0D1C08",
  },
  slate: {
    name: "slate",
    background: "radial-gradient(120% 75% at 50% 0%, rgba(148,163,184,0.42) 0%, rgba(51,65,85,0.24) 50%, rgba(10,16,26,0) 78%), linear-gradient(180deg, #334155 0%, #1E293B 54%, #0A101A 100%)",
    prayerBackground: "radial-gradient(110% 75% at 50% 8%, rgba(203,213,225,0.3) 0%, rgba(51,65,85,0.12) 58%, rgba(10,16,26,0) 82%), linear-gradient(180deg, #334155 0%, #1E293B 54%, #0A101A 100%)",
    accent: "#E2E8F0",
    hairline: "rgba(226,232,240,0.32)",
    canvas: "#0A101A",
  },
};

export const PALETTE_ORDER: PaletteName[] = [
  "emerald",
  "navy",
  "purple",
  "teal",
  "indigo",
  "plum",
  "forest",
  "slate",
];

export function resolvePalette(name?: string): Palette {
  if (name && name in PALETTES) {
    return PALETTES[name as PaletteName];
  }
  return PALETTES.navy;
}
