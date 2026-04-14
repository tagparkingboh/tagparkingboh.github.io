import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Payment Page Object Model
 * Step 4: Promo codes, T&Cs, and Stripe payment (embedded PaymentElement)
 */
export class PaymentPage extends BasePage {
  // Promo code section
  readonly promoCodeSection: Locator;
  readonly promoCodeInput: Locator;
  readonly promoApplyButton: Locator;
  readonly promoCodeApplied: Locator;
  readonly promoBadge: Locator;
  readonly promoSuccessMessage: Locator;
  readonly promoRemoveButton: Locator;
  readonly promoErrorMessage: Locator;

  // Booking summary
  readonly bookingSummary: Locator;
  readonly summaryTotal: Locator;
  readonly summaryDiscount: Locator;
  readonly summaryBasePrice: Locator;

  // Terms & Conditions
  readonly termsCheckbox: Locator;
  readonly termsLabel: Locator;
  readonly termsRequiredMessage: Locator;

  // Heard about us (required before payment)
  readonly heardAboutUsSection: Locator;
  readonly heardAboutUsSelect: Locator;
  readonly heardAboutUsSubmit: Locator;

  // Stripe Elements
  readonly stripeContainer: Locator;
  readonly paymentElement: Locator;
  readonly cardNumberFrame: Locator;
  readonly cardExpiryFrame: Locator;
  readonly cardCvcFrame: Locator;

  // Card inputs (inside Stripe iframe)
  readonly cardNumberInput: Locator;
  readonly cardExpiryInput: Locator;
  readonly cardCvcInput: Locator;

  // Payment button
  readonly payButton: Locator;
  readonly payButtonText: Locator;

  // Payment status
  readonly processingIndicator: Locator;
  readonly paymentError: Locator;
  readonly paymentSuccess: Locator;

  // Order summary
  readonly orderSummary: Locator;
  readonly totalAmount: Locator;
  readonly bookingReference: Locator;

  // Security badge
  readonly securityBadge: Locator;

  constructor(page: Page) {
    super(page);

    // Promo code section (from BookingsNew.jsx)
    this.promoCodeSection = page.locator('.promo-code-section');
    this.promoCodeInput = page.locator('.promo-code-input input[placeholder="Enter promo code"]');
    this.promoApplyButton = page.locator('button.promo-apply-btn');
    this.promoCodeApplied = page.locator('.promo-code-applied');
    this.promoBadge = page.locator('.promo-badge');
    this.promoSuccessMessage = page.locator('.promo-success');
    this.promoRemoveButton = page.locator('button.promo-remove');
    this.promoErrorMessage = page.locator('p.promo-error');

    // Booking summary
    this.bookingSummary = page.locator('.booking-summary');
    this.summaryTotal = page.locator('.summary-item.total span:last-child');
    this.summaryDiscount = page.locator('.summary-item.discount .discount-amount');
    this.summaryBasePrice = page.locator('.summary-item:has-text("Parking") span:last-child');

    // Terms & Conditions (from BookingsNew.jsx - inside checkbox-group)
    this.termsCheckbox = page.locator('input[name="terms"]');
    this.termsLabel = page.locator('label.checkbox-label:has(input[name="terms"])');
    this.termsRequiredMessage = page.locator('.terms-required p');

    // Heard about us
    this.heardAboutUsSection = page.locator('.heard-about-us-section');
    this.heardAboutUsSelect = page.locator('.heard-about-us-section select');
    this.heardAboutUsSubmit = page.locator('.heard-about-us-section button:has-text("Continue")');

    // Stripe Elements container - use the exact class from StripePayment.jsx
    this.stripeContainer = page.locator('.stripe-form');
    this.paymentElement = page.locator('.stripe-form iframe, .StripeElement');

    // Stripe iframes
    this.cardNumberFrame = page.frameLocator('iframe[name*="__privateStripeFrame"]').first();
    this.cardExpiryFrame = page.frameLocator('iframe[name*="__privateStripeFrame"]').nth(1);
    this.cardCvcFrame = page.frameLocator('iframe[name*="__privateStripeFrame"]').nth(2);

    // Card inputs (these need to be accessed through the frames)
    this.cardNumberInput = page.locator('input[name="cardnumber"]');
    this.cardExpiryInput = page.locator('input[name="exp-date"]');
    this.cardCvcInput = page.locator('input[name="cvc"]');

    // Payment button
    this.payButton = page.locator('.stripe-pay-btn, button:has-text("Pay"), button[type="submit"]:has-text("Pay")');
    this.payButtonText = page.locator('.stripe-pay-btn, button:has-text("Pay")');

    // Payment status
    this.processingIndicator = page.locator('.processing, button:has-text("Processing"), .spinner');
    this.paymentError = page.locator('.stripe-error, .payment-error, [class*="error"]');
    this.paymentSuccess = page.locator('.payment-success, .success-message');

    // Order summary
    this.orderSummary = page.locator('.order-summary, .booking-summary, [class*="summary"]');
    this.totalAmount = page.locator('.total-amount, .price-amount, [class*="total"]');
    this.bookingReference = page.locator('.booking-reference, [class*="reference"]');

    // Security badge
    this.securityBadge = page.locator('.stripe-security-note, [class*="security"]');
  }

