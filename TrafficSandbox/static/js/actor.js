import { getTransform } from "./view_state.js";

const actorCanvas = document.getElementById("actorCanvas");
const actorCtx = actorCanvas.getContext("2d");

// Get the container's width and height
const container = document.querySelector('.simulator-container');
const containerWidth = container.clientWidth;
const containerHeight = container.clientHeight;

// Set the canvas dimensions to match the container
actorCanvas.width = containerWidth;
actorCanvas.height = containerHeight;

let actors = null;

const ACTOR_TYPE = {
    "vehicle": { color: "rgb(79,108,243)" },
    "walker": { color: "rgb(245,177,8)" },
    "static": { color: "rgb(184,29,227)" },
    "bicycle": { color: "rgb(0,175,149)" },
};

const ROLE_TYPE = {
    "ads": { color: "rgb(245,82,82)" }
};


export function updateActors(newActors) {
    actors = newActors;
    drawActor();
}

export function drawActor() {
    if (!window.actors || actors.length === 0) return;
    
    const { offsetX, offsetY, scale, rotationAngle } = getTransform();

    actorCtx.clearRect(0, 0, actorCanvas.width, actorCanvas.height);
    actorCtx.save();

    actorCtx.translate(offsetX, offsetY);
    actorCtx.scale(scale, scale);
    actorCtx.rotate(rotationAngle);

    const fillGroups = new Map(); // color → list of polygons
    const textData = [];          

    for (let i = 0; i < actors.length; i++) {
        const actor = actors[i];
        const polygon = actor.polygon;
        if (!polygon || polygon.length < 3) continue; 

        const actorStyle = actor.role === "ads"
            ? ROLE_TYPE[actor.role]
            : ACTOR_TYPE[actor.category.split(".")[0]] || { color: "gray" };

        const normalized = [];
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (let j = 0; j < polygon.length; j++) {
            const [x, y] = polygon[j];
            const nx = x - min_x;
            const ny = y - min_y;
            normalized.push([nx, ny]);
            if (nx < minX) minX = nx;
            if (ny < minY) minY = ny;
            if (nx > maxX) maxX = nx;
            if (ny > maxY) maxY = ny;
        }

        if (!fillGroups.has(actorStyle.color)) {
            fillGroups.set(actorStyle.color, []);
        }
        fillGroups.get(actorStyle.color).push(normalized);

        const cx = (minX + maxX) / 2;
        const cy = (minY + maxY) / 2;
        textData.push({
            id: actor.id,
            speed: parseFloat(actor.speed).toFixed(2),
            cx,
            cy
        });
    }

    actorCtx.lineWidth = 0.03;
    actorCtx.strokeStyle = "black";
    actorCtx.setLineDash([]);

    for (const [color, polys] of fillGroups.entries()) {
        actorCtx.fillStyle = color;
        for (let i = 0; i < polys.length; i++) {
            const poly = polys[i];
            actorCtx.beginPath();
            actorCtx.moveTo(poly[0][0], poly[0][1]);
            for (let j = 1; j < poly.length; j++) {
                actorCtx.lineTo(poly[j][0], poly[j][1]);
            }
            actorCtx.closePath();
            actorCtx.fill();
            actorCtx.stroke();
        }
    }

    actorCtx.font = `0.6px Arial`;
    actorCtx.textAlign = "center";
    actorCtx.textBaseline = "middle";
    actorCtx.fillStyle = "black";

    for (let i = 0; i < textData.length; i++) {
        const { id, speed, cx, cy } = textData[i];
        actorCtx.fillText(`${id}`, cx, cy - 0.3);
        actorCtx.fillText(`${speed} m/s`, cx, cy + 0.3);
    }

    actorCtx.restore();
}

