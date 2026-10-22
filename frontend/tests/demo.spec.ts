import { expect, test, type Page, type TestInfo } from '@playwright/test'

const mockReply = {
  run_id: '00000000-0000-4000-8000-000000000001',
  answer: 'Mock reply: I will remember the name Ada for this conversation.',
  mode: 'mock',
  final_model: 'mock-v1',
  status: 'unverified',
  analysis: null,
  route_decisions: [],
  attempts: [{ model_key: 'mock-v1', model_id: 'mock-v1', latency_ms: 12, error_category: null, finish_reason: 'stop' }],
  total_latency_ms: 18,
  total_cost_usd: '0',
  known_cost_usd: '0',
  reserved_cost_usd: '0',
  cost_complete: true,
  escalation_reason: null,
  warnings: ['Offline browser fixture; no provider calls or research evidence.'],
}

async function screenshot(page: Page, testInfo: TestInfo, view: string) {
  if (process.env.CAPTURE_SCREENSHOTS === '1') {
    await page.screenshot({ path: `../docs/screenshots/phase-${process.env.SCREENSHOT_PHASE ?? '06'}-${view}-${testInfo.project.name}.png`, fullPage: true })
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
}

test.beforeEach(async ({ page }) => {
  // Block every API request by default so a missing fixture cannot reach a paid backend.
  await page.route('**/api/**', route => route.fulfill({ status: 503, json: { code: 'unmocked_test_request' } }))
  await page.route('**/api/config', route => route.fulfill({ json: { mode: 'mock', model_key: null, providers: [] } }))
})

test('keyboard chat preserves context, blocks duplicate sends, and clears on new chat', async ({ page }, testInfo) => {
  const requests: unknown[] = []
  let release: () => void = () => {}
  const heldReply = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/chat', async route => {
    requests.push(route.request().postDataJSON())
    if (requests.length === 1) await heldReply
    await route.fulfill({ json: { ...mockReply, answer: requests.length === 1 ? mockReply.answer : 'Mock reply: Your name is Ada.' } })
  })
  await page.goto('/')
  const composer = page.getByRole('textbox', { name: 'Your message' })
  const send = page.getByRole('button', { name: 'Send', exact: true })
  await expect(send).toBeDisabled()
  await composer.fill('My name is Ada.')
  await expect(send).toBeEnabled()
  await composer.press('Enter')
  await expect(page.getByRole('button', { name: 'Sending…' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'New chat' })).toBeDisabled()
  await composer.press('Enter')
  expect(requests).toHaveLength(1)
  release()
  await expect(page.getByText(mockReply.answer, { exact: true })).toBeVisible()
  await expect(composer).toBeFocused()
  const details = page.locator('summary').first()
  await details.focus()
  await details.press('Enter')
  await expect(page.getByText('Not analyzed (mock)', { exact: true })).toBeVisible()
  await expect(page.getByText('No API charge', { exact: false })).toBeVisible()
  await screenshot(page, testInfo, 'chat')
  await composer.fill('What is my name?')
  await composer.press('Enter')
  await expect(page.getByText('Mock reply: Your name is Ada.', { exact: true })).toBeVisible()
  expect(requests[1]).toEqual({ messages: [
    { role: 'user', content: 'My name is Ada.' },
    { role: 'assistant', content: mockReply.answer },
    { role: 'user', content: 'What is my name?' },
  ] })
  const newChat = page.getByRole('button', { name: 'New chat' })
  await newChat.focus()
  await newChat.press('Enter')
  await expect(page.getByRole('heading', { name: 'What can I help with?' })).toBeVisible()
  await expect(page.getByText(mockReply.answer, { exact: true })).toHaveCount(0)
  await expect(composer).toBeFocused()
  await composer.press('Shift+Enter')
  await expect(composer).toHaveValue('\n')
  expect(requests).toHaveLength(2)
})

