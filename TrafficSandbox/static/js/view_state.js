// =========================
// view_state.js
// =========================
import { mapBounds } from "./map.js";

export const minScale = 1;
export const maxScale = 50;
export const rotationStep = 0.002;

let offsetX = 0;
let offsetY = 0;
let scale = 1;
let rotationAngle = 0;

export function getTransform() {
  return { offsetX, offsetY, scale, rotationAngle };
}

export function setTransform({ x, y, s, r }) {
  if (s !== undefined) scale = Math.min(Math.max(s, minScale), maxScale);
  if (r !== undefined) rotationAngle = r;
  if (x !== undefined) offsetX = x;
  if (y !== undefined) offsetY = y;

  if (!mapBounds || !mapBounds.max_x) return;

  const mapWidth = mapBounds.max_x - mapBounds.min_x;
  const mapHeight = mapBounds.max_y - mapBounds.min_y;

  const container = document.querySelector(".simulator-container");
  if (!container) return;

  const viewWidth = container.clientWidth;
  const viewHeight = container.clientHeight;

  const mapScaledWidth = mapWidth * scale;
  const mapScaledHeight = mapHeight * scale;

  const limitX = Math.max(0, mapScaledWidth / 2 - viewWidth / 2);
  const limitY = Math.max(0, mapScaledHeight / 2 - viewHeight / 2);

  offsetX = Math.min(Math.max(offsetX, -limitX), limitX);
  offsetY = Math.min(Math.max(offsetY, -limitY), limitY);
}
