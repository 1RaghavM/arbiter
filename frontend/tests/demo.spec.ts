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
  await page.route('**/api/runs?limit=20&offset=0', route => {
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

test('run and benchmark dropdowns load saved details on demand and retry without provider calls', async ({ page }, testInfo) => {
  const run = {
    id: mockReply.run_id, created_at: '2026-11-06T14:00:00Z', mode: 'live', status: 'unverified',
    final_model: 'strong-fixture', total_latency_ms: 3200, total_cost_usd: null, known_cost_usd: '0.002', cost_complete: false,
    messages: [{ role: 'user', content: 'What is 6 multiplied by 7?' }],
    final_answer: 'Offline saved answer: 42. <script>window.fixtureExecuted = true</script>',
    analysis: { task: 'reasoning', difficulty: 'hard', reasoning: 'high', confidence: null, source: 'fallback' },
    route_decisions: [{ selected_key: 'strong-fixture', reason: 'Available stronger candidate within the remaining ceiling.' }],
    escalation_reason: 'First generation timed out.', reserved_cost_usd: '0.25', error: null,
    evaluations: [{ attempt: 2, model_key: 'strong-fixture', status: 'unknown', reason: 'The judge did not return a complete evaluation.' }],
    calls: [{
      sequence: 1, stage: 'generate', attempt: 1, model_id: 'gemini-3.5-flash-lite', status: 'error',
      latency_ms: 2000, input_tokens: null, output_tokens: null, cost_usd: null, error: { code: 'timeout' },
      output: { model_key: 'cheap-fixture', text: '', finish_reason: 'error' },
    }, {
      sequence: 2, stage: 'generate', attempt: 2, model_id: 'claude-sonnet-5-5', status: 'done',
      latency_ms: 900, input_tokens: 100, output_tokens: 20, cost_usd: '0.002', error: null,
      output: { model_key: 'strong-fixture', text: 'Offline saved attempt: 42.', finish_reason: 'stop' },
    }],
  }
  const failedRun = {
    ...run, id: '00000000-0000-4000-8000-000000000002', status: 'error', final_model: null,
    final_answer: null, analysis: null, calls: [], evaluations: [], route_decisions: [],
    escalation_reason: null, total_latency_ms: null, error: { code: 'provider_unavailable' },
  }
  const job = {
    job_id: '00000000-0000-4000-8000-000000000003', created_at: run.created_at,
    mode: 'mock', strategy: 'routed', status: 'blocked', case_count: 2,
    states: { pending: 1, running: 0, done: 1, error: 0, uncertain: 0 },
    online_pass_count: 0, known_cost_usd: '0', cost_complete: true, budget_usd: '0.25', budget_used_usd: '0',
    quality_basis: 'Offline browser fixture; online judge proxy only.',
    dataset_hash: 'offline-fixture-dataset', history_snapshot_id: null,
    cases: [
      { ordinal: 0, case_id: 'fixture-reasoning', strategy: 'routed', stage: 'runtime', state: 'done', run_id: run.id, attempts: 1 },
      { ordinal: 1, case_id: 'fixture-pending', strategy: 'routed', stage: 'runtime', state: 'pending', run_id: null, attempts: 0 },
    ],
  }
  let runReads = 0
  let jobReads = 0
  await page.route('**/api/runs?limit=20&offset=0', route => route.fulfill({ json: [run, failedRun] }))
  await page.route('**/api/benchmarks?limit=20', route => route.fulfill({ json: [job] }))
  await page.route(`**/api/runs/${run.id}`, route => {
    runReads++
    return runReads === 1
      ? route.fulfill({ status: 503, json: { code: 'database_unavailable' } })
      : route.fulfill({ json: run })
  })
  await page.route(`**/api/runs/${failedRun.id}`, route => route.fulfill({ json: failedRun }))
  await page.route(`**/api/benchmarks/${job.job_id}`, route => {
    jobReads++
    return jobReads === 1 ? route.fulfill({ json: { job_id: job.job_id, cases: null } }) : route.fulfill({ json: job })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Runs & benchmarks', exact: true }).click()
  const runs = page.getByRole('region', { name: 'Recent runs table' })
  await expect(runs).toBeVisible()
  expect(runReads).toBe(0)
  expect(jobReads).toBe(0)
  const details = runs.locator('details').first()
  await details.locator('summary').first().focus()
  await details.locator('summary').first().press('Enter')
  await expect(details.getByRole('alert')).toContainText('Could not load run details.')
  await details.getByRole('button', { name: 'Retry run details' }).click()
  await expect(details.getByText('What is 6 multiplied by 7?', { exact: true })).toBeVisible()
  await expect(details.getByText(run.final_answer, { exact: true })).toBeVisible()
  await expect(details.getByText('reasoning / hard', { exact: true })).toBeVisible()
  await expect(details.getByText('fallback · high reasoning · confidence unknown', { exact: true })).toBeVisible()
  await expect(details.getByText('gemini-3.5-flash-lite', { exact: true })).toBeVisible()
  await expect(details.getByText('claude-sonnet-5-5', { exact: true })).toBeVisible()
  await expect(details.getByText('Incomplete · known $0.002', { exact: true })).toBeVisible()
  await expect(details.getByText('$0.25', { exact: true })).toBeVisible()
  await expect(details.getByText('Selected claude-sonnet-5-5:', { exact: false })).toBeVisible()
  await expect(details.getByText('Attempt 2 · claude-sonnet-5-5 · unknown:', { exact: false })).toBeVisible()
  await expect(details.getByText('Cost unknown', { exact: false })).toBeVisible()
  await details.getByText('Attempt answer', { exact: true }).click()
  await expect(details.getByText('Offline saved attempt: 42.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => 'fixtureExecuted' in window)).toBe(false)
  expect(await details.evaluate(element => {
    const bounds = element.getBoundingClientRect()
    return bounds.left >= 0 && bounds.right <= window.innerWidth
  })).toBe(true)
  await screenshot(page, testInfo, 'run-details')
  await details.locator('summary').first().click()
  await details.locator('summary').first().click()
  await page.getByRole('button', { name: 'Chat', exact: true }).click()
  await page.getByRole('button', { name: 'Runs & benchmarks', exact: true }).click()
  await expect(details.getByText(run.final_answer, { exact: true })).toBeVisible()
  expect(runReads).toBe(2)
  const failedDetails = runs.locator('td > div > details').nth(1)
  await failedDetails.locator('summary').click()
  await expect(failedDetails.getByText('No answer was saved.', { exact: true })).toBeVisible()
  await expect(failedDetails.getByText('provider_unavailable', { exact: true })).toBeVisible()
  await expect(failedDetails.getByText('No calls recorded.', { exact: true })).toBeVisible()
  const benchmarks = page.getByRole('region', { name: 'Benchmark jobs table' })
  const jobDetails = benchmarks.locator('details').first()
  await jobDetails.locator('summary').click()
  await expect(jobDetails.getByRole('alert')).toContainText('Could not load benchmark details.')
  await jobDetails.getByRole('button', { name: 'Retry benchmark details' }).click()
  await expect(jobDetails.getByText('Dataset: offline-fixture-dataset', { exact: true })).toBeVisible()
  await expect(jobDetails.getByText('No run recorded.', { exact: true })).toBeVisible()
  const caseDetails = jobDetails.locator('li').first().locator('details').first()
  await caseDetails.locator('summary').click()
  await expect(caseDetails.getByText(run.final_answer, { exact: true })).toBeVisible()
  expect(runReads).toBe(3)
  expect(jobReads).toBe(2)
  expect(await caseDetails.evaluate(element => {
    const bounds = element.getBoundingClientRect()
    return bounds.left >= 0 && bounds.right <= window.innerWidth
  })).toBe(true)
  await details.locator('summary').first().click()
  await failedDetails.locator('summary').click()
  await screenshot(page, testInfo, 'benchmark-details')
})

test('selected completed runs download a Markdown summary', async ({ page }, testInfo) => {
  await page.route('**/api/runs?*', route => route.fulfill({ json: [{
    id: mockReply.run_id, created_at: '2026-11-06T12:00:00Z', mode: 'mock',
    status: 'unverified', final_model: 'mock-v1', total_latency_ms: 18,
    total_cost_usd: '0', known_cost_usd: '0', cost_complete: true,
  }] }))
  await page.route('**/api/benchmarks?*', route => route.fulfill({ json: [] }))
  await page.route('**/api/run-summaries', async route => {
    expect(route.request().postDataJSON()).toEqual({ run_ids: [mockReply.run_id] })
    await route.fulfill({ contentType: 'text/markdown', body: '# Selected run summary' })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Runs & benchmarks' }).click()
  await expect(page.getByRole('button', { name: 'Download summary (0)' })).toBeDisabled()
  await page.getByRole('checkbox', { name: `Select run ${mockReply.run_id}` }).check()
  await screenshot(page, testInfo, 'summary')
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download summary (1)' }).click()
  expect((await downloaded).suggestedFilename()).toBe('arbiter-run-summary.md')
})
