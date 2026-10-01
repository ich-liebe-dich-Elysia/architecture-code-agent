const express = require("express");
const {
  getQuestionForGame,
  evaluateAnswer,
} = require("../services/questionService");

function createGameRouter() {
  const router = express.Router();

  router.get("/play", (request, response) => {
    const gameId = 1;
    response.status(200).json({
      gameId,
      status: "started",
      question: getQuestionForGame(gameId),
    });
  });

  router.post("/play/:gameId/answer", (request, response) => {
    const gameId = Number(request.params.gameId);
    const result = evaluateAnswer(gameId, request.body.answer);
    response.status(200).json({ gameId, ...result });
  });

  router.get("/scores/:gameId", (request, response) => {
    response.status(200).json({
      gameId: Number(request.params.gameId),
      score: 0,
    });
  });

  return router;
}

module.exports = { createGameRouter };