test('invalid input and failed requests preserve a draft for an explicit retry', async ({ page }, testInfo) => {
  let requestCount = 0
  await page.route('**/api/chat', route => {
    requestCount++
    return requestCount === 1
      ? route.fulfill({ status: 503, json: { code: 'provider_unavailable', message: 'Unavailable' } })
      : route.fulfill({ json: { ...mockReply,
        mode: 'live', answer: 'Offline replay: The answer is 42.', final_model: 'strong-fixture',
        analysis: { task: 'reasoning', difficulty: 'hard', reasoning: 'high', confidence: null, source: 'fallback' },
        total_cost_usd: null, known_cost_usd: '0.002', reserved_cost_usd: '0.25', cost_complete: false,
        total_latency_ms: 3200, escalation_reason: 'First generation timed out.',
        attempts: [
          { model_key: 'cheap-fixture', model_id: 'gemini-3.5-flash-lite', latency_ms: 2000, error_category: 'timeout', finish_reason: 'error' },
          { model_key: 'strong-fixture', model_id: 'claude-sonnet-5-5', latency_ms: 900, error_category: null, finish_reason: 'stop' },
        ],
        route_decisions: [{ selected_key: 'strong-fixture', reason: 'Available stronger candidate within the remaining ceiling.' }],
      } })
  })
  await page.goto('/')
  const composer = page.getByRole('textbox', { name: 'Your message' })
  await composer.fill(' '.repeat(3))
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeDisabled()
  await composer.fill('x'.repeat(12001))
  await expect(page.getByText('Conversation limit reached.', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeDisabled()
  expect(requestCount).toBe(0)
  await composer.fill('What is 6 multiplied by 7?')
  await composer.press('Enter')
  await expect(page.getByRole('alert')).toContainText('Could not send your message')
  await expect(composer).toHaveValue('What is 6 multiplied by 7?')
  await screenshot(page, testInfo, 'error')
  await composer.press('Enter')
  await expect(page.getByText('Offline replay: The answer is 42.', { exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByText('Unverified · claude-sonnet-5-5 · 3.20 s', { exact: false })).toBeVisible()
  await page.locator('summary').click()
  await expect(page.getByText('reasoning / hard', { exact: true })).toBeVisible()
  await expect(page.getByText('Incomplete · known $0.002', { exact: true })).toBeVisible()
  await expect(page.getByText('$0.25', { exact: true })).toBeVisible()
  await expect(page.getByText('gemini-3.5-flash-lite', { exact: true })).toBeVisible()
  await expect(page.getByText('claude-sonnet-5-5', { exact: true })).toBeVisible()
  await expect(page.getByText('Attempt 1: gemini-3.5-flash-lite', { exact: false })).toBeVisible()
  await expect(page.getByText('Attempt 2: claude-sonnet-5-5', { exact: false })).toBeVisible()
  await screenshot(page, testInfo, 'details')
  expect(requestCount).toBe(2)
})

test('results show persisted summaries, empty states, and explicit refresh failures', async ({ page }, testInfo) => {
  let state: 'empty' | 'populated' | 'error' = 'empty'
  let reads = 0
  await page.route('**/api/runs?limit=20', route => {
    reads++
    if (state === 'error') return route.fulfill({ status: 503, json: { code: 'database_unavailable' } })
    return route.fulfill({ json: state === 'empty' ? [] : [{
      id: mockReply.run_id, created_at: '2026-10-21T14:00:00Z', mode: 'mock', status: 'unverified',
      final_model: 'mock-v1', total_latency_ms: 18, total_cost_usd: '0', known_cost_usd: '0', cost_complete: true,
    }, {
      id: '00000000-0000-4000-8000-000000000002', created_at: '2026-10-21T13:00:00Z', mode: 'dev', status: 'error',
      final_model: null, total_latency_ms: null, total_cost_usd: null, known_cost_usd: '0.002', cost_complete: false,
    }] })
  })
  await page.route('**/api/benchmarks?limit=20', route => {
    reads++
    if (state === 'error') return route.fulfill({ status: 503, json: { code: 'database_unavailable' } })
    return route.fulfill({ json: state === 'empty' ? [] : [{
      job_id: '00000000-0000-4000-8000-000000000003', created_at: '2026-10-21T14:00:00Z',
      mode: 'mock', strategy: 'comparison', status: 'completed', case_count: 6,
      states: { pending: 0, running: 0, done: 6, error: 0, uncertain: 0 },
      online_pass_count: 0, known_cost_usd: '0', cost_complete: false, budget_usd: '0.25', budget_used_usd: '0',
      quality_basis: 'Offline browser fixture; no independent benchmark grading.',
      scoring_known_cost_usd: '0', scoring_cost_complete: true,
      strategy_metrics: {
        'fixed-cheap': { attempted_count: 2, pass_count: 0, total_runtime_cost_usd: '0', median_latency_ms: 18 },
        'fixed-strong': { attempted_count: 2, pass_count: 0, total_runtime_cost_usd: '0', median_latency_ms: 18 },
        routed: { attempted_count: 2, pass_count: 0, total_runtime_cost_usd: null, median_latency_ms: 18 },
      },
    }] })
  })
  await page.goto('/')
  await page.getByRole('textbox', { name: 'Your message' }).fill('Keep this draft.')
  const results = page.getByRole('button', { name: 'Runs & benchmarks', exact: true })
  await results.focus()
  await results.press('Enter')
  await expect(page.getByText('No runs yet.', { exact: false })).toBeVisible()
  await expect(page.getByText('No benchmark jobs yet.', { exact: false })).toBeVisible()
  state = 'populated'
  await page.getByRole('button', { name: 'Refresh runs', exact: true }).click()
  await page.getByRole('button', { name: 'Refresh benchmarks', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Recent runs table' })).toContainText('Incomplete · known $0.002')
  await expect(page.getByRole('region', { name: 'Benchmark jobs table' })).toContainText('6 done / 6 cases')
  await expect(page.getByText('fixed-cheap: 0 / 2 independent passes')).toBeVisible()
  await expect(page.getByText('Runtime cost incomplete', { exact: false })).toBeVisible()
  await expect(page.getByText('Comparison jobs use independent grading', { exact: false })).toBeVisible()
  await screenshot(page, testInfo, 'results')
  if (testInfo.project.name === 'mobile') {
    const table = page.getByRole('region', { name: 'Recent runs table' })
    await table.focus()
    await table.press('ArrowRight')
    await expect.poll(() => table.evaluate(element => element.scrollLeft)).toBeGreaterThan(0)
  }
  const loadedReads = reads
  await page.getByRole('button', { name: 'Chat', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Your message' })).toHaveValue('Keep this draft.')
  await results.click()
  await expect(page.getByRole('region', { name: 'Recent runs table' })).toBeVisible()
  expect(reads).toBe(loadedReads)
  state = 'error'
  await page.getByRole('button', { name: 'Refresh runs', exact: true }).click()
  await page.getByRole('button', { name: 'Refresh benchmarks', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Could not load recent runs' })).toBeVisible()
  await expect(page.getByRole('alert').filter({ hasText: 'Could not load benchmark jobs' })).toBeVisible()
  await expect(page.getByRole('alert').filter({ hasText: 'Could not load recent runs' })).toContainText('Previously loaded records')
  await expect(page.getByRole('region', { name: 'Recent runs table' })).toContainText('mock-v1')
})
