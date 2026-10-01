const { questions } = require("../data/questions");

function getQuestionForGame(gameId) {
  const question = questions[(gameId - 1) % questions.length];
  return {
    id: question.id,
    prompt: question.prompt,
    options: question.options,
  };
}

function evaluateAnswer(gameId, answer) {
  const question = questions[(gameId - 1) % questions.length];
  return {
    correct: answer === question.answer,
    correctAnswer: question.answer,
  };
}

module.exports = { getQuestionForGame, evaluateAnswer };