  // ==========================================================================
  // Promo Code Methods
  // ==========================================================================

  /**
   * Enter and apply a promo code
   */
  async applyPromoCode(code: string) {
    await this.promoCodeInput.fill(code);
    await this.promoApplyButton.click();
    await this.waitForLoadingComplete();
    await this.page.waitForTimeout(1000);
  }

  /**
   * Check if promo code was successfully applied
   */
  async isPromoCodeApplied(): Promise<boolean> {
    return await this.promoCodeApplied.isVisible({ timeout: 2000 }).catch(() => false);
  }

  /**
   * Get the applied promo code text
   */
  async getAppliedPromoCode(): Promise<string> {
    if (await this.isPromoCodeApplied()) {
      return (await this.promoBadge.textContent()) || '';
    }
    return '';
  }

  /**
   * Get promo success message
   */
  async getPromoSuccessMessage(): Promise<string> {
    return (await this.promoSuccessMessage.textContent()) || '';
  }

  /**
   * Check if promo code has error
   */
  async hasPromoError(): Promise<boolean> {
    return await this.promoErrorMessage.isVisible({ timeout: 1000 }).catch(() => false);
  }

  /**
   * Get promo error message
   */
  async getPromoErrorMessage(): Promise<string> {
    return (await this.promoErrorMessage.textContent()) || '';
  }

  /**
   * Remove applied promo code
   */
  async removePromoCode() {
    await this.promoRemoveButton.click();
    await this.waitForLoadingComplete();
    await this.page.waitForTimeout(500);
  }

  // ==========================================================================
  // Terms & Conditions Methods
  // ==========================================================================

  /**
   * Check the Terms & Conditions checkbox
   */
  async acceptTerms() {
    const isChecked = await this.termsCheckbox.isChecked();
    if (!isChecked) {
      await this.termsCheckbox.check();
    }
  }

  /**
   * Uncheck the Terms & Conditions checkbox
   */
  async rejectTerms() {
    const isChecked = await this.termsCheckbox.isChecked();
    if (isChecked) {
      await this.termsCheckbox.uncheck();
    }
  }

  /**
   * Check if Terms & Conditions are accepted
   */
  async areTermsAccepted(): Promise<boolean> {
    return await this.termsCheckbox.isChecked();
  }

  /**
   * Check if terms required message is shown
   */
  async isTermsRequiredMessageVisible(): Promise<boolean> {
    return await this.termsRequiredMessage.isVisible({ timeout: 1000 }).catch(() => false);
  }

  // ==========================================================================
  // Heard About Us Methods
  // ==========================================================================

