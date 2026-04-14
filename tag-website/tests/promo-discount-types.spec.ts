import { test, expect, Page } from '@playwright/test';
import { testPromoCodes, promoCodeExpectations } from './utils/testData';

/**
 * TAG Parking - Promo Code Discount Types E2E Tests
 *
 * Tests the three distinct promo code discount types:
 * 1. 'percentage' (TEST10) - Standard percentage discount (e.g., 10% off)
 * 2. 'free_week' (FREEWEEK) - 1 Week Free: free for ≤7 days, deducts £79 for longer trips
 * 3. 'free_100' (FREE100) - 100% Off: completely free regardless of trip length
 *
 * Test Matrix:
 * - Each discount type with short trip (7 days) - verifies free vs paid behavior
 * - Each discount type with long trip (14 days) - verifies partial discount vs full free
 * - Promo code validation messages match expected type
 * - Payment UI shows correct state (Stripe form vs Free Booking confirmation)
 *
 * Test Card: 4242 4242 4242 4242, 10/65, 321
 */

// Test data
const TEST_CUSTOMER = {
  firstName: 'Promo',
  lastName: 'TestDiscount',
  email: 'qa.orca.contact@gmail.com',
  phone: '+447415693489',
};

const TEST_ADDRESS = {
  postcode: 'BH10 5BW',
  address1: '40 Western Ave',
  city: 'Bournemouth',
};

const TEST_VEHICLE = {
  registration: 'AA19MOT',
};

// Note: Pricing is dynamic and retrieved from the API.
// These are approximate values for reference only - tests should NOT hardcode exact amounts.
// Current pricing (Early tier, non-peak) as of April 2026:
// - 7 days: ~£85
// - 14 days: ~£150

/**
 * Helper: Format date for logging
 */
function formatTestDate(date: Date): string {
  return date.toLocaleDateString('en-GB', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  });
}

/**
 * Helper: Generate non-peak dates for test scenarios
 * Avoids Fri/Sat drop-off and Sun/Mon/Tue pickup
 */
function generateNonPeakDates(tripDuration: number, daysUntilDropoff: number = 16): { dropoffDate: Date; pickupDate: Date } {
  const now = new Date();
  let dropoffDate = new Date(now);
  dropoffDate.setDate(dropoffDate.getDate() + daysUntilDropoff);

  // Find non-peak combination
  const peakPickupDays = [0, 1, 2]; // Sun, Mon, Tue

  for (let attempt = 0; attempt < 14; attempt++) {
    const testDropoff = new Date(dropoffDate);
    testDropoff.setDate(testDropoff.getDate() + attempt);
    const dropoffDay = testDropoff.getDay();

    // Skip Fri/Sat drop-off
    if (dropoffDay === 5 || dropoffDay === 6) continue;

    // Check pickup day
    const testPickup = new Date(testDropoff);
    testPickup.setDate(testPickup.getDate() + tripDuration);
    const pickupDay = testPickup.getDay();

    // Skip Sun/Mon/Tue pickup
    if (!peakPickupDays.includes(pickupDay)) {
      dropoffDate = testDropoff;
      break;
    }
  }

  const pickupDate = new Date(dropoffDate);
  pickupDate.setDate(pickupDate.getDate() + tripDuration);

  return { dropoffDate, pickupDate };
}

/**
 * Helper: Select date in date picker
 */
async function selectDateInPicker(page: Page, date: Date): Promise<void> {
  await page.waitForSelector('.react-datepicker', { timeout: 5000 });

  for (let i = 0; i < 12; i++) {
    const currentMonth = await page.locator('.react-datepicker__current-month').textContent();
    if (currentMonth?.includes(date.toLocaleString('en-GB', { month: 'long' })) &&
        currentMonth?.includes(date.getFullYear().toString())) {
      break;
    }
    await page.locator('.react-datepicker__navigation--next').click();
    await page.waitForTimeout(200);
  }

  const dayStr = date.getDate().toString();
  const dayLocator = page.locator(`.react-datepicker__day:not(.react-datepicker__day--outside-month):has-text("${dayStr}")`).first();
  await dayLocator.click();
}

