"use strict";

const http = require("node:http");
const { spawn } = require("node:child_process");

function openBrowser(url) {
  if (process.env.NO_BROWSER === "1") return;
  let command;
  let args;
  if (process.platform === "win32") {
    command = "rundll32.exe";
    args = ["url.dll,FileProtocolHandler", url];
  } else if (process.platform === "darwin") {
    command = "open";
    args = [url];
  } else {
    command = "xdg-open";
    args = [url];
  }
  const browser = spawn(command, args, {
    detached: true, stdio: "ignore", windowsHide: true, shell: false,
  });
  browser.on("error", () => console.error("Open this address in your browser: " + url));
  browser.unref();
}

function launch() {
  const portText = (process.env.PORT || "3000").trim();
  const requestedPort = Number(portText);
  if (!/^\d+$/.test(portText) || !Number.isInteger(requestedPort) || requestedPort < 0 || requestedPort > 65535) {
    throw new Error("PORT must be a whole number from 0 to 65535.");
  }
  const { createApp } = require("./src/app.js");
  if (typeof createApp !== "function") throw new Error("src/app.js must export createApp().");
  const app = createApp();
  let activeServer;
  function listen(port, retried) {
    const server = http.createServer(app);
    activeServer = server;
    server.once("error", (error) => {
      if (error.code === "EADDRINUSE" && !retried && port !== 0) {
        console.log("Port " + port + " is occupied; choosing an available local port.");
        listen(0, true);
        return;
      }
      console.error("Cannot start game server: " + error.message);
      process.exitCode = 1;
    });
    server.listen(port, "127.0.0.1", () => {
      const url = "http://127.0.0.1:" + server.address().port;
      console.log("Game ready: " + url);
      console.log("Keep this window open while playing. Press Ctrl+C to stop.");
      openBrowser(url);
    });
  }
  listen(requestedPort, false);
  process.once("SIGINT", () => {
    if (activeServer) activeServer.close(() => process.exit(0));
  });
}

try {
  launch();
} catch (error) {
  console.error("Cannot start game: " + error.message);
  console.error("Check Node.js, run npm install in this directory, and try again.");
  process.exitCode = 1;
}
