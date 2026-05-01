PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS subjects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id INTEGER NOT NULL,
  source TEXT,
  magazine TEXT,
  normalized_magazine TEXT,
  edition TEXT,
  issue_year INTEGER,
  issue_month INTEGER,
  page_range TEXT,
  question_set TEXT,
  question_set_name TEXT,
  chapter TEXT,
  high_level_chapter TEXT,
  question_number TEXT,
  question_text TEXT,
  answer_text TEXT,
  explanation TEXT,
  metadata_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_questions_subject_id ON questions(subject_id);
CREATE INDEX IF NOT EXISTS idx_questions_normalized_magazine ON questions(normalized_magazine);
CREATE INDEX IF NOT EXISTS idx_questions_high_level_chapter ON questions(high_level_chapter);
CREATE INDEX IF NOT EXISTS idx_questions_question_set_name ON questions(question_set_name);
CREATE INDEX IF NOT EXISTS idx_questions_qno_page_mag ON questions(subject_id, normalized_magazine, question_number, page_range);

CREATE TABLE IF NOT EXISTS question_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'question',
  mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
  r2_key TEXT NOT NULL,
  size_bytes INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_question_images_question_id ON question_images(question_id);

CREATE TABLE IF NOT EXISTS configs (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  color TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS question_tags (
  question_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (question_id, tag_id),
  FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS question_lists (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  metadata_json TEXT,
  archived INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS question_list_items (
  list_id INTEGER NOT NULL,
  question_id INTEGER NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (list_id, question_id),
  FOREIGN KEY (list_id) REFERENCES question_lists(id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_question_list_items_list_position ON question_list_items(list_id, position);

CREATE TABLE IF NOT EXISTS imports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_name TEXT,
  subject_id INTEGER,
  rows_total INTEGER DEFAULT 0,
  rows_inserted INTEGER DEFAULT 0,
  rows_skipped INTEGER DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'created',
  message TEXT,
  r2_key TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS exams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  list_name TEXT,
  imported_at TEXT,
  evaluated INTEGER DEFAULT 0,
  evaluated_at TEXT,
  total_questions INTEGER,
  answered INTEGER,
  correct INTEGER,
  wrong INTEGER,
  score INTEGER,
  percent REAL,
  source_path TEXT,
  payload_json TEXT
);

CREATE TABLE IF NOT EXISTS exam_questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exam_id INTEGER NOT NULL,
  q_index INTEGER,
  question_json TEXT,
  response_json TEXT,
  correct INTEGER,
  answered INTEGER,
  score INTEGER,
  eval_status TEXT,
  eval_comment TEXT,
  FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS question_embeddings (
  question_id INTEGER PRIMARY KEY,
  model TEXT NOT NULL,
  dim INTEGER NOT NULL,
  vector_r2_key TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

INSERT OR IGNORE INTO subjects(name) VALUES ('Physics'), ('Chemistry'), ('Mathematics');