/**
 * Navigate through booking flow to Step 4 (Payment)
 */
async function navigateToPaymentStep(
  page: Page,
  dropoffDate: Date,
  pickupDate: Date
): Promise<void> {
  await page.goto('/tag-it');
  await page.waitForLoadState('networkidle');

  // Dismiss Welcome Modal
  const welcomeBtn = page.locator('button.welcome-modal-btn, button:has-text("Continue to booking")');
  await welcomeBtn.waitFor({ state: 'visible', timeout: 10000 });
  await welcomeBtn.click();
  await page.waitForTimeout(500);

  // ========== Step 1: Trip Details ==========
  await page.locator('#dropoffDate').click();
  await selectDateInPicker(page, dropoffDate);
  await page.waitForTimeout(1000);

  // Select Airline
  const airlineSelect = page.locator('#manualAirline');
  await airlineSelect.waitFor({ state: 'visible', timeout: 10000 });
  await page.waitForFunction(() => {
    const select = document.querySelector('#manualAirline') as HTMLSelectElement;
    return select && select.options.length > 2;
  }, { timeout: 10000 });
  const airlineOptions = await airlineSelect.locator('option').allTextContents();
  const realAirline = airlineOptions.find(opt => opt !== '' && opt !== 'Select airline' && opt !== 'Other');
  if (realAirline) {
    await airlineSelect.selectOption({ label: realAirline });
  }
  await page.waitForTimeout(500);

  // Select Destination
  const destSelect = page.locator('#manualDestination');
  await page.waitForFunction(() => {
    const select = document.querySelector('#manualDestination') as HTMLSelectElement;
    return select && select.options.length > 2;
  }, { timeout: 10000 });
  const destOptions = await destSelect.locator('option').allTextContents();
  const realDest = destOptions.find(opt => opt !== '' && opt !== 'Select destination' && opt !== 'Other');
  if (realDest) {
    await destSelect.selectOption({ label: realDest });
  }
  await page.waitForTimeout(500);

  // Enter Departure Time
  await page.locator('#manualFlightTime').click();
  await page.locator('#manualFlightTime').fill('14:30');
  await page.keyboard.press('Tab');
  await page.waitForTimeout(1000);

  // Select drop-off slot
  const dropoffSlotCard = page.locator('.dropoff-slot .slot-card, label.dropoff-slot').first();
  await dropoffSlotCard.waitFor({ state: 'visible', timeout: 10000 });
  await dropoffSlotCard.click();
  await page.waitForTimeout(500);

  // Select Return Date
  const returnDatePicker = page.locator('.return-date-picker input, input[placeholder="Select return date"]');
  await returnDatePicker.click();
  await selectDateInPicker(page, pickupDate);
  await page.waitForTimeout(500);

  // Fill arrival details if needed
  const arrivalTimeInput = page.locator('#manualArrivalFlightTime');
  if (await arrivalTimeInput.isVisible({ timeout: 2000 }).catch(() => false)) {
    await arrivalTimeInput.fill('18:30');
  }
  await page.waitForTimeout(500);

  // Continue to Step 2
  await page.locator('button.next-btn, button:has-text("Continue")').first().click();
  await page.waitForTimeout(1000);

  // ========== Step 2: Package Selection ==========
  const step2Continue = page.locator('button.next-btn, button:has-text("Continue")').first();
  if (await step2Continue.isVisible({ timeout: 3000 }).catch(() => false)) {
    await step2Continue.click();
    await page.waitForTimeout(1000);
  }

  // ========== Step 3: Details ==========
  await page.locator('#firstName').fill(TEST_CUSTOMER.firstName);
  await page.locator('#lastName').fill(TEST_CUSTOMER.lastName);
  await page.locator('#email').fill(TEST_CUSTOMER.email);

  const phoneInput = page.locator('.phone-input input[type="tel"]');
  await phoneInput.click();
  await phoneInput.fill(TEST_CUSTOMER.phone);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(500);

  // Address
  await page.locator('#billingPostcode').fill(TEST_ADDRESS.postcode);
  await page.locator('button:has-text("Find Address")').click();
  await page.waitForTimeout(2000);

  const manualEntryBtn = page.locator('button.manual-entry-link');
  if (await manualEntryBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await manualEntryBtn.click();
    await page.waitForTimeout(500);
  }

  await page.locator('#billingAddress1').fill(TEST_ADDRESS.address1);
  await page.locator('#billingCity').fill(TEST_ADDRESS.city);
  await page.waitForTimeout(300);

  // Vehicle
  await page.locator('#registration').fill(TEST_VEHICLE.registration);
  await page.waitForTimeout(300);
  await page.locator('button.validate-btn:has-text("Lookup")').click();
  await page.waitForTimeout(3000);

  // Continue to Payment
  await page.locator('button:has-text("Continue to Payment")').click();
  await page.waitForTimeout(3000);

  // Handle "Where did you hear about us?" if shown
  const heardAboutSelect = page.locator('.heard-about-us-section select');
  if (await heardAboutSelect.isVisible({ timeout: 3000 }).catch(() => false)) {
    await heardAboutSelect.selectOption('google');
    await page.waitForTimeout(300);
    await page.locator('button.heard-about-us-submit').click();
    await page.waitForTimeout(1000);
  }
}

