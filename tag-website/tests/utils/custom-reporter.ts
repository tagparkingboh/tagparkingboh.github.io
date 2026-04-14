import type {
  FullConfig,
  FullResult,
  Reporter,
  Suite,
  TestCase,
  TestResult,
} from '@playwright/test/reporter';
import * as fs from 'fs';
import * as path from 'path';

interface TestData {
  title: string;
  fullTitle: string;
  status: string;
  duration: number;
  email?: string;
  screenshot?: string;
  error?: string;
  retries: number;
  browser: string;
}

interface TestSummary {
  timestamp: string;
  totalTests: number;
  passed: number;
  failed: number;
  skipped: number;
  duration: string;
  tests: TestData[];
}

/**
 * Custom Playwright Reporter
 * Generates a detailed test report with email addresses used, screenshots, and other metadata
 */
class CustomReporter implements Reporter {
  private tests: TestData[] = [];
  private startTime: number = 0;
  private outputDir: string;

  constructor(options: { outputDir?: string } = {}) {
    this.outputDir = options.outputDir || 'test-results';
  }

  onBegin(config: FullConfig, suite: Suite) {
    this.startTime = Date.now();
    console.log('\n🧪 TAG Parking - E2E Test Suite');
    console.log('═'.repeat(50));
    console.log(`Running ${suite.allTests().length} tests across ${config.projects.length} browsers\n`);
  }

  onTestBegin(test: TestCase) {
    // Test starting - could add logging here if needed
  }

  onTestEnd(test: TestCase, result: TestResult) {
    // Extract email from test output or annotations
    let email: string | undefined;

    // Look for email in stdout
    for (const attachment of result.attachments) {
      if (attachment.name === 'test-email' && attachment.body) {
        email = attachment.body.toString();
      }
    }

    // Try to extract email from test title or output
    const emailMatch = result.stdout.join('').match(/[\w.-]+@yopmail\.com/);
    if (emailMatch) {
      email = emailMatch[0];
    }

    // Get screenshot path if available
    let screenshot: string | undefined;
    for (const attachment of result.attachments) {
      if (attachment.name === 'screenshot' && attachment.path) {
        screenshot = attachment.path;
      }
    }

    // Get browser/project name
    const browser = test.parent?.project()?.name || 'unknown';

    // Get error message if failed
    let error: string | undefined;
    if (result.status === 'failed' && result.errors.length > 0) {
      error = result.errors[0].message?.split('\n')[0] || 'Unknown error';
    }

    const testData: TestData = {
      title: test.title,
      fullTitle: test.titlePath().join(' > '),
      status: result.status,
      duration: result.duration,
      email,
      screenshot,
      error,
      retries: result.retry,
      browser,
    };

    this.tests.push(testData);

    // Print real-time status
    const statusIcon = this.getStatusIcon(result.status);
    const durationStr = `${(result.duration / 1000).toFixed(1)}s`;
    console.log(`${statusIcon} ${test.title} (${durationStr}) [${browser}]`);

    if (email) {
      console.log(`   📧 Email: ${email}`);
    }
    if (screenshot) {
      console.log(`   📸 Screenshot: ${path.basename(screenshot)}`);
    }
    if (error) {
      console.log(`   ❌ Error: ${error}`);
    }
  }

  async onEnd(result: FullResult) {
    const duration = Date.now() - this.startTime;
    const durationStr = this.formatDuration(duration);

    const passed = this.tests.filter(t => t.status === 'passed').length;
    const failed = this.tests.filter(t => t.status === 'failed').length;
    const skipped = this.tests.filter(t => t.status === 'skipped').length;

    console.log('\n' + '═'.repeat(50));
    console.log('📊 Test Results Summary');
    console.log('═'.repeat(50));
    console.log(`✅ Passed:  ${passed}`);
    console.log(`❌ Failed:  ${failed}`);
    console.log(`⏭️  Skipped: ${skipped}`);
    console.log(`⏱️  Duration: ${durationStr}`);
    console.log('═'.repeat(50));

    // Generate summary
    const summary: TestSummary = {
      timestamp: new Date().toISOString(),
      totalTests: this.tests.length,
      passed,
      failed,
      skipped,
      duration: durationStr,
      tests: this.tests,
    };

    // Ensure output directory exists
    if (!fs.existsSync(this.outputDir)) {
      fs.mkdirSync(this.outputDir, { recursive: true });
    }

    // Write JSON report
    const jsonPath = path.join(this.outputDir, 'test-summary.json');
    fs.writeFileSync(jsonPath, JSON.stringify(summary, null, 2));
    console.log(`\n📄 JSON Report: ${jsonPath}`);

    // Generate HTML report
    const htmlPath = path.join(this.outputDir, 'test-summary.html');
    fs.writeFileSync(htmlPath, this.generateHtmlReport(summary));
    console.log(`📄 HTML Report: ${htmlPath}`);

    // Print emails used
    const emailsUsed = this.tests.filter(t => t.email).map(t => t.email);
    if (emailsUsed.length > 0) {
      console.log('\n📧 Test Emails Used:');
      const uniqueEmails = [...new Set(emailsUsed)];
      uniqueEmails.forEach(email => console.log(`   - ${email}`));
    }

    // Print failed tests
    const failedTests = this.tests.filter(t => t.status === 'failed');
    if (failedTests.length > 0) {
      console.log('\n❌ Failed Tests:');
      failedTests.forEach(test => {
        console.log(`   - ${test.fullTitle}`);
        if (test.error) console.log(`     Error: ${test.error}`);
        if (test.screenshot) console.log(`     Screenshot: ${test.screenshot}`);
      });
    }

    console.log('\n');
  }

