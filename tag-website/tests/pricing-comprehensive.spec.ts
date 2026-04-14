/**
 * Comprehensive Pricing E2E Tests
 *
 * Tests verify pricing LOGIC without hardcoding specific prices:
 * 1. Advance booking tiers: early (≥14 days) < standard (7-13 days) < late (<7 days)
 * 2. Peak day pricing: Fri/Sat drop-off OR Sun/Mon/Tue pickup adds increment
 * 3. Duration pricing: longer trips cost more
 * 4. Promo codes work correctly with all pricing factors
 *
 * Tests compare prices RELATIVE to each other rather than checking exact amounts.
 */

import { test, expect, Page } from '@playwright/test';

// Test data
const TEST_CUSTOMER = {
  firstName: 'Pricing',
  lastName: 'TestUser',
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

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Get a future date.
 * If targetDayOfWeek is provided, finds that day of week WITHIN the specified day range.
 * For tier testing, we want dates that result in exactly the expected days_in_advance.
 */
function getFutureDate(daysFromNow: number): Date {
  const date = new Date();
  date.setDate(date.getDate() + daysFromNow);
  return date;
}

function getDayName(date: Date): string {
  return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][date.getDay()];
}

/**
 * Select date in date picker
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
 * Navigate through booking flow to Step 4 (Payment) and return the displayed price
 */
