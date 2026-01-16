import { getTransform } from "./view_state.js";

let mapData = null;
export const mapBounds = { min_x: 0, min_y: 0, max_x: 0, max_y: 0 };
let db = null;

const BOUNDARY_TYPE = {
  "UNKNOWN": { color: "#ccc", style: "solid" },
  "DOTTED_YELLOW": { color: "rgb(238,191,0)", style: "dotted" },
  "DOTTED_WHITE": { color: "#ffffff", style: "dotted" },
  "SOLID_YELLOW": { color: "rgb(238,191,0)", style: "solid" },
  "SOLID_WHITE": { color: "#ffffff", style: "solid" },
  "DOUBLE_YELLOW": { color: "rgb(238,191,0)", style: "double" },
  "CURB": { color: "#777777", style: "solid" }
};

function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("MapCacheDB", 1);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains("maps")) {
        db.createObjectStore("maps", { keyPath: "map_name" });
      }
    };

    request.onsuccess = (event) => resolve(event.target.result);
    request.onerror = (event) => reject(event.target.error);
  });
}

async function cacheMapToDB(newMapData) {
  if (!db) db = await openDB();
  const tx = db.transaction("maps", "readwrite");
  const store = tx.objectStore("maps");

  await store.put({
    map_name: newMapData.map_name || "unknown",
    timestamp: Date.now(),
    data: newMapData,
  });

  console.log(`[MapCache] Saved map ${newMapData.map_name} to IndexedDB`);
}

export async function loadCachedMap(map_name) {
  if (!db) db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("maps", "readonly");
    const store = tx.objectStore("maps");
    const req = store.get(map_name);

    req.onsuccess = () => {
      if (req.result) {
        console.log(`[MapCache] Loaded ${map_name} from IndexedDB`);
        resolve(req.result.data);
      } else {
        resolve(null);
      }
    };
    req.onerror = () => reject(req.error);
  });
}

export async function clearMapCache() {
  if (!db) db = await openDB();
  const tx = db.transaction("maps", "readwrite");
  tx.objectStore("maps").clear();
  console.log("[MapCache] Cleared all cached maps");
}

export async function updateMap(newMapData) {
  if (!newMapData || !newMapData.lanes) {
    console.warn("[Map] Invalid map data received.");
    return;
  }

  console.log(`[Map] Updating map: ${newMapData.map_name}`);

  mapData = newMapData;
  window.mapData = newMapData;

  let min_x = Infinity, min_y = Infinity, max_x = -Infinity, max_y = -Infinity;
  for (const lane of mapData.lanes) {
    if (!lane.polygon) continue;
    for (const [x, y] of lane.polygon) {
      if (typeof x !== "number" || typeof y !== "number") continue;
      if (x < min_x) min_x = x;
      if (x > max_x) max_x = x;
      if (y < min_y) min_y = y;
      if (y > max_y) max_y = y;
    }
  }

  mapBounds.min_x = min_x;
  mapBounds.min_y = min_y;
  mapBounds.max_x = max_x;
  mapBounds.max_y = max_y;

  try {
    await cacheMapToDB(newMapData);
    localStorage.setItem("lastMapName", newMapData.map_name);
    console.log("[MapCache] Cached:", newMapData.map_name);
  } catch (e) {
    console.warn("[MapCache] Failed to cache map:", e);
  }


  drawMap();
}

export function drawMap() {
  if (!mapData) return;

  const canvas = document.getElementById("mapCanvas");
  const ctx = canvas.getContext("2d");
  const { offsetX, offsetY, scale, rotationAngle } = getTransform();

  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr;
    canvas.height = h * dpr;
  }

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  ctx.save();
  ctx.translate(w / 2 + offsetX, h / 2 + offsetY);
  ctx.rotate(rotationAngle);
  ctx.scale(scale, scale);

  const mapCenterX = (mapBounds.max_x + mapBounds.min_x) / 2;
  const mapCenterY = (mapBounds.max_y + mapBounds.min_y) / 2;
  ctx.translate(-mapCenterX, -mapCenterY);

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high"; 
  // drawAllLanes(ctx, mapData.lanes);
  for (const lane of mapData.lanes) {
    drawLane(ctx, lane);
    drawBoundary(ctx, lane, "left_boundary", lane.left_boundary_type);
    drawBoundary(ctx, lane, "right_boundary", lane.right_boundary_type);
  }

  ctx.restore();
}

function drawLane(ctx, lane) {
  const polygon = lane.polygon;
  if (!polygon || polygon.length === 0) return;

  ctx.save();
  ctx.beginPath();

  for (let i = 0; i < polygon.length; i++) {
    const [x, y] = polygon[i];
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();

  ctx.fillStyle = "#B9B9B9";
  ctx.fill();

  // ctx.strokeStyle = "rgba(100, 100, 100, 0.35)";
  ctx.strokeStyle = "#B9B9B9";
  ctx.lineWidth = 0.4;
  ctx.stroke();

  ctx.restore();
}

function drawBoundary(ctx, lane, key, typeKey) {
  const boundary = lane[key];
  if (!boundary || boundary.length < 2) return;

  if (
    !typeKey ||
    (!typeKey.includes("YELLOW") && !typeKey.includes("WHITE"))
  ) {
    return;
  }

  const style = BOUNDARY_TYPE[typeKey] || BOUNDARY_TYPE.UNKNOWN;
  const { scale } = getTransform();
  const dpr = window.devicePixelRatio || 1;

  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = style.color;

  ctx.lineWidth = 0.4;

  if (style.style === "dotted") {
    const dashLength = 4;
    ctx.setLineDash([dashLength, dashLength]);
  } else {
    ctx.setLineDash([]);
  }

  ctx.beginPath();
  for (let i = 0; i < boundary.length; i++) {
    const [x, y] = boundary[i];
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.restore();
}


export function showMapLoading(text = "Loading map...") {
  const overlay = document.getElementById("loading-bar");
  const txt = overlay.querySelector(".loading-text");
  txt.textContent = text;
  overlay.style.display = "flex";
  updateMapLoading(5);
}

export function updateMapLoading(percent) {
  const bar = document.querySelector(".loading-progress-bar");
  if (bar) bar.style.width = `${Math.min(100, percent)}%`;
}

export function hideMapLoading() {
  const overlay = document.getElementById("loading-bar");
  const bar = overlay.querySelector(".loading-progress-bar");
  if (bar) bar.style.width = "100%";
  setTimeout(() => {
    overlay.style.display = "none";
    if (bar) bar.style.width = "0%";
  }, 300);
}