  /**
   * Select a source from "Where did you hear about us?"
   */
  async selectHeardAboutUs(source: string) {
    if (await this.heardAboutUsSection.isVisible({ timeout: 2000 }).catch(() => false)) {
      await this.heardAboutUsSelect.selectOption({ label: source });
      // Find and click submit if there's a submit button
      const submitBtn = this.page.locator('.heard-about-us-section button[type="submit"], .heard-about-us-section button:has-text("Submit")');
      if (await submitBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await submitBtn.click();
      }
      await this.waitForLoadingComplete();
    }
  }

  // ==========================================================================
  // Booking Summary Methods
  // ==========================================================================

  /**
   * Get the displayed base price
   */
  async getBasePrice(): Promise<string> {
    return (await this.summaryBasePrice.textContent()) || '';
  }

  /**
   * Get the displayed discount amount
   */
  async getDiscountAmount(): Promise<string> {
    if (await this.summaryDiscount.isVisible({ timeout: 1000 }).catch(() => false)) {
      return (await this.summaryDiscount.textContent()) || '';
    }
    return '';
  }

  /**
   * Get the displayed total price
   */
  async getTotalPrice(): Promise<string> {
    return (await this.summaryTotal.textContent()) || '';
  }

  /**
   * Parse price from text (e.g., "£99.00" -> 99.00)
   */
  parsePrice(priceText: string): number {
    const match = priceText.match(/[\d.]+/);
    return match ? parseFloat(match[0]) : 0;
  }

  // ==========================================================================
  // Stripe Payment Methods
  // ==========================================================================

  /**
   * Wait for Stripe payment form to load
   */
  async waitForStripeLoad() {
    await this.stripeContainer.waitFor({ state: 'visible', timeout: 30000 });
    await this.paymentElement.waitFor({ state: 'visible', timeout: 30000 });
    // Give Stripe extra time to fully initialize
    await this.page.waitForTimeout(2000);
  }

  /**
   * Fill card number in Stripe iframe
   * Note: This is complex due to Stripe's iframe security
   */
  async fillCardNumber(cardNumber: string) {
    // Stripe's PaymentElement handles the card input differently
    // We need to interact with the Stripe-hosted inputs
    const frame = this.page.frameLocator('iframe[name*="privateStripeFrame"]').first();
    await frame.locator('[name="number"], [placeholder*="number"]').fill(cardNumber);
  }

  /**
   * Fill card expiry in Stripe iframe
   */
  async fillCardExpiry(expiry: string) {
    const frame = this.page.frameLocator('iframe[name*="privateStripeFrame"]').first();
    await frame.locator('[name="expiry"], [placeholder*="MM / YY"]').fill(expiry);
  }

  /**
   * Fill card CVC in Stripe iframe
   */
  async fillCardCvc(cvc: string) {
    const frame = this.page.frameLocator('iframe[name*="privateStripeFrame"]').first();
    await frame.locator('[name="cvc"], [placeholder*="CVC"]').fill(cvc);
  }