async function getBookingPrice(
  page: Page,
  dropoffDate: Date,
  pickupDate: Date,
  promoCode?: string
): Promise<{ total: number; originalPrice: number; discount: number }> {
  await page.goto('/tag-it');
  await page.waitForLoadState('networkidle');

  // Dismiss Welcome Modal if present
  const welcomeModal = page.locator('.welcome-modal');
  const modalVisible = await welcomeModal.isVisible({ timeout: 5000 }).catch(() => false);
  if (modalVisible) {
    const continueBtn = page.locator('button.welcome-modal-btn');
    await continueBtn.click();
    await page.waitForTimeout(1000);
  }

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

  // ========== Step 4: Payment - Get Price ==========
  await page.locator('.booking-summary').waitFor({ state: 'visible', timeout: 10000 });
  await page.waitForTimeout(1000);

  // Apply promo code if provided
  if (promoCode) {
    const promoSection = page.locator('.promo-code-section');
    await promoSection.waitFor({ state: 'visible', timeout: 10000 });

    const promoInput = page.locator('.promo-code-input input[type="text"]');
    await promoInput.fill(promoCode);
    await page.waitForTimeout(300);

    await page.locator('.promo-apply-btn').click();
    await page.waitForTimeout(3000);
  }

  // Get pricing info
  let originalPrice = 0;
  let discount = 0;
  let total = 0;

  // Get subtotal (original price before discount)
  const subtotalEl = page.locator('.summary-item.subtotal span:last-child');
  if (await subtotalEl.isVisible({ timeout: 2000 }).catch(() => false)) {
    const text = await subtotalEl.textContent() || '0';
    originalPrice = parseFloat(text.replace(/[^0-9.]/g, ''));
  }

  // Get discount amount
  const discountEl = page.locator('.summary-item.discount .discount-amount');
  if (await discountEl.isVisible({ timeout: 2000 }).catch(() => false)) {
    const text = await discountEl.textContent() || '0';
    discount = parseFloat(text.replace(/[^0-9.]/g, ''));
  }

  // Get total
  const totalEl = page.locator('.summary-item.total span:last-child');
  await totalEl.waitFor({ state: 'visible', timeout: 5000 });
  const totalText = await totalEl.textContent() || '0';
  total = parseFloat(totalText.replace(/[^0-9.]/g, ''));

  // If no subtotal shown (no promo), original = total
  if (originalPrice === 0) {
    originalPrice = total;
  }

  return { total, originalPrice, discount };
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

// =============================================================================
// Test Suite: Advance Booking Tiers
// Each test gets ONE price, shared via test.describe.configure
// =============================================================================

test.describe.serial('Advance Booking Tiers', () => {
  let earlyTierPrice = 0;
  let standardTierPrice = 0;
  let lateTierPrice = 0;

  test('Early tier (≥14 days advance) - 7-day trip', async ({ page }) => {
    const dropOff = getFutureDate(16); // 16 days out = early tier
    const pickup = new Date(dropOff);
    pickup.setDate(pickup.getDate() + 7);

    const { total } = await getBookingPrice(page, dropOff, pickup);
    earlyTierPrice = total;

    console.log(`Early Tier Price (16 days advance): £${earlyTierPrice.toFixed(2)}`);
    expect(earlyTierPrice).toBeGreaterThan(0);

    // Complete payment
    const success = await completePayment(page, false);
    expect(success).toBe(true);
  });

  test('Standard tier (7-13 days advance) - 7-day trip', async ({ page }) => {
    const dropOff = getFutureDate(10); // 10 days out = standard tier
    const pickup = new Date(dropOff);
    pickup.setDate(pickup.getDate() + 7);

    const { total } = await getBookingPrice(page, dropOff, pickup);
    standardTierPrice = total;

    console.log(`Standard Tier Price (10 days advance): £${standardTierPrice.toFixed(2)}`);
    expect(standardTierPrice).toBeGreaterThan(0);
    expect(standardTierPrice).toBeGreaterThan(earlyTierPrice);

    // Complete payment
    const success = await completePayment(page, false);
    expect(success).toBe(true);
  });

  test('Late tier (<7 days advance) - 7-day trip', async ({ page }) => {
    const dropOff = getFutureDate(5); // 5 days out = late tier
    const pickup = new Date(dropOff);
    pickup.setDate(pickup.getDate() + 7);

    const { total } = await getBookingPrice(page, dropOff, pickup);
    lateTierPrice = total;

    console.log(`Late Tier Price (5 days advance): £${lateTierPrice.toFixed(2)}`);
    expect(lateTierPrice).toBeGreaterThan(0);
    expect(lateTierPrice).toBeGreaterThan(standardTierPrice);

    // Complete payment
    const success = await completePayment(page, false);
    expect(success).toBe(true);
  });

  test('Summary: Tier pricing verification', async () => {
    console.log(`
======================================================================
TIER PRICING SUMMARY
======================================================================
Early Tier (≥14 days):  £${earlyTierPrice.toFixed(2)}
Standard Tier (7-13d):  £${standardTierPrice.toFixed(2)}
Late Tier (<7 days):    £${lateTierPrice.toFixed(2)}
----------------------------------------------------------------------
Tier Increment 1:       £${(standardTierPrice - earlyTierPrice).toFixed(2)}
Tier Increment 2:       £${(lateTierPrice - standardTierPrice).toFixed(2)}
======================================================================
`);
    expect(earlyTierPrice).toBeLessThan(standardTierPrice);
    expect(standardTierPrice).toBeLessThan(lateTierPrice);
  });
});

// =============================================================================
// Test Suite: Peak Day Pricing
// =============================================================================

test.describe.serial('Peak Day Pricing', () => {
  let nonPeakPrice = 0;
  let peakDropoffPrice = 0;

  test('Non-peak Wednesday drop-off', async ({ page }) => {
    // Find next Wednesday that's 16+ days out (early tier)
    let dropOff = getFutureDate(16);
    while (dropOff.getDay() !== 3) { // 3 = Wednesday
      dropOff.setDate(dropOff.getDate() + 1);
    }
    const pickup = new Date(dropOff);
    pickup.setDate(pickup.getDate() + 7);

    const { total } = await getBookingPrice(page, dropOff, pickup);
    nonPeakPrice = total;

    console.log(`Non-peak (Wed drop-off): £${nonPeakPrice.toFixed(2)}`);
    expect(nonPeakPrice).toBeGreaterThan(0);

    // Complete payment
    const success = await completePayment(page, false);
    expect(success).toBe(true);
  });

  test('Peak Friday drop-off should cost more', async ({ page }) => {
    // Find next Friday that's 16+ days out (early tier, same as non-peak test)
    let dropOff = getFutureDate(16);
    while (dropOff.getDay() !== 5) { // 5 = Friday
      dropOff.setDate(dropOff.getDate() + 1);
    }
    const pickup = new Date(dropOff);
    pickup.setDate(pickup.getDate() + 7);

    const { total } = await getBookingPrice(page, dropOff, pickup);
    peakDropoffPrice = total;

    console.log(`Peak (Fri drop-off): £${peakDropoffPrice.toFixed(2)}`);
    console.log(`Peak increment: £${(peakDropoffPrice - nonPeakPrice).toFixed(2)}`);

    expect(peakDropoffPrice).toBeGreaterThan(0);
    expect(peakDropoffPrice).toBeGreaterThan(nonPeakPrice);

    // Complete payment
    const success = await completePayment(page, false);
    expect(success).toBe(true);
  });
});

// =============================================================================
// Test Suite: Duration Pricing
// =============================================================================

test.describe.serial('Duration Pricing', () => {
  let price7Day = 0;
  let price14Day = 0;

  test('7-day trip price', async ({ page }) => {
    const dropOff = getFutureDate(16); // 16 days out = early tier
    const pickup = new Date(dropOff);
    pickup.setDate(pickup.getDate() + 7);

    const { total } = await getBookingPrice(page, dropOff, pickup);
    price7Day = total;

    console.log(`7-day trip: £${price7Day.toFixed(2)}`);
    expect(price7Day).toBeGreaterThan(0);

    // Complete payment
    const success = await completePayment(page, false);
    expect(success).toBe(true);
  });

  test('14-day trip should cost more', async ({ page }) => {
    const dropOff = getFutureDate(16); // 16 days out = early tier
    const pickup = new Date(dropOff);
    pickup.setDate(pickup.getDate() + 14);

    const { total } = await getBookingPrice(page, dropOff, pickup);
    price14Day = total;

    console.log(`14-day trip: £${price14Day.toFixed(2)}`);
    console.log(`Duration difference: £${(price14Day - price7Day).toFixed(2)}`);

    expect(price14Day).toBeGreaterThan(0);
    expect(price14Day).toBeGreaterThan(price7Day);

    // Complete payment
    const success = await completePayment(page, false);
    expect(success).toBe(true);
  });
});

// =============================================================================
// Test Suite: Promo Codes
// =============================================================================

test.describe.serial('Promo Code Application', () => {
  let basePrice = 0;

  test('Get base price without promo', async ({ page }) => {
    const dropOff = getFutureDate(16); // 16 days out = early tier
    const pickup = new Date(dropOff);
    pickup.setDate(pickup.getDate() + 7);

    const { total } = await getBookingPrice(page, dropOff, pickup);
    basePrice = total;

    console.log(`Base price (no promo): £${basePrice.toFixed(2)}`);
    expect(basePrice).toBeGreaterThan(0);

    // Complete payment
    const success = await completePayment(page, false);
    expect(success).toBe(true);
  });

  test('TEST10 applies 10% discount', async ({ page }) => {
    const dropOff = getFutureDate(16); // 16 days out = early tier
    const pickup = new Date(dropOff);
    pickup.setDate(pickup.getDate() + 7);

    const { total, originalPrice, discount } = await getBookingPrice(page, dropOff, pickup, 'TEST10');

    const expectedDiscount = originalPrice * 0.10;
    console.log(`
======================================================================
TEST10 (10% off)
======================================================================
Original: £${originalPrice.toFixed(2)}
Discount: £${discount.toFixed(2)} (expected: £${expectedDiscount.toFixed(2)})
Total:    £${total.toFixed(2)}
======================================================================
`);

    expect(total).toBeLessThan(originalPrice);
    expect(total).toBeCloseTo(originalPrice - expectedDiscount, 0);

    // Complete payment
    const success = await completePayment(page, false);
    expect(success).toBe(true);
  });

  test('FREEWEEK on 7-day trip is FREE', async ({ page }) => {
    const dropOff = getFutureDate(16); // 16 days out = early tier
    const pickup = new Date(dropOff);
    pickup.setDate(pickup.getDate() + 7);

    const { total, originalPrice } = await getBookingPrice(page, dropOff, pickup, 'FREEWEEK');

    console.log(`FREEWEEK on 7-day: Original £${originalPrice.toFixed(2)}, Total £${total.toFixed(2)}`);

    expect(total).toBe(0);

    // Complete free booking
    const success = await completePayment(page, true);
    expect(success).toBe(true);
  });

  test('FREE100 on 14-day trip is completely FREE', async ({ page }) => {
    const dropOff = getFutureDate(16); // 16 days out = early tier
    const pickup = new Date(dropOff);
    pickup.setDate(pickup.getDate() + 14);

    const { total, originalPrice } = await getBookingPrice(page, dropOff, pickup, 'FREE100');

    console.log(`FREE100 on 14-day: Original £${originalPrice.toFixed(2)}, Total £${total.toFixed(2)}`);

    expect(total).toBe(0);

    // Complete free booking
    const success = await completePayment(page, true);
    expect(success).toBe(true);
  });
});