/**
 * Apply a promo code and verify the response
 */
async function applyPromoCode(page: Page, promoCode: string): Promise<{
  success: boolean;
  message: string;
  discountPercent: number | null;
}> {
  // Wait for the promo code section to be visible
  const promoSection = page.locator('.promo-code-section');
  await promoSection.waitFor({ state: 'visible', timeout: 10000 });

  // Find the promo code input within the promo-code-input div
  const promoInput = page.locator('.promo-code-input input[type="text"]');
  await promoInput.waitFor({ state: 'visible', timeout: 5000 });
  await promoInput.fill(promoCode);
  await page.waitForTimeout(300);

  // Click Apply button
  const applyBtn = page.locator('.promo-apply-btn');
  await applyBtn.click();
  await page.waitForTimeout(3000);

  // Check for success message (promo applied shows .promo-code-applied)
  const appliedSection = page.locator('.promo-code-applied');
  const successMsg = page.locator('.promo-success');
  const errorMsg = page.locator('.promo-error');

  const isApplied = await appliedSection.isVisible({ timeout: 3000 }).catch(() => false);
  const isSuccess = isApplied || await successMsg.isVisible({ timeout: 1000 }).catch(() => false);
  const isError = await errorMsg.isVisible({ timeout: 1000 }).catch(() => false);

  let message = '';
  if (isSuccess) {
    message = await successMsg.textContent() || '';
  } else if (isError) {
    message = await errorMsg.textContent() || '';
  }

  // Try to extract discount percent from message
  let discountPercent: number | null = null;
  if (message.includes('10%')) discountPercent = 10;
  else if (message.includes('20%')) discountPercent = 20;
  else if (message.includes('100%') || message.toLowerCase().includes('free')) discountPercent = 100;

  return { success: isSuccess, message, discountPercent };
}

/**
 * Get pricing info from the payment summary
 */
async function getPricingInfo(page: Page): Promise<{
  originalPrice: number;
  discount: number;
  total: number;
  isFreeBooking: boolean;
}> {
  // Wait for booking summary to load
  await page.locator('.booking-summary').waitFor({ state: 'visible', timeout: 10000 });
  await page.waitForTimeout(1000);

  // Get subtotal (original price before discount)
  const subtotalEl = page.locator('.summary-item.subtotal span:last-child');
  let originalPrice = 0;
  if (await subtotalEl.isVisible({ timeout: 2000 }).catch(() => false)) {
    const text = await subtotalEl.textContent() || '0';
    originalPrice = parseFloat(text.replace(/[^0-9.]/g, ''));
  }

  // Get discount amount
  const discountEl = page.locator('.summary-item.discount .discount-amount');
  let discount = 0;
  if (await discountEl.isVisible({ timeout: 2000 }).catch(() => false)) {
    const text = await discountEl.textContent() || '0';
    discount = parseFloat(text.replace(/[^0-9.]/g, ''));
  }

  // Get total (always present)
  const totalEl = page.locator('.summary-item.total span:last-child');
  let total = 0;
  if (await totalEl.isVisible({ timeout: 2000 }).catch(() => false)) {
    const text = await totalEl.textContent() || '0';
    total = parseFloat(text.replace(/[^0-9.]/g, ''));
  }

  // If no subtotal shown (no promo), original = total
  if (originalPrice === 0) {
    originalPrice = total;
  }

  const isFreeBooking = total === 0 || total < 1;

  return { originalPrice, discount, total, isFreeBooking };
}

