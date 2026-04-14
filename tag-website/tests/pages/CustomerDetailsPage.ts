import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Customer Details Page Object Model
 * Step 3: Enter customer information
 */
export class CustomerDetailsPage extends BasePage {
  // Personal details
  readonly firstNameInput: Locator;
  readonly lastNameInput: Locator;
  readonly emailInput: Locator;
  readonly phoneInput: Locator;

  // Phone input with country code
  readonly phoneCountrySelect: Locator;
  readonly phoneNumberField: Locator;

  // Form validation
  readonly firstNameError: Locator;
  readonly lastNameError: Locator;
  readonly emailError: Locator;
  readonly phoneError: Locator;

  constructor(page: Page) {
    super(page);

    // Personal details
    this.firstNameInput = page.locator('input[name="firstName"], input[placeholder*="first"], input[placeholder*="First"]');
    this.lastNameInput = page.locator('input[name="lastName"], input[placeholder*="last"], input[placeholder*="Last"]');
    this.emailInput = page.locator('input[name="email"], input[type="email"], input[placeholder*="email"]');
    this.phoneInput = page.locator('input[name="phone"], input[type="tel"], input[placeholder*="phone"]');

    // Phone input with country code (react-phone-number-input)
    this.phoneCountrySelect = page.locator('.PhoneInputCountrySelect, select[class*="PhoneInputCountry"]');
    this.phoneNumberField = page.locator('.PhoneInputInput, input[class*="PhoneInputInput"]');

    // Form validation errors
    this.firstNameError = page.locator('[data-error="firstName"], .firstName-error, .error:near(input[name="firstName"])');
    this.lastNameError = page.locator('[data-error="lastName"], .lastName-error, .error:near(input[name="lastName"])');
    this.emailError = page.locator('[data-error="email"], .email-error, .error:near(input[name="email"])');
    this.phoneError = page.locator('[data-error="phone"], .phone-error, .error:near(input[name="phone"])');
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
   * Enter phone number (handles react-phone-number-input if present)
   */
  async enterPhone(phone: string) {
    // Try the react-phone-number-input first
    if (await this.phoneNumberField.isVisible({ timeout: 1000 }).catch(() => false)) {
      await this.phoneNumberField.clear();
      await this.phoneNumberField.fill(phone);
    } else {
      await this.phoneInput.clear();
      await this.phoneInput.fill(phone);
    }
  }

  /**
   * Select phone country code
   */
  async selectPhoneCountry(countryCode: string) {
    if (await this.phoneCountrySelect.isVisible({ timeout: 1000 }).catch(() => false)) {
      await this.phoneCountrySelect.selectOption(countryCode);
    }
  }

  /**
   * Get entered first name
   */
  async getFirstName(): Promise<string> {
    return await this.firstNameInput.inputValue();
  }

  /**
   * Get entered last name
   */
  async getLastName(): Promise<string> {
    return await this.lastNameInput.inputValue();
  }

  /**
   * Get entered email
   */
  async getEmail(): Promise<string> {
    return await this.emailInput.inputValue();
  }

  /**
   * Check if first name has validation error
   */
  async hasFirstNameError(): Promise<boolean> {
    return await this.firstNameError.isVisible({ timeout: 1000 }).catch(() => false);
  }

  /**
   * Check if last name has validation error
   */
  async hasLastNameError(): Promise<boolean> {
    return await this.lastNameError.isVisible({ timeout: 1000 }).catch(() => false);
  }

  /**
   * Check if email has validation error
   */
  async hasEmailError(): Promise<boolean> {
    return await this.emailError.isVisible({ timeout: 1000 }).catch(() => false);
  }

  /**
   * Check if phone has validation error
   */
  async hasPhoneError(): Promise<boolean> {
    return await this.phoneError.isVisible({ timeout: 1000 }).catch(() => false);
  }

  /**
   * Verify customer details step is displayed
   */
  async verifyStepDisplayed() {
    await expect(this.firstNameInput).toBeVisible();
    await expect(this.emailInput).toBeVisible();
  }

  /**
   * Complete customer details step with provided data
   */
  async completeCustomerDetails(customerData: {
    firstName: string;
    lastName: string;
    email: string;
    phone: string;
    countryCode?: string;
  }) {
    await this.enterFirstName(customerData.firstName);
    await this.enterLastName(customerData.lastName);
    await this.enterEmail(customerData.email);

    if (customerData.countryCode) {
      await this.selectPhoneCountry(customerData.countryCode);
    }
    await this.enterPhone(customerData.phone);
  }

  /**
   * Validate that all required fields are filled
   */
  async validateRequiredFields(): Promise<boolean> {
    const firstName = await this.getFirstName();
    const lastName = await this.getLastName();
    const email = await this.getEmail();

    return !!(firstName && lastName && email);
  }
}
