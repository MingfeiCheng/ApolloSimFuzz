import { getTransform } from "./view_state.js";

const trafficLightCanvas = document.getElementById("trafficLightCanvas");
const trafficLightCtx = trafficLightCanvas.getContext("2d");

trafficLightCanvas.width = window.innerWidth;
trafficLightCanvas.height = window.innerHeight;

let trafficLights = null;

const TRAFFIC_LIGHT_TYPE = {
    "green": { color: "rgb(0,175,9)" },
    "red": { color: "rgb(194,0,0)" },
    "yellow": { color: "rgb(255,195,10)" },
    "unknown": { color: "rgb(101,101,101)" }
}

export function updateTrafficLights(newTrafficLights) {
    trafficLights = newTrafficLights;
    drawTrafficLight();
}

export function drawTrafficLight() {
    if (!trafficLights) return;
    
    const { offsetX, offsetY, scale, rotationAngle } = getTransform();
    trafficLightCtx.clearRect(0, 0, trafficLightCanvas.width, trafficLightCanvas.height);
    trafficLightCtx.save();

    trafficLightCtx.translate(offsetX, offsetY);
    trafficLightCtx.scale(scale, scale);
    trafficLightCtx.rotate(rotationAngle);

    trafficLights.forEach(light => {
        const stop_line = light.stop_line;
        const state = light.state;

        trafficLightCtx.strokeStyle = TRAFFIC_LIGHT_TYPE[state].color;
        trafficLightCtx.lineWidth = 0.4;

        trafficLightCtx.beginPath();
        stop_line.forEach(([x, y], i) => {
            const normalizedX = x - min_x;
            const normalizedY = y - min_y;
            if (i === 0) trafficLightCtx.moveTo(normalizedX, normalizedY);
            else trafficLightCtx.lineTo(normalizedX, normalizedY);
        });
        trafficLightCtx.stroke();
    });

    trafficLightCtx.restore();
}
