import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Waitlist Signup Page Object Model
 * Handles the email capture form on the HomePage
 */
export class WaitlistSignupPage extends BasePage {
  // Form inputs
  readonly firstNameInput: Locator;
  readonly lastNameInput: Locator;
  readonly emailInput: Locator;
  readonly submitButton: Locator;

  // Status messages
  readonly successMessage: Locator;
  readonly errorMessage: Locator;

  // Subscribe section
  readonly subscribeSection: Locator;

  constructor(page: Page) {
    super(page);

    // Form inputs in the subscribe section
    this.subscribeSection = page.locator('#subscribe, .subscribe');
    this.firstNameInput = page.locator('.subscribe-form input[placeholder="First name"]');
    this.lastNameInput = page.locator('.subscribe-form input[placeholder="Last name"]');
    this.emailInput = page.locator('.subscribe-form input[placeholder="Enter your email"]');
    this.submitButton = page.locator('.subscribe-form button');

    // Status messages
    this.successMessage = page.locator('.subscribe-success');
    this.errorMessage = page.locator('.subscribe-error');
  }

  /**
   * Navigate to the homepage
   */
  async navigateToHomepage() {
    await this.goto('/');
    await this.waitForPageLoad();
  }

  /**
   * Scroll to the subscribe section
   */
  async scrollToSubscribeSection() {
    await this.subscribeSection.scrollIntoViewIfNeeded();
    await this.page.waitForTimeout(500);
  }

  /**
   * Enter first name
   */
  async enterFirstName(firstName: string) {
    await this.firstNameInput.clear();
    await this.firstNameInput.fill(firstName);
  }

  /**
   * Enter last name
   */
  async enterLastName(lastName: string) {
    await this.lastNameInput.clear();
    await this.lastNameInput.fill(lastName);
  }

  /**
   * Enter email address
   */
  async enterEmail(email: string) {
    await this.emailInput.clear();
    await this.emailInput.fill(email);
  }

  /**
   * Click the submit button
   */
  async clickSubmit() {
    await this.submitButton.click();
  }

  /**
   * Get the submit button text
   */
  async getSubmitButtonText(): Promise<string> {
    return (await this.submitButton.textContent()) || '';
  }

  /**
   * Check if submit button is disabled
   */
  async isSubmitButtonDisabled(): Promise<boolean> {
    return await this.submitButton.isDisabled();
  }

  /**
   * Check if success message is displayed
   */
  async isSuccessMessageVisible(): Promise<boolean> {
    return await this.successMessage.isVisible({ timeout: 5000 }).catch(() => false);
  }

  /**
   * Check if error message is displayed
   */
  async isErrorMessageVisible(): Promise<boolean> {
    return await this.errorMessage.isVisible({ timeout: 2000 }).catch(() => false);
  }

  /**
   * Get success message text
   */
  async getSuccessMessageText(): Promise<string> {
    if (await this.isSuccessMessageVisible()) {
      return (await this.successMessage.textContent()) || '';
    }
    return '';
  }

  /**
   * Get error message text
   */
  async getErrorMessageText(): Promise<string> {
    if (await this.isErrorMessageVisible()) {
      return (await this.errorMessage.textContent()) || '';
    }
    return '';
  }

  /**
   * Get first name input value
   */
  async getFirstNameValue(): Promise<string> {
    return await this.firstNameInput.inputValue();
  }

  /**
   * Get last name input value
   */
  async getLastNameValue(): Promise<string> {
    return await this.lastNameInput.inputValue();
  }

  /**
   * Get email input value
   */
  async getEmailValue(): Promise<string> {
    return await this.emailInput.inputValue();
  }

  /**
   * Check if form is cleared (after successful submission)
   */
  async isFormCleared(): Promise<boolean> {
    const firstName = await this.getFirstNameValue();
    const lastName = await this.getLastNameValue();
    const email = await this.getEmailValue();
    return firstName === '' && lastName === '' && email === '';
  }

  /**
   * Verify subscribe section is displayed
   */
  async verifySubscribeSectionDisplayed() {
    await expect(this.subscribeSection).toBeVisible();
    await expect(this.firstNameInput).toBeVisible();
    await expect(this.lastNameInput).toBeVisible();
    await expect(this.emailInput).toBeVisible();
    await expect(this.submitButton).toBeVisible();
  }

  /**
   * Fill the complete signup form
   */
  async fillSignupForm(data: { firstName: string; lastName: string; email: string }) {
    await this.enterFirstName(data.firstName);
    await this.enterLastName(data.lastName);
    await this.enterEmail(data.email);
  }

  /**
   * Complete signup flow
   */
  async completeSignup(data: { firstName: string; lastName: string; email: string }) {
    await this.scrollToSubscribeSection();
    await this.fillSignupForm(data);
    await this.clickSubmit();
    // Wait for API response
    await this.page.waitForTimeout(2000);
  }

  /**
   * Wait for submission to complete
   */
  async waitForSubmissionComplete() {
    // Wait for button text to change from "Joining..." back to normal
    await this.page.waitForFunction(
      () => {
        const button = document.querySelector('.subscribe-form button');
        return button && !button.textContent?.includes('Joining');
      },
      { timeout: 10000 }
    );
  }
}