  /**
   * Fill test card details using Stripe's test cards
   * Uses Stripe PaymentElement which renders in iframes
   * Test card: 4242 4242 4242 4242, 10/65, 321
   */
  async fillTestCard(testCardType: 'success' | 'decline' | 'auth_required' = 'success') {
    const testCards = {
      success: { number: '4242424242424242', expiry: '1065', cvc: '321' },
      decline: { number: '4000000000000002', expiry: '1065', cvc: '321' },
      auth_required: { number: '4000002500003155', expiry: '1065', cvc: '321' },
    };

    const card = testCards[testCardType];

    // Wait for Stripe PaymentElement to be ready
    await this.page.waitForTimeout(3000);

    // Stripe PaymentElement uses multiple iframes for each field
    // Try different iframe selectors that Stripe uses
    try {
      // Card number iframe
      const cardNumberFrame = this.page.frameLocator('iframe[name*="__privateStripeFrame"]').first();
      await cardNumberFrame.locator('input[name="cardnumber"]').fill(card.number);
      await this.page.waitForTimeout(500);

      // Expiry iframe (usually second frame)
      const expiryFrame = this.page.frameLocator('iframe[name*="__privateStripeFrame"]').nth(1);
      await expiryFrame.locator('input[name="exp-date"]').fill(card.expiry);
      await this.page.waitForTimeout(500);

      // CVC iframe (usually third frame)
      const cvcFrame = this.page.frameLocator('iframe[name*="__privateStripeFrame"]').nth(2);
      await cvcFrame.locator('input[name="cvc"]').fill(card.cvc);
      await this.page.waitForTimeout(500);
    } catch (error) {
      // Alternative: Try single iframe with PaymentElement structure
      console.log('Trying alternative Stripe iframe structure...');
      try {
        const stripeFrame = this.page.frameLocator('iframe[title*="Secure payment"]').first();
        await stripeFrame.locator('[data-testid="card-number-input"], input[autocomplete="cc-number"]').fill(card.number);
        await stripeFrame.locator('[data-testid="card-expiry-input"], input[autocomplete="cc-exp"]').fill(card.expiry);
        await stripeFrame.locator('[data-testid="card-cvc-input"], input[autocomplete="cc-csc"]').fill(card.cvc);
      } catch (innerError) {
        console.log('Stripe iframe interaction failed - PaymentElement structure may differ');
      }
    }
  }

  /**
   * Click the pay button
   */
  async clickPayButton() {
    await this.payButton.click();
  }

  /**
   * Submit payment and wait for result
   */
  async submitPayment() {
    await this.clickPayButton();
    // Wait for processing to complete
    await this.waitForPaymentResult();
  }

  /**
   * Wait for payment processing to complete
   */
  async waitForPaymentResult(timeout: number = 60000) {
    // Wait for either success or error
    await Promise.race([
      this.paymentSuccess.waitFor({ state: 'visible', timeout }).catch(() => {}),
      this.paymentError.waitFor({ state: 'visible', timeout }).catch(() => {}),
      this.page.waitForURL('**/booking-confirmation**', { timeout }).catch(() => {}),
    ]);
  }

  /**
   * Check if payment succeeded
   */
  async isPaymentSuccessful(): Promise<boolean> {
    return (
      (await this.paymentSuccess.isVisible({ timeout: 2000 }).catch(() => false)) ||
      this.page.url().includes('booking-confirmation')
    );
  }

  /**
   * Check if payment failed
   */
  async hasPaymentError(): Promise<boolean> {
    return await this.paymentError.isVisible({ timeout: 1000 }).catch(() => false);
  }

  /**
   * Get payment error message
   */
  async getPaymentErrorMessage(): Promise<string> {
    if (await this.hasPaymentError()) {
      return (await this.paymentError.textContent()) || '';
    }
    return '';
  }

  /**
   * Get the displayed total amount
   */
  async getTotalAmount(): Promise<string> {
    return (await this.totalAmount.textContent()) || '';
  }

  /**
   * Get the pay button text (should include amount)
   */
  async getPayButtonText(): Promise<string> {
    return (await this.payButton.textContent()) || '';
  }

  /**
   * Verify payment page is displayed
   */
  async verifyStepDisplayed() {
    await this.waitForStripeLoad();
    await expect(this.stripeContainer).toBeVisible();
    await expect(this.payButton).toBeVisible();
  }

  /**
   * Check if security badge is visible
   */
  async isSecurityBadgeVisible(): Promise<boolean> {
    return await this.securityBadge.isVisible();
  }

  /**
   * Complete payment with test card
   */
  async completePayment(testCardType: 'success' | 'decline' | 'auth_required' = 'success') {
    await this.waitForStripeLoad();
    await this.fillTestCard(testCardType);
    await this.submitPayment();
  }
}