  private getStatusIcon(status: string): string {
    switch (status) {
      case 'passed': return '✅';
      case 'failed': return '❌';
      case 'skipped': return '⏭️';
      case 'timedOut': return '⏰';
      default: return '❓';
    }
  }

  private formatDuration(ms: number): string {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return minutes > 0
      ? `${minutes}m ${remainingSeconds}s`
      : `${seconds}s`;
  }

  private generateHtmlReport(summary: TestSummary): string {
    const passRate = ((summary.passed / summary.totalTests) * 100).toFixed(1);

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TAG Parking - Test Results</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
      color: #fff;
      min-height: 100vh;
      padding: 2rem;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    h1 {
      font-size: 2.5rem;
      margin-bottom: 0.5rem;
      background: linear-gradient(90deg, #adff2f, #7fff00);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .timestamp { color: #888; margin-bottom: 2rem; }
    .summary-cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }
    .card {
      background: rgba(255,255,255,0.05);
      border-radius: 12px;
      padding: 1.5rem;
      text-align: center;
      border: 1px solid rgba(255,255,255,0.1);
    }
    .card-value { font-size: 2.5rem; font-weight: bold; }
    .card-label { color: #888; margin-top: 0.5rem; }
    .card.passed .card-value { color: #adff2f; }
    .card.failed .card-value { color: #ff6b6b; }
    .card.skipped .card-value { color: #ffd93d; }
    .card.duration .card-value { color: #4ecdc4; }
    .progress-bar {
      height: 8px;
      background: rgba(255,255,255,0.1);
      border-radius: 4px;
      overflow: hidden;
      margin-bottom: 2rem;
    }
    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, #adff2f, #7fff00);
      width: ${passRate}%;
      transition: width 0.5s ease;
    }
    .section { margin-bottom: 2rem; }
    .section-title {
      font-size: 1.25rem;
      margin-bottom: 1rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid rgba(255,255,255,0.1);
    }
    .test-list { list-style: none; }
    .test-item {
      background: rgba(255,255,255,0.03);
      border-radius: 8px;
      padding: 1rem;
      margin-bottom: 0.5rem;
      border-left: 4px solid;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
    .test-item.passed { border-color: #adff2f; }
    .test-item.failed { border-color: #ff6b6b; }
    .test-item.skipped { border-color: #ffd93d; }
    .test-title { flex: 1; min-width: 200px; }
    .test-meta {
      display: flex;
      gap: 1rem;
      font-size: 0.85rem;
      color: #888;
      flex-wrap: wrap;
    }
    .test-meta span { display: flex; align-items: center; gap: 0.25rem; }
    .email-tag {
      background: rgba(173, 255, 47, 0.2);
      color: #adff2f;
      padding: 0.25rem 0.5rem;
      border-radius: 4px;
      font-size: 0.75rem;
    }
    .error-msg {
      width: 100%;
      margin-top: 0.5rem;
      padding: 0.5rem;
      background: rgba(255, 107, 107, 0.1);
      border-radius: 4px;
      color: #ff6b6b;
      font-size: 0.85rem;
    }
    .screenshot-link {
      color: #4ecdc4;
      text-decoration: none;
    }
    .screenshot-link:hover { text-decoration: underline; }
    .emails-section {
      background: rgba(255,255,255,0.03);
      border-radius: 8px;
      padding: 1rem;
    }
    .email-list {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 0.5rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>🅿️ TAG Parking Test Results</h1>
    <p class="timestamp">Generated: ${new Date(summary.timestamp).toLocaleString()}</p>

    <div class="summary-cards">
      <div class="card passed">
        <div class="card-value">${summary.passed}</div>
        <div class="card-label">Passed</div>
      </div>
      <div class="card failed">
        <div class="card-value">${summary.failed}</div>
        <div class="card-label">Failed</div>
      </div>
      <div class="card skipped">
        <div class="card-value">${summary.skipped}</div>
        <div class="card-label">Skipped</div>
      </div>
      <div class="card duration">
        <div class="card-value">${summary.duration}</div>
        <div class="card-label">Duration</div>
      </div>
    </div>

    <div class="progress-bar">
      <div class="progress-fill"></div>
    </div>
    <p style="text-align: center; color: #888; margin-bottom: 2rem;">${passRate}% Pass Rate</p>

    ${this.generateEmailsSection(summary.tests)}

    <div class="section">
      <h2 class="section-title">📋 All Tests</h2>
      <ul class="test-list">
        ${summary.tests.map(test => `
          <li class="test-item ${test.status}">
            <div class="test-title">
              <strong>${this.getStatusIcon(test.status)} ${test.title}</strong>
              <div style="color: #666; font-size: 0.85rem;">${test.fullTitle}</div>
            </div>
            <div class="test-meta">
              <span>⏱️ ${(test.duration / 1000).toFixed(1)}s</span>
              <span>🌐 ${test.browser}</span>
              ${test.email ? `<span class="email-tag">📧 ${test.email}</span>` : ''}
              ${test.screenshot ? `<span><a href="${test.screenshot}" class="screenshot-link">📸 Screenshot</a></span>` : ''}
            </div>
            ${test.error ? `<div class="error-msg">❌ ${test.error}</div>` : ''}
          </li>
        `).join('')}
      </ul>
    </div>
  </div>
</body>
</html>`;
  }

  private generateEmailsSection(tests: TestData[]): string {
    const emails = [...new Set(tests.filter(t => t.email).map(t => t.email))];
    if (emails.length === 0) return '';

    return `
    <div class="section">
      <h2 class="section-title">📧 Test Emails Used</h2>
      <div class="emails-section">
        <p>The following yopmail addresses were used during testing:</p>
        <div class="email-list">
          ${emails.map(email => `<span class="email-tag">${email}</span>`).join('')}
        </div>
      </div>
    </div>
    `;
  }
}

export default CustomReporter;
