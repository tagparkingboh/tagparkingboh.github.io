import { Page, Locator, expect } from '@playwright/test';

/**
 * Base Page Object Model class
 * Contains common methods and elements shared across all pages
 */
export class BasePage {
  readonly page: Page;

  // Common elements
  readonly logo: Locator;
  readonly heroSection: Locator;
  readonly stepIndicator: Locator;
  readonly nextButton: Locator;
  readonly backButton: Locator;
  readonly errorMessage: Locator;
  readonly loadingSpinner: Locator;

  constructor(page: Page) {
    this.page = page;
    this.logo = page.locator('.logo, [class*="logo"]');
    this.heroSection = page.locator('.hero-section, [class*="hero"]');
    this.stepIndicator = page.locator('.step-indicator, .booking-steps');
    this.nextButton = page.locator('button:has-text("Next"), button:has-text("Continue")');
    this.backButton = page.locator('button:has-text("Back"), button:has-text("Previous")');
    this.errorMessage = page.locator('.error-message, [class*="error"]');
    this.loadingSpinner = page.locator('.spinner, .loading, [class*="spinner"]');
  }

  /**
   * Navigate to the base URL
   */
  async goto(path: string = '/') {
    await this.page.goto(path);
  }

  /**
   * Wait for page to be fully loaded
   */
  async waitForPageLoad() {
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Wait for loading spinner to disappear
   */
  async waitForLoadingComplete() {
    const spinner = this.loadingSpinner;
    if (await spinner.isVisible({ timeout: 1000 }).catch(() => false)) {
      await spinner.waitFor({ state: 'hidden', timeout: 30000 });
    }
  }

  /**
   * Check if error message is displayed
   */
  async hasError(): Promise<boolean> {
    return await this.errorMessage.isVisible({ timeout: 1000 }).catch(() => false);
  }

  /**
   * Get error message text
   */
  async getErrorMessage(): Promise<string> {
    if (await this.hasError()) {
      return await this.errorMessage.textContent() || '';
    }
    return '';
  }

  /**
   * Click the next/continue button
   */
  async clickNext() {
    await this.nextButton.click();
    await this.waitForLoadingComplete();
  }

  /**
   * Click the back button
   */
  async clickBack() {
    await this.backButton.click();
    await this.waitForLoadingComplete();
  }

  /**
   * Take a screenshot with a descriptive name
   */
  async takeScreenshot(name: string) {
    await this.page.screenshot({ path: `test-results/screenshots/${name}.png`, fullPage: true });
  }

  /**
   * Scroll to an element
   */
  async scrollToElement(locator: Locator) {
    await locator.scrollIntoViewIfNeeded();
  }

  /**
   * Wait for an element to be visible
   */
  async waitForVisible(locator: Locator, timeout: number = 10000) {
    await locator.waitFor({ state: 'visible', timeout });
  }

  /**
   * Get current step number from step indicator
   */
  async getCurrentStep(): Promise<number> {
    const activeStep = this.page.locator('.step.active, [class*="step"][class*="active"]');
    const text = await activeStep.textContent();
    const match = text?.match(/\d+/);
    return match ? parseInt(match[0]) : 0;
  }
}
