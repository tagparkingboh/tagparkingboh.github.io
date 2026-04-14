import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Vehicle Details Page Object Model
 * Step 2: Enter vehicle information
 */
export class VehicleDetailsPage extends BasePage {
  // Registration lookup
  readonly registrationInput: Locator;
  readonly lookupButton: Locator;
  readonly lookupSpinner: Locator;
  readonly lookupResult: Locator;

  // Vehicle details form
  readonly makeSelect: Locator;
  readonly modelSelect: Locator;
  readonly colourSelect: Locator;
  readonly customMakeInput: Locator;
  readonly customModelInput: Locator;

  // Package selection
  readonly packageContainer: Locator;
  readonly packageOption: Locator;
  readonly selectedPackage: Locator;
  readonly handWashPackage: Locator;
  readonly valetPackage: Locator;
  readonly noPackage: Locator;

  // Promo code
  readonly promoCodeInput: Locator;
  readonly applyPromoButton: Locator;
  readonly promoSuccess: Locator;
  readonly promoError: Locator;
  readonly removePromoButton: Locator;

  constructor(page: Page) {
    super(page);

    // Registration lookup
    this.registrationInput = page.locator('input[name="registration"], input[placeholder*="registration"], input[placeholder*="reg"]');
    this.lookupButton = page.locator('button:has-text("Lookup"), button:has-text("Find"), button:has-text("Search")');
    this.lookupSpinner = page.locator('.lookup-spinner, .lookup-loading');
    this.lookupResult = page.locator('.lookup-result, .vehicle-info');

    // Vehicle details form
    this.makeSelect = page.locator('select[name="make"], [class*="make"] select');
    this.modelSelect = page.locator('select[name="model"], [class*="model"] select');
    this.colourSelect = page.locator('select[name="colour"], select[name="color"], [class*="colour"] select');
    this.customMakeInput = page.locator('input[name="customMake"], input[placeholder*="make"]');
    this.customModelInput = page.locator('input[name="customModel"], input[placeholder*="model"]');

    // Package selection
    this.packageContainer = page.locator('.package-options, .packages-container, [class*="package"]');
    this.packageOption = page.locator('.package-option, .package-card, [class*="package-option"]');
    this.selectedPackage = page.locator('.package-option.selected, .package-card.selected');
    this.handWashPackage = page.locator('[data-package="hand-wash"], button:has-text("Hand Wash"), .package-option:has-text("Hand Wash")');
    this.valetPackage = page.locator('[data-package="valet"], button:has-text("Valet"), .package-option:has-text("Valet")');
    this.noPackage = page.locator('[data-package="none"], button:has-text("No Thanks"), .package-option:has-text("No Thanks")');

    // Promo code
    this.promoCodeInput = page.locator('input[name="promoCode"], input[placeholder*="promo"], input[placeholder*="Promo"]');
    this.applyPromoButton = page.locator('button:has-text("Apply"), button:has-text("APPLY")');
    this.promoSuccess = page.locator('.promo-success, [class*="promo-success"], .success-message');
    this.promoError = page.locator('.promo-error, [class*="promo-error"]');
    this.removePromoButton = page.locator('button:has-text("Remove"), .remove-promo');
  }

  /**
   * Enter vehicle registration
   */
  async enterRegistration(registration: string) {
    await this.registrationInput.clear();
    await this.registrationInput.fill(registration);
  }

  /**
   * Click lookup button and wait for result
   */
  async lookupVehicle() {
    await this.lookupButton.click();
    await this.waitForLoadingComplete();
    // Wait for lookup result or timeout
    await this.page.waitForTimeout(2000);
  }

  /**
   * Enter registration and lookup
   */
  async enterAndLookupRegistration(registration: string) {
    await this.enterRegistration(registration);
    await this.lookupVehicle();
  }

  /**
   * Select vehicle make from dropdown
   */
  async selectMake(make: string) {
    await this.makeSelect.selectOption({ label: make });
  }

  /**
   * Select vehicle model from dropdown
   */
  async selectModel(model: string) {
    await this.modelSelect.selectOption({ label: model });
  }

  /**
   * Select vehicle colour from dropdown
   */
  async selectColour(colour: string) {
    await this.colourSelect.selectOption({ label: colour });
  }

  /**
   * Enter custom make (when "Other" is selected)
   */
  async enterCustomMake(make: string) {
    await this.customMakeInput.fill(make);
  }

  /**
   * Enter custom model (when "Other" is selected)
   */
  async enterCustomModel(model: string) {
    await this.customModelInput.fill(model);
  }

  /**
   * Select a package by name
   */
  async selectPackage(packageName: 'hand-wash' | 'valet' | 'none') {
    switch (packageName) {
      case 'hand-wash':
        await this.handWashPackage.click();
        break;
      case 'valet':
        await this.valetPackage.click();
        break;
      case 'none':
        await this.noPackage.click();
        break;
    }
    await this.waitForLoadingComplete();
  }

  /**
   * Enter and apply promo code
   */
  async applyPromoCode(code: string) {
    await this.promoCodeInput.fill(code);
    await this.applyPromoButton.click();
    await this.waitForLoadingComplete();
    await this.page.waitForTimeout(1000);
  }

  /**
   * Check if promo code was successfully applied
   */
  async isPromoApplied(): Promise<boolean> {
    return await this.promoSuccess.isVisible({ timeout: 2000 }).catch(() => false);
  }

  /**
   * Check if promo code has error
   */
  async hasPromoError(): Promise<boolean> {
    return await this.promoError.isVisible({ timeout: 1000 }).catch(() => false);
  }

  /**
   * Remove applied promo code
   */
  async removePromoCode() {
    await this.removePromoButton.click();
    await this.waitForLoadingComplete();
  }

  /**
   * Get the currently selected make
   */
  async getSelectedMake(): Promise<string> {
    return await this.makeSelect.inputValue();
  }

  /**
   * Get the currently selected model
   */
  async getSelectedModel(): Promise<string> {
    return await this.modelSelect.inputValue();
  }

  /**
   * Get the currently selected colour
   */
  async getSelectedColour(): Promise<string> {
    return await this.colourSelect.inputValue();
  }

  /**
   * Verify vehicle details step is displayed
   */
  async verifyStepDisplayed() {
    await expect(this.registrationInput).toBeVisible();
  }

  /**
   * Complete vehicle details step with provided data
   */
  async completeVehicleDetails(vehicleData: {
    registration: string;
    make?: string;
    model?: string;
    colour?: string;
    package?: 'hand-wash' | 'valet' | 'none';
    promoCode?: string;
  }) {
    // Enter registration and lookup
    await this.enterAndLookupRegistration(vehicleData.registration);

    // Select or enter make/model/colour if not auto-filled
    if (vehicleData.make) {
      const makeValue = await this.getSelectedMake();
      if (!makeValue || makeValue === '' || makeValue === 'Select make') {
        await this.selectMake(vehicleData.make);
      }
    }

    if (vehicleData.model) {
      const modelValue = await this.getSelectedModel();
      if (!modelValue || modelValue === '' || modelValue === 'Select model') {
        await this.selectModel(vehicleData.model);
      }
    }

    if (vehicleData.colour) {
      const colourValue = await this.getSelectedColour();
      if (!colourValue || colourValue === '' || colourValue === 'Select colour') {
        await this.selectColour(vehicleData.colour);
      }
    }

    // Select package
    if (vehicleData.package) {
      await this.selectPackage(vehicleData.package);
    }

    // Apply promo code if provided
    if (vehicleData.promoCode) {
      await this.applyPromoCode(vehicleData.promoCode);
    }
  }
}
