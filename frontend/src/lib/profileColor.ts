// Dark enough for white letters (≥ 4.5:1), different enough to tell apart.
const COLORS = [
  "#0a6fdc",
  "#c9281d",
  "#1d7a34",
  "#9a5000",
  "#7c3aed",
  "#0e7490",
  "#be185d",
  "#4b5563",
];

export function profileColor(id: number): string {
  return COLORS[id % COLORS.length] ?? "#4b5563";
}
