// Run only on a disposable local Compose stack. No registration UI is needed.
import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { chromium } from 'playwright-core'

const origin = process.env.PORTAL_ORIGIN ?? 'http://localhost:8080'
const browser = await chromium.launch({ channel: 'chrome', headless: true })
try {
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto(origin + '/cabinet')
  await page.getByRole('button', { name: 'Войти в кабинет' }).waitFor()
  const email = `${randomUUID()}@example.test`
  const password = randomUUID()
  await page.evaluate(
    async ({ email, password }) => {
      async function api(path, method = 'GET', data) {
        const r = await fetch('/api/v1' + path, {
          method,
          headers:
            method === 'GET'
              ? {}
              : {
                  'Content-Type': 'application/json',
                  'X-Portal-Request': '1',
                  'Idempotency-Key': crypto.randomUUID(),
                },
          body: data === undefined ? undefined : JSON.stringify(data),
        })
        if (!r.ok) throw Error(`${method} ${path}: ${r.status}`)
        return r.json()
      }
      async function command(path, method, body) {
        const receipt = await api(path, method, body)
        const op = await api(receipt.status_url.slice('/api/v1'.length))
        if (op.state !== 'succeeded') throw Error('command failed')
        return op.resources
      }
      await api('/auth/guest-sessions', 'POST')
      const survey = await api('/surveys/rheuma_screening_v1')
      const [s] = await command('/screenings', 'POST', {
        survey_id: survey.survey_id,
        weights_version: survey.weights_version,
        disclaimer_version: survey.disclaimer_version,
        disclaimer_accepted: true,
      })
      await command(`/screenings/${s.resource_id}/answers`, 'POST', {
        expected_session_version: 1,
        question_code: 'В1',
        value: true,
      })
      await api('/auth/registrations', 'POST', {
        email,
        password,
        medical_data_consent: { accepted: true, version: 'demo-medical-v1' },
      })
    },
    { email, password },
  )
  // Keep the real HttpOnly refresh cookie but simulate an expired access cookie.
  await context.clearCookies({ name: 'portal_session' })
  await page.reload()
  await page.getByLabel('Имя', { exact: true }).fill('Тестовый пациент')
  await page.getByRole('button', { name: 'Сохранить профиль' }).click()
  await page.getByRole('heading', { name: 'Тестовый пациент' }).waitFor()
  await page.getByText('Добавить препарат', { exact: true }).click()
  await page.getByLabel('Название препарата').fill('Тестовый препарат')
  await page.getByLabel('Дозировка').fill('тест')
  await page.getByLabel('Время приёма').fill('09:00')
  await page.getByLabel('Дата начала').fill('2026-01-01')
  await page.getByRole('button', { name: 'Сохранить препарат' }).click()
  await page.getByText('Тестовый препарат — тест').waitFor()
  await page.getByRole('link', { name: 'Результат 1, версия 1' }).waitFor()
  assert(
    (await context.cookies()).some(
      (c) => c.name === 'portal_session' && c.httpOnly && c.secure,
    ),
  )
  await page.getByRole('button', { name: 'Выйти', exact: true }).click()
  await page.getByLabel('Электронная почта').fill(email)
  await page.getByLabel('Пароль').fill(password)
  await page.getByRole('button', { name: 'Войти в кабинет' }).click()
  await page.getByRole('link', { name: 'Результат 1, версия 1' }).click()
  await page.getByRole('heading', { name: 'Результат анкеты' }).waitFor()
  assert.match(page.url(), /\/results\/[^/]+\/versions\/1$/)
  await page.getByRole('button', { name: 'Получить пояснение' }).click()
  await page.getByText(/Демонстрационный уровень:/).waitFor()
  // The tabs share cookies, not forms. A switch can beat any focus/broadcast handler.
  const other = await context.newPage()
  await other.goto(origin + '/cabinet')
  await page.goto(origin + '/cabinet')
  await page.getByRole('heading', { name: 'Тестовый пациент' }).waitFor()
  await page.getByText('Добавить препарат', { exact: true }).click()
  await page.getByLabel('Название препарата').fill('Старый черновик')
  await page.getByLabel('Дозировка').fill('тест')
  await page.getByLabel('Время приёма').fill('09:00')
  await page.getByLabel('Дата начала').fill('2026-01-01')
  await other.evaluate(async () => {
    const r = await fetch('/api/v1/auth/registrations', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Portal-Request': '1',
        'Idempotency-Key': crypto.randomUUID(),
      },
      body: JSON.stringify({
        email: `${crypto.randomUUID()}@example.test`,
        password: crypto.randomUUID(),
        medical_data_consent: { accepted: true, version: 'demo-medical-v1' },
      }),
    })
    if (r.status !== 201) throw Error(`second registration: ${r.status}`)
  })
  const rejected = page.waitForResponse(
    (r) =>
      r.url().endsWith('/me/medications') && r.request().method() === 'POST',
  )
  await page
    .getByRole('button', { name: 'Сохранить препарат' })
    .evaluate((button) => button.form.requestSubmit())
  const response = await rejected
  assert.equal(response.status(), 409)
  assert.equal((await response.json()).code, 'SESSION_CHANGED')
  await page.getByLabel('Имя', { exact: true }).waitFor()
  assert.equal(await page.getByLabel('Название препарата').inputValue(), '')
  assert.equal(
    await page.evaluate(
      async () => (await (await fetch('/api/v1/me/medications')).json()).total,
    ),
    0,
  )

  // A normal sign-out/in must also invalidate the other tab without submitting or refocusing it.
  await other.reload()
  await other.getByRole('button', { name: 'Выйти', exact: true }).click()
  await page.getByRole('button', { name: 'Войти в кабинет' }).waitFor()
  await other.getByLabel('Электронная почта').fill(email)
  await other.getByLabel('Пароль').fill(password)
  await other.getByRole('button', { name: 'Войти в кабинет' }).click()
  await page.getByRole('heading', { name: 'Тестовый пациент' }).waitFor()
  await page.getByText('Тестовый препарат — тест').waitFor()
  console.log(
    'PASS: patient journey, result explanation and cross-tab cabinet isolation',
  )
} finally {
  await browser.close()
}
