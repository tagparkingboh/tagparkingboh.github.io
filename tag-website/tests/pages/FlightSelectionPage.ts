import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Flight Selection Page Object Model
 * Step 1: Select departure and return flights
 */
export class FlightSelectionPage extends BasePage {
  // Date pickers
  readonly dropoffDateInput: Locator;
  readonly pickupDateInput: Locator;
  readonly datePicker: Locator;
  readonly datePickerMonth: Locator;
  readonly datePickerNextMonth: Locator;
  readonly datePickerPrevMonth: Locator;

  // Flight selection
  readonly flightList: Locator;
  readonly flightCard: Locator;
  readonly selectedFlight: Locator;
  readonly flightNumber: Locator;
  readonly flightTime: Locator;
  readonly flightDestination: Locator;

  // Time slots
  readonly timeSlotContainer: Locator;
  readonly timeSlotButton: Locator;
  readonly selectedTimeSlot: Locator;

  // Return flight
  readonly arrivalFlightList: Locator;
  readonly arrivalFlightCard: Locator;

  // Price display
  readonly priceDisplay: Locator;
  readonly priceAmount: Locator;

  // "Tag It" button
  readonly tagItButton: Locator;

  constructor(page: Page) {
    super(page);

    // Date pickers
    this.dropoffDateInput = page.locator('input[placeholder*="drop"], input[name*="dropoff"], .react-datepicker-wrapper').first();
    this.pickupDateInput = page.locator('input[placeholder*="pick"], input[name*="pickup"], .react-datepicker-wrapper').last();
    this.datePicker = page.locator('.react-datepicker, .react-datepicker__month-container');
    this.datePickerMonth = page.locator('.react-datepicker__current-month');
    this.datePickerNextMonth = page.locator('.react-datepicker__navigation--next');
    this.datePickerPrevMonth = page.locator('.react-datepicker__navigation--previous');

    // Flight selection
    this.flightList = page.locator('.flight-list, .flights-container, [class*="flight-list"]');
    this.flightCard = page.locator('.flight-card, .flight-item, [class*="flight-card"]');
    this.selectedFlight = page.locator('.flight-card.selected, .flight-item.selected, [class*="selected"]');
    this.flightNumber = page.locator('.flight-number, [class*="flight-number"]');
    this.flightTime = page.locator('.flight-time, [class*="flight-time"]');
    this.flightDestination = page.locator('.flight-destination, [class*="destination"]');

    // Time slots
    this.timeSlotContainer = page.locator('.time-slots, .slot-picker, [class*="time-slot"]');
    this.timeSlotButton = page.locator('.time-slot-btn, .slot-button, button[class*="slot"]');
    this.selectedTimeSlot = page.locator('.time-slot-btn.selected, .slot-button.selected');

    // Return flight
    this.arrivalFlightList = page.locator('.arrival-flights, .return-flights');
    this.arrivalFlightCard = page.locator('.arrival-flight-card, .return-flight-item');

    // Price display
    this.priceDisplay = page.locator('.price-display, .pricing-info, [class*="price"]');
    this.priceAmount = page.locator('.price-amount, .total-price, [class*="price-amount"]');

    // Tag It button
    this.tagItButton = page.locator('button:has-text("Tag It"), button:has-text("TAG IT")');
  }

  /**
   * Navigate to the booking page
   */
  async navigateToBooking() {
    await this.goto('/');
    await this.waitForPageLoad();
  }

  /**
   * Click on "Tag It" button to start booking
   */
  async clickTagIt() {
    await this.tagItButton.click();
    await this.waitForLoadingComplete();
  }

  /**
   * Select a date from the date picker
   */
  async selectDate(picker: Locator, date: Date) {
    await picker.click();
    await this.datePicker.waitFor({ state: 'visible' });

    // Navigate to the correct month
    const targetMonth = date.toLocaleString('default', { month: 'long', year: 'numeric' });

    let attempts = 0;
    while (attempts < 12) {
      const currentMonth = await this.datePickerMonth.textContent();
      if (currentMonth?.includes(targetMonth)) break;

      // Check if we need to go forward or backward
      const currentDate = new Date(currentMonth || '');
      if (date > currentDate) {
        await this.datePickerNextMonth.click();
      } else {
        await this.datePickerPrevMonth.click();
      }
      attempts++;
      await this.page.waitForTimeout(200);
    }

    // Click on the day
    const daySelector = `.react-datepicker__day--0${date.getDate().toString().padStart(2, '0')}:not(.react-datepicker__day--outside-month)`;
    await this.page.locator(daySelector).click();
  }

  /**
   * Set drop-off date
   */
  async setDropoffDate(date: Date) {
    await this.selectDate(this.dropoffDateInput, date);
  }

  /**
   * Set pickup date
   */
  async setPickupDate(date: Date) {
    await this.selectDate(this.pickupDateInput, date);
  }

  /**
   * Select a flight by index
   */
  async selectFlightByIndex(index: number) {
    const flights = this.flightCard;
    await flights.nth(index).click();
    await this.waitForLoadingComplete();
  }

  /**
   * Select a flight by flight number
   */
  async selectFlightByNumber(flightNumber: string) {
    const flight = this.page.locator(`.flight-card:has-text("${flightNumber}"), .flight-item:has-text("${flightNumber}")`);
    await flight.click();
    await this.waitForLoadingComplete();
  }

  /**
   * Select a time slot by index
   */
  async selectTimeSlotByIndex(index: number) {
    const slots = this.timeSlotButton;
    await slots.nth(index).click();
  }

  /**
   * Select a time slot by time text
   */
  async selectTimeSlotByTime(time: string) {
    const slot = this.page.locator(`button:has-text("${time}")`);
    await slot.click();
  }

  /**
   * Select return flight by index
   */
  async selectReturnFlightByIndex(index: number) {
    const flights = this.arrivalFlightCard;
    await flights.nth(index).click();
    await this.waitForLoadingComplete();
  }

  /**
   * Get the displayed price
   */
  async getDisplayedPrice(): Promise<string> {
    return await this.priceAmount.textContent() || '';
  }

  /**
   * Get number of available flights
   */
  async getFlightCount(): Promise<number> {
    return await this.flightCard.count();
  }

  /**
   * Check if flights are loaded
   */
  async areFlightsLoaded(): Promise<boolean> {
    return await this.flightList.isVisible() && (await this.getFlightCount()) > 0;
  }

  /**
   * Verify flight selection step is displayed
   */
  async verifyStepDisplayed() {
    await expect(this.dropoffDateInput).toBeVisible();
  }

  /**
   * Complete flight selection step with provided dates
   */
  async completeFlightSelection(dropoffDate: Date, pickupDate: Date) {
    await this.setDropoffDate(dropoffDate);
    await this.page.waitForTimeout(500);
    await this.setPickupDate(pickupDate);
    await this.waitForLoadingComplete();

    // Wait for flights to load and select the first one
    if (await this.areFlightsLoaded()) {
      await this.selectFlightByIndex(0);
    }

    // Select time slot if available
    if (await this.timeSlotButton.first().isVisible({ timeout: 2000 }).catch(() => false)) {
      await this.selectTimeSlotByIndex(0);
    }
  }
}
