let mapName = "-";
let frame = 0;
let gameTime = 0;
let realTime = 0;

export function updateInfo(newMapName, newFrame, newGameTime, newRealTime) {
    // Update global variables with new values
    mapName = newMapName;
    frame = newFrame;
    gameTime = newGameTime;
    realTime = newRealTime;

    drawInfo();
}

export function drawInfo() {
    document.getElementById("map-name").textContent = `Map: ${mapName}`;
    document.getElementById("frame").textContent = `Frame: ${frame}`;
    document.getElementById("game-time").textContent = `Game Time: ${gameTime}`;
    document.getElementById("real-time").textContent = `Real (Server) Time: ${realTime}`;
}