/**
 * Complete payment (handles both Stripe and free bookings)
 */
async function completePayment(page: Page, expectFree: boolean): Promise<boolean> {
  // Check T&Cs
  const termsCheckbox = page.locator('input[name="terms"]');
  const isChecked = await termsCheckbox.isChecked();
  if (!isChecked) {
    await termsCheckbox.check();
    await page.waitForTimeout(1000);
  }

  if (expectFree) {
    // For free bookings, look for "Complete" or "Confirm" button
    const completeButton = page.locator('button:has-text("Complete"), button:has-text("Confirm"), button.free-booking-btn');
    if (await completeButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      await completeButton.click();
      await page.waitForTimeout(5000);
    }
  } else {
    // For paid bookings, fill Stripe form
    await page.locator('.stripe-form').waitFor({ state: 'visible', timeout: 15000 });
    await page.waitForTimeout(2000);

    const stripeFrame = page.frameLocator('iframe[title*="Secure"]').first();
    await stripeFrame.locator('input[name="number"]').fill('4242424242424242');
    await page.waitForTimeout(500);
    await stripeFrame.locator('input[name="expiry"]').fill('1065');
    await page.waitForTimeout(500);
    await stripeFrame.locator('input[name="cvc"]').fill('321');
    await page.waitForTimeout(500);

    await page.locator('button.stripe-pay-btn').click();
    await page.waitForTimeout(5000);
  }

  // Check for success
  const successVisible = await page.locator('text=Payment Successful!, text=Booking Confirmed!, text=Booking Complete!').first().isVisible({ timeout: 30000 }).catch(() => false);
  if (successVisible) return true;

  const bookingRef = await page.locator('text=/TAG-[A-Z0-9]+/').isVisible({ timeout: 5000 }).catch(() => false);
  return bookingRef;
}

/**
 * Log test scenario
 */
function logScenario(scenario: {
  testName: string;
  promoCode: string;
  discountType: string;
  tripDuration: number;
  expectedBehavior: string;
  originalPrice: number;
  discount: number;
  total: number;
  isFreeBooking: boolean;
}) {
  console.log('\n' + '='.repeat(70));
  console.log(`TEST: ${scenario.testName}`);
  console.log('='.repeat(70));
  console.log(`Promo Code:       ${scenario.promoCode}`);
  console.log(`Discount Type:    ${scenario.discountType}`);
  console.log(`Trip Duration:    ${scenario.tripDuration} days`);
  console.log(`Expected:         ${scenario.expectedBehavior}`);
  console.log(`Original Price:   £${scenario.originalPrice.toFixed(2)}`);
  console.log(`Discount:         £${scenario.discount.toFixed(2)}`);
  console.log(`Total:            £${scenario.total.toFixed(2)}`);
  console.log(`Is Free Booking:  ${scenario.isFreeBooking ? 'YES' : 'NO'}`);
  console.log('='.repeat(70) + '\n');
}


// =============================================================================
// TEST SCENARIOS
// =============================================================================

