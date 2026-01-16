import { loadCachedMap, updateMap, drawMap, showMapLoading, updateMapLoading, hideMapLoading } from "./map.js";
import { updateTrafficLights } from './traffic_light.js';
import { updateActors } from './actor.js';
import { updateInfo } from './info.js';
import { addCanvasListeners } from "./listener.js";

window.addEventListener("DOMContentLoaded", async () => {
  try {
    console.log("[Cache] Checking IndexedDB for cached map...");

    const lastMapName = localStorage.getItem("lastMapName") || "borregas_ave";
    const cached = await loadCachedMap(lastMapName);

    if (cached) {
      console.log(`[Cache] Restoring cached map: ${lastMapName}`);
      showMapLoading("Restoring cached map...");
      updateMapLoading(20);

      await updateMap(cached);
      drawMap();

      updateMapLoading(100);
      setTimeout(() => hideMapLoading(), 300);
    } else {
      console.log("[Cache] No cached map found in IndexedDB.");
    }
  } catch (e) {
    console.warn("[Cache] Failed to restore cached map:", e);
    hideMapLoading();
  }
});

const socket = io();

socket.on("connect", () => {
  console.log("[Socket] Connected to backend");
});

socket.on("disconnect", () => {
  console.log("[Socket] Disconnected");
});

// functions
const mapCanvas = document.getElementById("mapCanvas");
const actorCanvas = document.getElementById("actorCanvas");
const trafficLightCanvas = document.getElementById("trafficLightCanvas");

window.latestTrafficData = null;


socket.on("map_loading_start", (data) => {
  console.log(`[Socket] Map loading start: ${data.map_name}`);
  showMapLoading(`Loading map: ${data.map_name}`);
  updateMapLoading(5);
});

socket.on("init_map", async (mapData) => {
  console.log("[Socket] Received new map data:", mapData.map_name);
  updateMapLoading(60);
  await updateMap(mapData);
  updateMapLoading(90);
  drawMap();
});

socket.on("map_loading_done", () => {
  updateMapLoading(100);
  setTimeout(hideMapLoading, 300);
});

socket.on("map_loading_error", (err) => {
  console.error("[Socket] Map loading failed:", err);
  showMapLoading("❌ Failed to load map");
  setTimeout(hideMapLoading, 1000);
});


socket.on("traffic_update", (trafficData) => {
  // console.log("[Socket] Received traffic update:", trafficData);
  window.latestTrafficData = trafficData;
  updateFrame();
});

// update
export function updateFrame(trafficData) {

  trafficData = window.latestTrafficData;
  if (!trafficData) return;
  
  // drawMap();
  updateInfo(
    trafficData.map_name, 
    trafficData.frame, 
    trafficData.game_time, 
    trafficData.real_time
  );
  updateTrafficLights(trafficData.traffic_lights);
  updateActors(trafficData.actors);
}

addCanvasListeners(mapCanvas, () => updateFrame(window.latestTrafficData));
actorCanvas.style.pointerEvents = "none";
trafficLightCanvas.style.pointerEvents = "none";