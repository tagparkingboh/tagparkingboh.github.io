import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Booking Confirmation Page Object Model
 * Final step: Display booking confirmation details
 */
export class ConfirmationPage extends BasePage {
  // Confirmation elements
  readonly confirmationContainer: Locator;
  readonly successIcon: Locator;
  readonly successMessage: Locator;
  readonly bookingReference: Locator;
  readonly bookingReferenceValue: Locator;

  // Booking details summary
  readonly bookingSummary: Locator;
  readonly customerName: Locator;
  readonly customerEmail: Locator;
  readonly vehicleDetails: Locator;
  readonly flightDetails: Locator;
  readonly dropoffDate: Locator;
  readonly pickupDate: Locator;
  readonly totalPaid: Locator;

  // Email confirmation note
  readonly emailConfirmationNote: Locator;

  // Action buttons
  readonly printButton: Locator;
  readonly newBookingButton: Locator;
  readonly homeButton: Locator;

  constructor(page: Page) {
    super(page);

    // Confirmation elements
    this.confirmationContainer = page.locator('.confirmation-page, .booking-confirmation, [class*="confirmation"]');
    this.successIcon = page.locator('.success-icon, .check-icon, svg[class*="success"], svg[class*="check"]');
    this.successMessage = page.locator('.success-message, h1:has-text("confirmed"), h2:has-text("confirmed")');
    this.bookingReference = page.locator('.booking-reference, [class*="reference"]');
    this.bookingReferenceValue = page.locator('.reference-value, .booking-reference strong, .booking-reference span');

    // Booking details summary
    this.bookingSummary = page.locator('.booking-summary, .confirmation-details, [class*="summary"]');
    this.customerName = page.locator('[class*="customer-name"], .name-field');
    this.customerEmail = page.locator('[class*="customer-email"], .email-field');
    this.vehicleDetails = page.locator('[class*="vehicle"], .vehicle-info');
    this.flightDetails = page.locator('[class*="flight"], .flight-info');
    this.dropoffDate = page.locator('[class*="dropoff"], [class*="drop-off"], .dropoff-date');
    this.pickupDate = page.locator('[class*="pickup"], [class*="pick-up"], .pickup-date');
    this.totalPaid = page.locator('[class*="total"], .amount-paid');

    // Email confirmation note
    this.emailConfirmationNote = page.locator('.email-note, [class*="email-sent"], p:has-text("email")');

    // Action buttons
    this.printButton = page.locator('button:has-text("Print"), a:has-text("Print")');
    this.newBookingButton = page.locator('button:has-text("New Booking"), a:has-text("New Booking"), button:has-text("Book Again")');
    this.homeButton = page.locator('button:has-text("Home"), a:has-text("Home"), button:has-text("Return")');
  }

  /**
   * Wait for confirmation page to load
   */
  async waitForConfirmationLoad() {
    await this.page.waitForURL('**/booking-confirmation**', { timeout: 30000 });
    await this.confirmationContainer.waitFor({ state: 'visible', timeout: 10000 });
  }

  /**
   * Check if confirmation page is displayed
   */
  async isConfirmationDisplayed(): Promise<boolean> {
    return (
      this.page.url().includes('booking-confirmation') &&
      (await this.confirmationContainer.isVisible({ timeout: 2000 }).catch(() => false))
    );
  }

  /**
   * Get the booking reference number
   */
  async getBookingReference(): Promise<string> {
    const refElement = this.bookingReferenceValue.or(this.bookingReference);
    const text = await refElement.textContent();
    // Extract reference number (usually starts with TAG-)
    const match = text?.match(/TAG-[A-Z0-9]+/i);
    return match ? match[0] : text || '';
  }

  /**
   * Get the displayed customer name
   */
  async getCustomerName(): Promise<string> {
    return (await this.customerName.textContent()) || '';
  }

  /**
   * Get the displayed customer email
   */
  async getCustomerEmail(): Promise<string> {
    return (await this.customerEmail.textContent()) || '';
  }

  /**
   * Get the displayed vehicle details
   */
  async getVehicleDetails(): Promise<string> {
    return (await this.vehicleDetails.textContent()) || '';
  }

  /**
   * Get the displayed total paid amount
   */
  async getTotalPaid(): Promise<string> {
    return (await this.totalPaid.textContent()) || '';
  }

  /**
   * Check if success message is displayed
   */
  async isSuccessMessageVisible(): Promise<boolean> {
    return await this.successMessage.isVisible();
  }

  /**
   * Check if email confirmation note is displayed
   */
  async isEmailNoteVisible(): Promise<boolean> {
    return await this.emailConfirmationNote.isVisible({ timeout: 2000 }).catch(() => false);
  }

  /**
   * Click print button
   */
  async clickPrint() {
    await this.printButton.click();
  }

  /**
   * Click new booking button
   */
  async clickNewBooking() {
    await this.newBookingButton.click();
    await this.waitForPageLoad();
  }

  /**
   * Click home/return button
   */
  async clickHome() {
    await this.homeButton.click();
    await this.waitForPageLoad();
  }

  /**
   * Verify confirmation page is displayed correctly
   */
  async verifyConfirmationDisplayed() {
    await this.waitForConfirmationLoad();
    await expect(this.confirmationContainer).toBeVisible();
    await expect(this.bookingReference).toBeVisible();
  }

  /**
   * Verify all expected booking details are shown
   */
  async verifyBookingDetails(expectedDetails: {
    reference?: string;
    customerName?: string;
    email?: string;
    totalAmount?: string;
  }) {
    await this.verifyConfirmationDisplayed();

    if (expectedDetails.reference) {
      const reference = await this.getBookingReference();
      expect(reference).toContain(expectedDetails.reference);
    }

    if (expectedDetails.customerName) {
      const name = await this.getCustomerName();
      expect(name).toContain(expectedDetails.customerName);
    }

    if (expectedDetails.email) {
      const email = await this.getCustomerEmail();
      expect(email).toContain(expectedDetails.email);
    }

    if (expectedDetails.totalAmount) {
      const total = await this.getTotalPaid();
      expect(total).toContain(expectedDetails.totalAmount);
    }
  }

  /**
   * Get all confirmation details as an object
   */
  async getConfirmationDetails() {
    return {
      reference: await this.getBookingReference(),
      customerName: await this.getCustomerName(),
      customerEmail: await this.getCustomerEmail(),
      vehicleDetails: await this.getVehicleDetails(),
      totalPaid: await this.getTotalPaid(),
      isSuccessful: await this.isSuccessMessageVisible(),
    };
  }
}
