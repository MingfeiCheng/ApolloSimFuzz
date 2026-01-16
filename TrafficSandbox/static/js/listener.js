import { getTransform, setTransform, minScale, maxScale, rotationStep } from "./view_state.js";
import { drawMap } from "./map.js";

let isDragging = false;
let isRotating = false;
let startX = 0, startY = 0;
let rafToken = 0;

function requestRedraw() {
  cancelAnimationFrame(rafToken);
  rafToken = requestAnimationFrame(drawMap);
}

export function addCanvasListeners(canvas) {
  const initial = getTransform();

  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();

    const { offsetX, offsetY, scale } = getTransform();
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const dynamicStep = scale * 0.05;
    const newScale = e.deltaY < 0
      ? Math.min(scale + dynamicStep, maxScale)
      : Math.max(scale - dynamicStep, minScale);

    const ratio = newScale / scale;

    const newOffsetX = mouseX - ratio * (mouseX - offsetX);
    const newOffsetY = mouseY - ratio * (mouseY - offsetY);

    setTransform({ x: newOffsetX, y: newOffsetY, s: newScale });
    requestRedraw();
  }, { passive: false });

  canvas.addEventListener("contextmenu", e => e.preventDefault());

  canvas.addEventListener("mousedown", (e) => {
    e.preventDefault();
    const t = getTransform();

    if (e.button === 0) { 
      isDragging = true;
      startX = e.clientX - t.offsetX;
      startY = e.clientY - t.offsetY;
    } else if (e.button === 2) { 
      isRotating = true;
      startX = e.clientX;
      startY = e.clientY;
    }
  });

  canvas.addEventListener("mousemove", (e) => {
    const t = getTransform();

    if (isDragging) {
      const newX = e.clientX - startX;
      const newY = e.clientY - startY;
      setTransform({ x: newX, y: newY });
      requestRedraw();
    } else if (isRotating) {
      const dx = e.clientX - startX;
      const newAngle = t.rotationAngle - dx * rotationStep;
      setTransform({ r: newAngle });
      startX = e.clientX;
      startY = e.clientY;
      requestRedraw();
    }
  });

  ["mouseup", "mouseleave"].forEach(evt => {
    canvas.addEventListener(evt, () => {
      isDragging = false;
      isRotating = false;
    });
  });

  const resetBtn = document.getElementById("resetViewButton");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      setTransform({
        x: initial.offsetX,
        y: initial.offsetY,
        s: initial.scale,
        r: initial.rotationAngle,
      });
      requestRedraw();
    });
  }
}
