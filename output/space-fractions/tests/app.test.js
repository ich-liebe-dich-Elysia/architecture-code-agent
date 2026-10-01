const assert = require("node:assert/strict");
const test = require("node:test");
const app = require("../src/app");

async function requestApplication(path) {
  const server = app.listen(0, "127.0.0.1");
  await new Promise((resolve) => server.once("listening", resolve));

  try {
    const { port } = server.address();
    return await fetch(`http://127.0.0.1:${port}${path}`);
  } finally {
    await new Promise((resolve, reject) => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
  }
}

test("GET /health reports a healthy service", async () => {
  const response = await requestApplication("/health");
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok" });
});

test("GET /play starts a game and returns a fraction question", async () => {
  const response = await requestApplication("/play");
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.gameId, 1);
  assert.ok(body.question.prompt);
});
