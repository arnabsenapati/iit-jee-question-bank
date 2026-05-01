# Cloudflare setup

This repository is the Cloudflare-native migration target for the IIT JEE Question Bank app.

## 1. Cloudflare Pages

Create a Pages project from GitHub.

- Repository: `arnabsenapati/iit-jee-question-bank`
- Branch: `main`
- Root directory: `web`
- Build command: `npm run build`
- Build output directory: `dist`

## 2. Cloudflare D1

Create a D1 database named:

```txt
iit-jee-question-bank
```

Apply migration:

```bash
npx wrangler d1 migrations apply iit-jee-question-bank
```

Then update `wrangler.toml` with the generated D1 `database_id`.

## 3. Cloudflare R2

Create an R2 bucket named:

```txt
iit-jee-question-bank-assets
```

This bucket is intended for:

- question images
- answer images
- uploaded TSV files
- generated exports
- snapshots/backups

## 4. Worker API

The Worker entry point is:

```txt
workers/src/index.js
```

Initial routes:

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/subjects`
- `GET /api/questions`

## 5. Local development

Run the Worker locally:

```bash
npx wrangler dev
```

Run the frontend locally from `web/`:

```bash
npm install
npm run dev
```

The Vite dev proxy sends `/api` requests to the Worker dev server on `127.0.0.1:8787`.

## 6. Important migration note

The original SQLite DB is about 180 MB. Importing it into D1 should be done through an exported SQL file, not by committing the `.db` file into GitHub.

Do not commit secrets, API tokens, database dumps, or production backups into this repository.