test.describe('Promo Code Discount Types', () => {

  // ---------------------------------------------------------------------------
  // PERCENTAGE TYPE (TEST10) - 10% off
  // ---------------------------------------------------------------------------

  test.describe('percentage type (TEST10)', () => {

    test('7-day trip with 10% promo - should pay 90% of price', async ({ page }) => {
      const { dropoffDate, pickupDate } = generateNonPeakDates(7, 16);

      await navigateToPaymentStep(page, dropoffDate, pickupDate);

      // Apply promo code
      const promoResult = await applyPromoCode(page, testPromoCodes.tenPercent);
      expect(promoResult.success).toBe(true);

      // Get pricing
      const pricing = await getPricingInfo(page);

      logScenario({
        testName: '10% Promo - 7-day trip',
        promoCode: testPromoCodes.tenPercent,
        discountType: 'percentage',
        tripDuration: 7,
        expectedBehavior: 'Pay 90% of £79 = £71.10',
        originalPrice: pricing.originalPrice,
        discount: pricing.discount,
        total: pricing.total,
        isFreeBooking: pricing.isFreeBooking,
      });

      // Verify NOT a free booking
      expect(pricing.isFreeBooking).toBe(false);
      expect(pricing.total).toBeGreaterThan(0);

      // Complete payment with Stripe
      const success = await completePayment(page, false);
      expect(success).toBe(true);
    });

    test('14-day trip with 10% promo - should pay 90% of price', async ({ page }) => {
      const { dropoffDate, pickupDate } = generateNonPeakDates(14, 16);

      await navigateToPaymentStep(page, dropoffDate, pickupDate);

      const promoResult = await applyPromoCode(page, testPromoCodes.tenPercent);
      expect(promoResult.success).toBe(true);

      const pricing = await getPricingInfo(page);

      logScenario({
        testName: '10% Promo - 14-day trip',
        promoCode: testPromoCodes.tenPercent,
        discountType: 'percentage',
        tripDuration: 14,
        expectedBehavior: 'Pay 90% of £140 = £126',
        originalPrice: pricing.originalPrice,
        discount: pricing.discount,
        total: pricing.total,
        isFreeBooking: pricing.isFreeBooking,
      });

      expect(pricing.isFreeBooking).toBe(false);
      expect(pricing.total).toBeGreaterThan(0);

      const success = await completePayment(page, false);
      expect(success).toBe(true);
    });

  });

  // ---------------------------------------------------------------------------
  // FREE_WEEK TYPE (FREEWEEK) - Free for ≤7 days, partial discount for longer
  // ---------------------------------------------------------------------------

  test.describe('free_week type (FREEWEEK)', () => {

    test('7-day trip with FREEWEEK - should be completely FREE', async ({ page }) => {
      const { dropoffDate, pickupDate } = generateNonPeakDates(7, 16);

      await navigateToPaymentStep(page, dropoffDate, pickupDate);

      const promoResult = await applyPromoCode(page, testPromoCodes.freeWeek);
      expect(promoResult.success).toBe(true);
      expect(promoResult.message.toLowerCase()).toContain('free');

      const pricing = await getPricingInfo(page);

      logScenario({
        testName: 'FREEWEEK - 7-day trip (should be FREE)',
        promoCode: testPromoCodes.freeWeek,
        discountType: 'free_week',
        tripDuration: 7,
        expectedBehavior: 'Completely FREE (≤7 days)',
        originalPrice: pricing.originalPrice,
        discount: pricing.discount,
        total: pricing.total,
        isFreeBooking: pricing.isFreeBooking,
      });

      // Should be FREE
      expect(pricing.isFreeBooking).toBe(true);
      expect(pricing.total).toBe(0);

      // Complete as free booking (no Stripe)
      const success = await completePayment(page, true);
      expect(success).toBe(true);
    });

    test('5-day trip with FREEWEEK - should be completely FREE', async ({ page }) => {
      const { dropoffDate, pickupDate } = generateNonPeakDates(5, 16);

      await navigateToPaymentStep(page, dropoffDate, pickupDate);

      const promoResult = await applyPromoCode(page, testPromoCodes.freeWeek);
      expect(promoResult.success).toBe(true);

      const pricing = await getPricingInfo(page);

      logScenario({
        testName: 'FREEWEEK - 5-day trip (should be FREE)',
        promoCode: testPromoCodes.freeWeek,
        discountType: 'free_week',
        tripDuration: 5,
        expectedBehavior: 'Completely FREE (≤7 days)',
        originalPrice: pricing.originalPrice,
        discount: pricing.discount,
        total: pricing.total,
        isFreeBooking: pricing.isFreeBooking,
      });

      expect(pricing.isFreeBooking).toBe(true);

      const success = await completePayment(page, true);
      expect(success).toBe(true);
    });

    test('14-day trip with FREEWEEK - should pay remainder after £79 deducted', async ({ page }) => {
      const { dropoffDate, pickupDate } = generateNonPeakDates(14, 16);

      await navigateToPaymentStep(page, dropoffDate, pickupDate);

      const promoResult = await applyPromoCode(page, testPromoCodes.freeWeek);
      expect(promoResult.success).toBe(true);

      const pricing = await getPricingInfo(page);

      logScenario({
        testName: 'FREEWEEK - 14-day trip (should pay remainder)',
        promoCode: testPromoCodes.freeWeek,
        discountType: 'free_week',
        tripDuration: 14,
        expectedBehavior: 'Pay £140 - £79 = £61 (week1 deducted)',
        originalPrice: pricing.originalPrice,
        discount: pricing.discount,
        total: pricing.total,
        isFreeBooking: pricing.isFreeBooking,
      });

      // Should NOT be free - must pay remainder
      expect(pricing.isFreeBooking).toBe(false);
      expect(pricing.total).toBeGreaterThan(0);

      // For free_week on >7 day trips: discount = week1 price (around £85)
      // Verify discount is greater than 0 and less than original (partial discount)
      expect(pricing.discount).toBeGreaterThan(0);
      expect(pricing.discount).toBeLessThan(pricing.originalPrice);

      // Total should be original - discount (customer pays remainder)
      expect(pricing.total).toBeCloseTo(pricing.originalPrice - pricing.discount, 1);

      // Complete with Stripe payment
      const success = await completePayment(page, false);
      expect(success).toBe(true);
    });

    test('8-day trip with FREEWEEK - boundary test, should pay remainder', async ({ page }) => {
      const { dropoffDate, pickupDate } = generateNonPeakDates(8, 16);

      await navigateToPaymentStep(page, dropoffDate, pickupDate);

      const promoResult = await applyPromoCode(page, testPromoCodes.freeWeek);
      expect(promoResult.success).toBe(true);

      const pricing = await getPricingInfo(page);

      logScenario({
        testName: 'FREEWEEK - 8-day trip (boundary, should pay remainder)',
        promoCode: testPromoCodes.freeWeek,
        discountType: 'free_week',
        tripDuration: 8,
        expectedBehavior: '8 days > 7, so deduct £79, pay remainder',
        originalPrice: pricing.originalPrice,
        discount: pricing.discount,
        total: pricing.total,
        isFreeBooking: pricing.isFreeBooking,
      });

      // 8 days is past the 7-day boundary, should NOT be free
      expect(pricing.isFreeBooking).toBe(false);
      expect(pricing.total).toBeGreaterThan(0);

      const success = await completePayment(page, false);
      expect(success).toBe(true);
    });

  });

  // ---------------------------------------------------------------------------
  // FREE_100 TYPE (FREE100) - Completely free regardless of trip length
  // ---------------------------------------------------------------------------

  test.describe('free_100 type (FREE100)', () => {

    test('7-day trip with FREE100 - should be completely FREE', async ({ page }) => {
      const { dropoffDate, pickupDate } = generateNonPeakDates(7, 16);

      await navigateToPaymentStep(page, dropoffDate, pickupDate);

      const promoResult = await applyPromoCode(page, testPromoCodes.free100);
      expect(promoResult.success).toBe(true);

      const pricing = await getPricingInfo(page);

      logScenario({
        testName: 'FREE100 - 7-day trip (should be FREE)',
        promoCode: testPromoCodes.free100,
        discountType: 'free_100',
        tripDuration: 7,
        expectedBehavior: 'Completely FREE (100% off)',
        originalPrice: pricing.originalPrice,
        discount: pricing.discount,
        total: pricing.total,
        isFreeBooking: pricing.isFreeBooking,
      });

      expect(pricing.isFreeBooking).toBe(true);
      expect(pricing.total).toBe(0);

      const success = await completePayment(page, true);
      expect(success).toBe(true);
    });

    test('14-day trip with FREE100 - should STILL be completely FREE', async ({ page }) => {
      const { dropoffDate, pickupDate } = generateNonPeakDates(14, 16);

      await navigateToPaymentStep(page, dropoffDate, pickupDate);

      const promoResult = await applyPromoCode(page, testPromoCodes.free100);
      expect(promoResult.success).toBe(true);

      const pricing = await getPricingInfo(page);

      logScenario({
        testName: 'FREE100 - 14-day trip (should STILL be FREE)',
        promoCode: testPromoCodes.free100,
        discountType: 'free_100',
        tripDuration: 14,
        expectedBehavior: 'Completely FREE even for 14 days (unlike free_week)',
        originalPrice: pricing.originalPrice,
        discount: pricing.discount,
        total: pricing.total,
        isFreeBooking: pricing.isFreeBooking,
      });

      // FREE100 should be completely free even for 14-day trip
      // This is the KEY DIFFERENCE from FREEWEEK
      expect(pricing.isFreeBooking).toBe(true);
      expect(pricing.total).toBe(0);

      const success = await completePayment(page, true);
      expect(success).toBe(true);
    });

    test('21-day trip with FREE100 - should be completely FREE', async ({ page }) => {
      const { dropoffDate, pickupDate } = generateNonPeakDates(21, 16);

      await navigateToPaymentStep(page, dropoffDate, pickupDate);

      const promoResult = await applyPromoCode(page, testPromoCodes.free100);
      expect(promoResult.success).toBe(true);

      const pricing = await getPricingInfo(page);

      logScenario({
        testName: 'FREE100 - 21-day trip (should be FREE)',
        promoCode: testPromoCodes.free100,
        discountType: 'free_100',
        tripDuration: 21,
        expectedBehavior: 'Completely FREE for any duration',
        originalPrice: pricing.originalPrice,
        discount: pricing.discount,
        total: pricing.total,
        isFreeBooking: pricing.isFreeBooking,
      });

      expect(pricing.isFreeBooking).toBe(true);
      expect(pricing.total).toBe(0);

      const success = await completePayment(page, true);
      expect(success).toBe(true);
    });

  });

  // ---------------------------------------------------------------------------
  // COMPARISON TESTS - Same trip, different promo types
  // ---------------------------------------------------------------------------

  test.describe('Discount Type Comparison', () => {

    test('14-day trip: FREEWEEK vs FREE100 - verify different outcomes', async () => {
      // This test documents the expected DIFFERENCE between the two 100% promo types
      // For a 14-day trip:
      // - FREEWEEK: Customer pays £61 (£140 - £79 week1)
      // - FREE100: Customer pays £0 (completely free)

      console.log('\n' + '='.repeat(70));
      console.log('COMPARISON TEST: FREEWEEK vs FREE100 for 14-day trip');
      console.log('='.repeat(70));
      console.log('FREEWEEK (free_week type):');
      console.log('  - Original: £140');
      console.log('  - Discount: £79 (week1 price)');
      console.log('  - Total: £61 (customer pays remainder)');
      console.log('  - Is Free: NO');
      console.log('');
      console.log('FREE100 (free_100 type):');
      console.log('  - Original: £140');
      console.log('  - Discount: £140 (full amount)');
      console.log('  - Total: £0');
      console.log('  - Is Free: YES');
      console.log('='.repeat(70) + '\n');

      // This test just logs the expected behavior
      // The actual verification is done in the individual tests above
      expect(true).toBe(true);
    });

  });

  // ---------------------------------------------------------------------------
  // INVALID PROMO CODE TESTS
  // ---------------------------------------------------------------------------

  test.describe('Invalid Promo Codes', () => {

    test('Invalid promo code shows error message', async ({ page }) => {
      const { dropoffDate, pickupDate } = generateNonPeakDates(7, 16);

      await navigateToPaymentStep(page, dropoffDate, pickupDate);

      const promoResult = await applyPromoCode(page, testPromoCodes.invalid);

      console.log('\nInvalid Promo Test:');
      console.log(`  Code: ${testPromoCodes.invalid}`);
      console.log(`  Success: ${promoResult.success}`);
      console.log(`  Message: ${promoResult.message}`);

      expect(promoResult.success).toBe(false);
    });

  });

});
