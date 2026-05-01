const json = (data, init = {}) =>
  new Response(JSON.stringify(data, null, 2), {
    ...init,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'access-control-allow-origin': '*',
      ...(init.headers || {}),
    },
  })

const notFound = () => json({ ok: false, error: 'Not found' }, { status: 404 })

async function handleHealth(env) {
  let d1Ok = false
  try {
    const result = await env.DB.prepare('SELECT 1 AS ok').first()
    d1Ok = Number(result?.ok) === 1
  } catch {
    d1Ok = false
  }

  return json({
    ok: true,
    app: 'iit-jee-question-bank-api',
    env: env.APP_ENV || 'development',
    services: {
      d1: d1Ok ? 'connected' : 'not-ready',
      r2: env.ASSETS_BUCKET ? 'bound' : 'not-bound',
    },
  })
}

async function handleSubjects(env) {
  const rows = await env.DB.prepare(
    'SELECT id, name FROM subjects ORDER BY name'
  ).all()
  return json({ ok: true, subjects: rows.results || [] })
}

async function handleQuestions(env, url) {
  const subject = url.searchParams.get('subject') || ''
  const limit = Math.min(Number(url.searchParams.get('limit') || 50), 200)
  const offset = Math.max(Number(url.searchParams.get('offset') || 0), 0)

  if (subject) {
    const rows = await env.DB.prepare(`
      SELECT q.id, q.question_number, q.page_range, q.magazine, q.edition,
             q.question_set_name, q.chapter, q.high_level_chapter, q.question_text
      FROM questions q
      JOIN subjects s ON s.id = q.subject_id
      WHERE lower(s.name) = lower(?1)
      ORDER BY q.id DESC
      LIMIT ?2 OFFSET ?3
    `).bind(subject, limit, offset).all()
    return json({ ok: true, questions: rows.results || [], limit, offset })
  }

  const rows = await env.DB.prepare(`
    SELECT id, question_number, page_range, magazine, edition,
           question_set_name, chapter, high_level_chapter, question_text
    FROM questions
    ORDER BY id DESC
    LIMIT ?1 OFFSET ?2
  `).bind(limit, offset).all()
  return json({ ok: true, questions: rows.results || [], limit, offset })
}

async function handleDashboard(env, url) {
  const subject = url.searchParams.get('subject') || ''
  const subjectRow = subject
    ? await env.DB.prepare('SELECT id, name FROM subjects WHERE lower(name) = lower(?1)').bind(subject).first()
    : null

  const where = subjectRow ? 'WHERE subject_id = ?1' : ''
  const bindValues = subjectRow ? [subjectRow.id] : []

  const totalQuestions = await env.DB.prepare(`SELECT COUNT(*) AS count FROM questions ${where}`).bind(...bindValues).first()
  const totalChapters = await env.DB.prepare(`SELECT COUNT(DISTINCT high_level_chapter) AS count FROM questions ${where}`).bind(...bindValues).first()
  const uniqueMagazines = await env.DB.prepare(`SELECT COUNT(DISTINCT normalized_magazine) AS count FROM questions ${where}`).bind(...bindValues).first()

  return json({
    ok: true,
    stats: {
      totalQuestions: Number(totalQuestions?.count || 0),
      totalChapters: Number(totalChapters?.count || 0),
      uniqueMagazines: Number(uniqueMagazines?.count || 0),
    },
    generatedAt: new Date().toISOString(),
  })
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url)

    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          'access-control-allow-origin': '*',
          'access-control-allow-methods': 'GET,POST,PUT,DELETE,OPTIONS',
          'access-control-allow-headers': 'content-type,authorization',
        },
      })
    }

    try {
      if (url.pathname === '/api/health') return handleHealth(env)
      if (url.pathname === '/api/subjects') return handleSubjects(env)
      if (url.pathname === '/api/questions') return handleQuestions(env, url)
      if (url.pathname === '/api/dashboard') return handleDashboard(env, url)
      return notFound()
    } catch (error) {
      return json({ ok: false, error: error.message || String(error) }, { status: 500 })
    }
  },
}
