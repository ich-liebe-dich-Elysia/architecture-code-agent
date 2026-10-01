"""Representative architecture inputs for tests, independent of local task files."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


DOCUMENTATION = """# Architecture
The Space Fractions system is a web-based learning tool.
Chosen architectural style: Microservices

* Language/runtime: Node.js 18-20 (Justification: meets ASR-1)
* Web framework: Express.js 4-5 (Justification: meets NFR-1)
* Persistence: PostgreSQL 14-15 (Justification: meets ASR-1)
* GameComponent: responsible for game logic
* QuestionComponent: responsible for question management
* UserComponent: responsible for authentication

```yml
paths:
  /play:
    get:
      summary: Play the game
```

```sql
CREATE TABLE games (
  id SERIAL PRIMARY KEY,
  game_state JSONB NOT NULL
);
```

| Requirement ID | Short Text | Component |
| --- | --- | --- |
| FR-1 | Play game | GameComponent |
| NFR-1 | Performance | GameComponent |
| ASR-1 | Data durability | QuestionComponent |
"""

VIEWS = """# Architecture Views
```plantuml
@startuml UseCaseDiagram
actor EndUser
actor Admin
usecase "Play Game" as (PlayGame)
usecase "View Score" as (ViewScore)
usecase "Update Questions" as (UpdateQuestions)
usecase "View Help" as (ViewHelp)
@enduml

@startuml ClassDiagram
class Game
class Question
class User
class Admin
Game --* Question
User --* Game
Admin --* Question
@enduml

@startuml ComponentDiagram
artifact GameComponent
artifact QuestionComponent
artifact UserComponent
artifact AdminComponent
GameComponent -- QuestionComponent
@enduml

@startuml StateDiagram
state Playing
state Paused
state GameOver
@enduml

@startuml SequenceDiagram
User->>Game: play()
Game->>Question: getPrompt()
User->>Game: submit answer
Game->>Question: check answer
@enduml
```
"""


@contextmanager
def architecture_documents():
    """Materialize test inputs for the public, file-based parser APIs."""
    with TemporaryDirectory(prefix="architecture-agent-inputs-") as directory:
        root = Path(directory)
        documentation = root / "Architecture_Documentation.md"
        views = root / "Architecture_View.md"
        documentation.write_text(DOCUMENTATION, encoding="utf-8")
        views.write_text(VIEWS, encoding="utf-8")
        yield documentation, views
