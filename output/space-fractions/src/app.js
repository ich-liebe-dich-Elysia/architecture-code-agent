const express = require("express");
const { createGameRouter } = require("./routes/game");

const app = express();
app.use(express.json());

app.get("/health", (request, response) => {
  response.status(200).json({ status: "ok" });
});

app.use(createGameRouter());

app.use((request, response) => {
  response.status(404).json({ error: "Route not found" });
});

if (require.main === module) {
  const port = process.env.PORT || 3000;
  app.listen(port, () => {
    console.log(`Space Fractions API listening on port ${port}`);
  });
}

module.exports = app;
