-- Esquema del predictor estadistico (MVP). SQLite.
-- Idea central: NUCLEO normalizado + stats en formato LARGO para estandarizar
-- 4 deportes (soccer/nba/mlb/nfl) con sets de stats muy distintos, en UN esquema.
-- Agregar 'corners' (soccer) o 'era' (mlb) = filas nuevas con otro `stat`, sin migrar.

CREATE TABLE IF NOT EXISTS teams (
    team_id  INTEGER PRIMARY KEY,
    sport    TEXT NOT NULL,            -- 'nba' | 'mlb' | 'soccer' | 'nfl'
    name     TEXT NOT NULL,
    league   TEXT,                     -- conferencia / liga
    UNIQUE (sport, name)
);

CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY,
    sport     TEXT NOT NULL,
    team_id   INTEGER REFERENCES teams(team_id),
    name      TEXT NOT NULL,
    position  TEXT
);

CREATE TABLE IF NOT EXISTS games (
    game_id      INTEGER PRIMARY KEY,
    sport        TEXT NOT NULL,
    season       TEXT,
    date         TEXT NOT NULL,        -- ISO 'YYYY-MM-DD'
    home_team_id INTEGER REFERENCES teams(team_id),
    away_team_id INTEGER REFERENCES teams(team_id),
    home_score   INTEGER,
    away_score   INTEGER,
    status       TEXT,                 -- 'scheduled' | 'final'
    venue        TEXT
);

-- Stats heterogeneas por partido, en formato LARGO (1 fila por game/team/stat).
-- Pivotear long->wide en pandas (pivot_table) para alimentar el modelo.
CREATE TABLE IF NOT EXISTS team_game_stats (
    game_id INTEGER REFERENCES games(game_id),
    team_id INTEGER REFERENCES teams(team_id),
    stat    TEXT NOT NULL,             -- 'pts','reb','ast','xg','corners','cards','hits','era'...
    value   REAL,
    PRIMARY KEY (game_id, team_id, stat)
);

CREATE TABLE IF NOT EXISTS player_game_stats (
    game_id   INTEGER REFERENCES games(game_id),
    player_id INTEGER REFERENCES players(player_id),
    stat      TEXT NOT NULL,
    value     REAL,
    PRIMARY KEY (game_id, player_id, stat)
);

CREATE TABLE IF NOT EXISTS injuries (
    sport     TEXT NOT NULL,
    team_id   INTEGER REFERENCES teams(team_id),
    player_id INTEGER REFERENCES players(player_id),
    date      TEXT,
    status    TEXT                     -- 'out' | 'questionable' | 'rest'
);

CREATE INDEX IF NOT EXISTS ix_games_date ON games (sport, date);
CREATE INDEX IF NOT EXISTS ix_tgs_team   ON team_game_stats (team_id, stat);
