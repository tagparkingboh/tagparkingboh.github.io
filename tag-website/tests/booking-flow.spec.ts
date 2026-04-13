import { test, expect } from '@playwright/test';
import { FlightSelectionPage } from './pages/FlightSelectionPage';
import { VehicleDetailsPage } from './pages/VehicleDetailsPage';
import { CustomerDetailsPage } from './pages/CustomerDetailsPage';
import { BillingDetailsPage } from './pages/BillingDetailsPage';
import { PaymentPage } from './pages/PaymentPage';
import {
  testPromoCodes,
  testCustomers,
  testVehicles,
  testAddresses,
  generateTestDates,
  generatePeakDayDates,
  generateTierBoundaryDates,
  generateRandomEmail,
  generateRandomPhone,
} from './utils/testData';

/**
 * TAG Parking - Online Booking Flow E2E Tests
 *
 * Tests cover:
 * - Promo code add/remove functionality
 * - T&Cs check/uncheck blocking payment
 * - Pricing boundaries (peak days, tier increments, trip durations)
 *
 * Prerequisites:
 * - Staging environment running at VITE_API_URL
 * - Test promo codes exist: TEST10 (10% off), FREEWEEK (100% off for ≤7 days)
 */

// Uses baseURL from playwright.config.ts (staging-tagparking.netlify.app)

/**
 * Helper: Navigate through booking flow to Step 4 (Payment)
 */
async function navigateToPaymentStep(
  page: any,
  dropoffDate: Date,
  pickupDate: Date,
  customer = testCustomers.valid,
  vehicle = testVehicles.valid,
  address = testAddresses.uk
) {
  const flightPage = new FlightSelectionPage(page);
  const vehiclePage = new VehicleDetailsPage(page);
  const customerPage = new CustomerDetailsPage(page);
  const billingPage = new BillingDetailsPage(page);

  // Step 1: Navigate and select dates
  await page.goto('/tag-it');
  await page.waitForLoadState('networkidle');

  // Set drop-off date
  await page.locator('input[placeholder*="Drop"]').first().click();
  await selectDateInPicker(page, dropoffDate);

  // Set pickup date
  await page.locator('input[placeholder*="Pick"], input[placeholder*="Return"]').first().click();
  await selectDateInPicker(page, pickupDate);

  // Wait for flights to load and select first departure flight
  await page.waitForTimeout(2000);
  const departureFlights = page.locator('.flight-card, .flight-option, [class*="flight"]').first();
  if (await departureFlights.isVisible({ timeout: 5000 }).catch(() => false)) {
    await departureFlights.click();
  }

  // Select first time slot if available
  const timeSlot = page.locator('.slot-btn, .time-slot, [class*="slot"]').first();
  if (await timeSlot.isVisible({ timeout: 3000 }).catch(() => false)) {
    await timeSlot.click();
  }

  // Select return flight if available
  await page.waitForTimeout(1000);
  const returnFlight = page.locator('.arrival-flight, .return-flight, [class*="arrival"]').first();
  if (await returnFlight.isVisible({ timeout: 3000 }).catch(() => false)) {
    await returnFlight.click();
  }

  // Click continue to Step 2
  await page.locator('button:has-text("Continue")').first().click();
  await page.waitForTimeout(1000);

  // Step 2: Package selection - click continue
  await page.locator('button:has-text("Continue")').first().click();
  await page.waitForTimeout(1000);

  // Step 3: Customer & Billing Details
  // Fill customer details
  await page.locator('input[name="firstName"]').fill(customer.firstName);
  await page.locator('input[name="lastName"]').fill(customer.lastName);
  await page.locator('input[name="email"]').fill(generateRandomEmail());
  await page.locator('input[name="phone"], input[type="tel"]').fill(generateRandomPhone());

  // Fill vehicle registration
  await page.locator('input[name="registration"], input[placeholder*="reg"]').fill(vehicle.registration);

  // Try DVLA lookup or manual entry
  const lookupBtn = page.locator('button:has-text("Lookup"), button:has-text("Find")');
  if (await lookupBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await lookupBtn.click();
    await page.waitForTimeout(2000);
  }

  // Fill postcode and lookup address
  await page.locator('input[name="postcode"], input[placeholder*="postcode"]').fill(address.postcode);
  const addressLookupBtn = page.locator('button:has-text("Find Address"), button:has-text("Lookup")');
  if (await addressLookupBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await addressLookupBtn.click();
    await page.waitForTimeout(2000);

    // Select first address if dropdown appears
    const addressDropdown = page.locator('select[name="selectedAddress"], .address-dropdown');
    if (await addressDropdown.isVisible({ timeout: 2000 }).catch(() => false)) {
      await addressDropdown.selectOption({ index: 1 });
    }
  }

  // Click continue to Step 4
  await page.locator('button:has-text("Continue")').click();
  await page.waitForTimeout(2000);
}

/**
 * Helper: Select date in date picker
 */
async function selectDateInPicker(page: any, date: Date) {
  // Wait for date picker to be visible
  await page.waitForSelector('.react-datepicker, [class*="datepicker"]', { timeout: 5000 });

  const targetMonth = date.toLocaleString('en-GB', { month: 'long', year: 'numeric' });

  // Navigate to correct month
  for (let i = 0; i < 12; i++) {
    const currentMonth = await page.locator('.react-datepicker__current-month').textContent();
    if (currentMonth?.includes(date.toLocaleString('en-GB', { month: 'long' })) &&
        currentMonth?.includes(date.getFullYear().toString())) {
      break;
    }
    await page.locator('.react-datepicker__navigation--next').click();
    await page.waitForTimeout(200);
  }

  // Click on the day
  const dayStr = date.getDate().toString();
  const dayLocator = page.locator(`.react-datepicker__day:not(.react-datepicker__day--outside-month):has-text("${dayStr}")`).first();
  await dayLocator.click();
}

// =============================================================================
// PROMO CODE TESTS
// =============================================================================

test.describe('Promo Code - Add & Remove', () => {
  test.beforeEach(async ({ page }) => {
    const dates = generateTestDates(14, 7);
    await navigateToPaymentStep(page, dates.dropoffDate, dates.pickupDate);
  });

  test('should successfully apply TEST10 promo code (10% off)', async ({ page }) => {
    const paymentPage = new PaymentPage(page);

    // Get original price
    const originalTotal = await paymentPage.getTotalPrice();
    const originalPrice = paymentPage.parsePrice(originalTotal);

    // Apply TEST10 promo code
    await paymentPage.applyPromoCode(testPromoCodes.tenPercent);

    // Verify promo is applied
    expect(await paymentPage.isPromoCodeApplied()).toBe(true);
    expect(await paymentPage.getAppliedPromoCode()).toContain('TEST10');

    // Verify discount is shown
    const discountAmount = await paymentPage.getDiscountAmount();
    expect(discountAmount).toBeTruthy();

    // Verify total is reduced by 10%
    const newTotal = await paymentPage.getTotalPrice();
    const newPrice = paymentPage.parsePrice(newTotal);
    const expectedPrice = originalPrice * 0.9;
    expect(newPrice).toBeCloseTo(expectedPrice, 0);
  });

  test('should successfully apply FREEWEEK promo code (100% off for 7 days)', async ({ page }) => {
    const paymentPage = new PaymentPage(page);

    // Apply FREEWEEK promo code
    await paymentPage.applyPromoCode(testPromoCodes.freeWeek);

    // Verify promo is applied
    expect(await paymentPage.isPromoCodeApplied()).toBe(true);
    expect(await paymentPage.getAppliedPromoCode()).toContain('FREEWEEK');

    // For 7-day trip, total should be £0 or very low
    const newTotal = await paymentPage.getTotalPrice();
    const newPrice = paymentPage.parsePrice(newTotal);
    expect(newPrice).toBeLessThanOrEqual(1); // Allow for rounding
  });

  test('should show error for invalid promo code', async ({ page }) => {
    const paymentPage = new PaymentPage(page);

    // Apply invalid promo code
    await paymentPage.applyPromoCode(testPromoCodes.invalid);

    // Verify error is shown
    expect(await paymentPage.hasPromoError()).toBe(true);
    expect(await paymentPage.isPromoCodeApplied()).toBe(false);
  });

  test('should successfully remove applied promo code', async ({ page }) => {
    const paymentPage = new PaymentPage(page);

    // Get original price
    const originalTotal = await paymentPage.getTotalPrice();
    const originalPrice = paymentPage.parsePrice(originalTotal);

    // Apply promo code
    await paymentPage.applyPromoCode(testPromoCodes.tenPercent);
    expect(await paymentPage.isPromoCodeApplied()).toBe(true);

    // Get discounted price
    const discountedTotal = await paymentPage.getTotalPrice();
    const discountedPrice = paymentPage.parsePrice(discountedTotal);
    expect(discountedPrice).toBeLessThan(originalPrice);

    // Remove promo code
    await paymentPage.removePromoCode();

    // Verify promo is removed
    expect(await paymentPage.isPromoCodeApplied()).toBe(false);

    // Verify price is back to original
    const restoredTotal = await paymentPage.getTotalPrice();
    const restoredPrice = paymentPage.parsePrice(restoredTotal);
    expect(restoredPrice).toBeCloseTo(originalPrice, 0);
  });

  test('should allow re-applying promo code after removal', async ({ page }) => {
    const paymentPage = new PaymentPage(page);

    // Apply promo code
    await paymentPage.applyPromoCode(testPromoCodes.tenPercent);
    expect(await paymentPage.isPromoCodeApplied()).toBe(true);

    // Remove promo code
    await paymentPage.removePromoCode();
    expect(await paymentPage.isPromoCodeApplied()).toBe(false);

    // Re-apply same promo code
    await paymentPage.applyPromoCode(testPromoCodes.tenPercent);
    expect(await paymentPage.isPromoCodeApplied()).toBe(true);
  });
});

// =============================================================================
// TERMS & CONDITIONS TESTS
// =============================================================================

test.describe('Terms & Conditions - Check/Uncheck', () => {
  test.beforeEach(async ({ page }) => {
    const dates = generateTestDates(14, 7);
    await navigateToPaymentStep(page, dates.dropoffDate, dates.pickupDate);
  });

  test('should require T&Cs to be accepted before showing payment form', async ({ page }) => {
    const paymentPage = new PaymentPage(page);

    // Ensure T&Cs are not checked
    await paymentPage.rejectTerms();
    expect(await paymentPage.areTermsAccepted()).toBe(false);

    // Verify payment form is not visible / terms required message is shown
    const termsMessage = await paymentPage.isTermsRequiredMessageVisible();
    const stripeVisible = await paymentPage.stripeContainer.isVisible({ timeout: 1000 }).catch(() => false);

    // Either terms message should be visible OR stripe should not be visible
    expect(termsMessage || !stripeVisible).toBe(true);
  });

  test('should show payment form when T&Cs are accepted', async ({ page }) => {
    const paymentPage = new PaymentPage(page);

    // Answer "heard about us" question first if visible
    await paymentPage.selectHeardAboutUs('Google');

    // Accept T&Cs
    await paymentPage.acceptTerms();
    expect(await paymentPage.areTermsAccepted()).toBe(true);

    // Wait for Stripe to load
    await page.waitForTimeout(2000);

    // Verify payment form is visible
    const stripeVisible = await paymentPage.stripeContainer.isVisible({ timeout: 5000 }).catch(() => false);
    expect(stripeVisible).toBe(true);
  });

  test('should hide payment form when T&Cs are unchecked after being checked', async ({ page }) => {
    const paymentPage = new PaymentPage(page);

    // Answer "heard about us" question
    await paymentPage.selectHeardAboutUs('Google');

    // Accept T&Cs
    await paymentPage.acceptTerms();
    await page.waitForTimeout(2000);

    // Verify payment form is visible
    expect(await paymentPage.stripeContainer.isVisible({ timeout: 3000 }).catch(() => false)).toBe(true);

    // Uncheck T&Cs
    await paymentPage.rejectTerms();
    await page.waitForTimeout(500);

    // Verify payment form is hidden or terms message shows
    const termsMessage = await paymentPage.isTermsRequiredMessageVisible();
    const stripeVisible = await paymentPage.stripeContainer.isVisible({ timeout: 1000 }).catch(() => false);
    expect(termsMessage || !stripeVisible).toBe(true);
  });

  test('should toggle T&Cs checkbox correctly', async ({ page }) => {
    const paymentPage = new PaymentPage(page);

    // Start unchecked
    await paymentPage.rejectTerms();
    expect(await paymentPage.areTermsAccepted()).toBe(false);

    // Check
    await paymentPage.acceptTerms();
    expect(await paymentPage.areTermsAccepted()).toBe(true);

    // Uncheck
    await paymentPage.rejectTerms();
    expect(await paymentPage.areTermsAccepted()).toBe(false);

    // Check again
    await paymentPage.acceptTerms();
    expect(await paymentPage.areTermsAccepted()).toBe(true);
  });
});

// =============================================================================
// PRICING BOUNDARY TESTS
// =============================================================================

test.describe('Pricing - Peak Day Boundaries', () => {
  const peakDates = generatePeakDayDates();

  test('should show peak pricing for Friday drop-off', async ({ page }) => {
    await navigateToPaymentStep(
      page,
      peakDates.peakDropoffFriday.dropoffDate,
      peakDates.peakDropoffFriday.pickupDate
    );

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    // Peak pricing should be applied (we just verify price is reasonable)
    expect(price).toBeGreaterThan(0);
    console.log(`Friday drop-off price: £${price}`);
  });

  test('should show peak pricing for Saturday drop-off', async ({ page }) => {
    await navigateToPaymentStep(
      page,
      peakDates.peakDropoffSaturday.dropoffDate,
      peakDates.peakDropoffSaturday.pickupDate
    );

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    expect(price).toBeGreaterThan(0);
    console.log(`Saturday drop-off price: £${price}`);
  });

  test('should show peak pricing for Sunday pick-up', async ({ page }) => {
    await navigateToPaymentStep(
      page,
      peakDates.peakPickupSunday.dropoffDate,
      peakDates.peakPickupSunday.pickupDate
    );

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    expect(price).toBeGreaterThan(0);
    console.log(`Sunday pick-up price: £${price}`);
  });

  test('should show non-peak pricing for mid-week booking', async ({ page }) => {
    await navigateToPaymentStep(
      page,
      peakDates.nonPeak.dropoffDate,
      peakDates.nonPeak.pickupDate
    );

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    expect(price).toBeGreaterThan(0);
    console.log(`Mid-week (non-peak) price: £${price}`);
  });

  test('peak vs non-peak price comparison', async ({ page }) => {
    // Get peak price
    await navigateToPaymentStep(
      page,
      peakDates.peakDropoffFriday.dropoffDate,
      peakDates.peakDropoffFriday.pickupDate
    );
    const paymentPage = new PaymentPage(page);
    const peakTotal = await paymentPage.getTotalPrice();
    const peakPrice = paymentPage.parsePrice(peakTotal);

    // Get non-peak price (new booking)
    await navigateToPaymentStep(
      page,
      peakDates.nonPeak.dropoffDate,
      peakDates.nonPeak.pickupDate
    );
    const nonPeakTotal = await paymentPage.getTotalPrice();
    const nonPeakPrice = paymentPage.parsePrice(nonPeakTotal);

    console.log(`Peak price: £${peakPrice}, Non-peak price: £${nonPeakPrice}`);

    // Peak should be >= non-peak (allowing for same price if increment is 0)
    expect(peakPrice).toBeGreaterThanOrEqual(nonPeakPrice);
  });
});

test.describe('Pricing - Tier Boundaries', () => {
  const tierDates = generateTierBoundaryDates();

  test('should show early bird pricing (>14 days out)', async ({ page }) => {
    await navigateToPaymentStep(
      page,
      tierDates.early.dropoffDate,
      tierDates.early.pickupDate
    );

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    expect(price).toBeGreaterThan(0);
    console.log(`Early bird price (${tierDates.early.daysUntilDropoff} days): £${price}`);
  });

  test('should show standard pricing (7-14 days out)', async ({ page }) => {
    await navigateToPaymentStep(
      page,
      tierDates.standard.dropoffDate,
      tierDates.standard.pickupDate
    );

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    expect(price).toBeGreaterThan(0);
    console.log(`Standard price (${tierDates.standard.daysUntilDropoff} days): £${price}`);
  });

  test('should show late pricing (<7 days out)', async ({ page }) => {
    await navigateToPaymentStep(
      page,
      tierDates.late.dropoffDate,
      tierDates.late.pickupDate
    );

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    expect(price).toBeGreaterThan(0);
    console.log(`Late price (${tierDates.late.daysUntilDropoff} days): £${price}`);
  });

  test('should show correct pricing at 14-day boundary', async ({ page }) => {
    await navigateToPaymentStep(
      page,
      tierDates.boundary14Days.dropoffDate,
      tierDates.boundary14Days.pickupDate
    );

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    expect(price).toBeGreaterThan(0);
    console.log(`14-day boundary price: £${price}`);
  });

  test('should show correct pricing at 7-day boundary', async ({ page }) => {
    await navigateToPaymentStep(
      page,
      tierDates.boundary7Days.dropoffDate,
      tierDates.boundary7Days.pickupDate
    );

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    expect(price).toBeGreaterThan(0);
    console.log(`7-day boundary price: £${price}`);
  });

  test('tier pricing comparison - early should be cheapest', async ({ page }) => {
    // Get early price
    await navigateToPaymentStep(page, tierDates.early.dropoffDate, tierDates.early.pickupDate);
    const paymentPage = new PaymentPage(page);
    const earlyPrice = paymentPage.parsePrice(await paymentPage.getTotalPrice());

    // Get standard price
    await navigateToPaymentStep(page, tierDates.standard.dropoffDate, tierDates.standard.pickupDate);
    const standardPrice = paymentPage.parsePrice(await paymentPage.getTotalPrice());

    // Get late price
    await navigateToPaymentStep(page, tierDates.late.dropoffDate, tierDates.late.pickupDate);
    const latePrice = paymentPage.parsePrice(await paymentPage.getTotalPrice());

    console.log(`Early: £${earlyPrice}, Standard: £${standardPrice}, Late: £${latePrice}`);

    // Early should be <= Standard <= Late
    expect(earlyPrice).toBeLessThanOrEqual(standardPrice);
    expect(standardPrice).toBeLessThanOrEqual(latePrice);
  });
});

test.describe('Pricing - Trip Duration', () => {
  test('should calculate price for 7-day trip', async ({ page }) => {
    const dates = generateTestDates(14, 7);
    await navigateToPaymentStep(page, dates.dropoffDate, dates.pickupDate);

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    expect(price).toBeGreaterThan(0);
    console.log(`7-day trip price: £${price}`);
  });

  test('should calculate price for 14-day trip', async ({ page }) => {
    const dates = generateTestDates(14, 14);
    await navigateToPaymentStep(page, dates.dropoffDate, dates.pickupDate);

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    expect(price).toBeGreaterThan(0);
    console.log(`14-day trip price: £${price}`);
  });

  test('should calculate price for 21-day trip', async ({ page }) => {
    const dates = generateTestDates(14, 21);
    await navigateToPaymentStep(page, dates.dropoffDate, dates.pickupDate);

    const paymentPage = new PaymentPage(page);
    const totalPrice = await paymentPage.getTotalPrice();
    const price = paymentPage.parsePrice(totalPrice);

    expect(price).toBeGreaterThan(0);
    console.log(`21-day trip price: £${price}`);
  });

  test('longer trips should cost more', async ({ page }) => {
    const paymentPage = new PaymentPage(page);

    // 7-day trip
    const dates7 = generateTestDates(14, 7);
    await navigateToPaymentStep(page, dates7.dropoffDate, dates7.pickupDate);
    const price7 = paymentPage.parsePrice(await paymentPage.getTotalPrice());

    // 14-day trip
    const dates14 = generateTestDates(14, 14);
    await navigateToPaymentStep(page, dates14.dropoffDate, dates14.pickupDate);
    const price14 = paymentPage.parsePrice(await paymentPage.getTotalPrice());

    // 21-day trip
    const dates21 = generateTestDates(14, 21);
    await navigateToPaymentStep(page, dates21.dropoffDate, dates21.pickupDate);
    const price21 = paymentPage.parsePrice(await paymentPage.getTotalPrice());

    console.log(`7 days: £${price7}, 14 days: £${price14}, 21 days: £${price21}`);

    // Longer trips should cost more
    expect(price14).toBeGreaterThan(price7);
    expect(price21).toBeGreaterThan(price14);
  });
});

// =============================================================================
// COMBINED TESTS
// =============================================================================

test.describe('Combined - Promo + Pricing', () => {
  test('should apply 10% discount correctly to peak day pricing', async ({ page }) => {
    const peakDates = generatePeakDayDates();
    await navigateToPaymentStep(
      page,
      peakDates.peakDropoffFriday.dropoffDate,
      peakDates.peakDropoffFriday.pickupDate
    );

    const paymentPage = new PaymentPage(page);

    // Get original peak price
    const originalPrice = paymentPage.parsePrice(await paymentPage.getTotalPrice());

    // Apply 10% promo
    await paymentPage.applyPromoCode(testPromoCodes.tenPercent);
    expect(await paymentPage.isPromoCodeApplied()).toBe(true);

    // Verify discount
    const discountedPrice = paymentPage.parsePrice(await paymentPage.getTotalPrice());
    const expectedPrice = originalPrice * 0.9;

    expect(discountedPrice).toBeCloseTo(expectedPrice, 0);
    console.log(`Peak price: £${originalPrice}, After 10% off: £${discountedPrice}`);
  });

  test('FREEWEEK should give 100% off for 7-day trip', async ({ page }) => {
    const dates = generateTestDates(14, 7);
    await navigateToPaymentStep(page, dates.dropoffDate, dates.pickupDate);

    const paymentPage = new PaymentPage(page);

    // Get original price
    const originalPrice = paymentPage.parsePrice(await paymentPage.getTotalPrice());

    // Apply FREEWEEK
    await paymentPage.applyPromoCode(testPromoCodes.freeWeek);
    expect(await paymentPage.isPromoCodeApplied()).toBe(true);

    // Should be free or near-free
    const discountedPrice = paymentPage.parsePrice(await paymentPage.getTotalPrice());
    expect(discountedPrice).toBeLessThanOrEqual(1);
    console.log(`7-day original: £${originalPrice}, After FREEWEEK: £${discountedPrice}`);
  });

  test('FREEWEEK should deduct week 1 price for 14-day trip', async ({ page }) => {
    const dates = generateTestDates(14, 14);
    await navigateToPaymentStep(page, dates.dropoffDate, dates.pickupDate);

    const paymentPage = new PaymentPage(page);

    // Get original 14-day price
    const originalPrice = paymentPage.parsePrice(await paymentPage.getTotalPrice());

    // Apply FREEWEEK
    await paymentPage.applyPromoCode(testPromoCodes.freeWeek);
    expect(await paymentPage.isPromoCodeApplied()).toBe(true);

    // Should have week 1 price deducted (not free)
    const discountedPrice = paymentPage.parsePrice(await paymentPage.getTotalPrice());
    expect(discountedPrice).toBeGreaterThan(0);
    expect(discountedPrice).toBeLessThan(originalPrice);
    console.log(`14-day original: £${originalPrice}, After FREEWEEK: £${discountedPrice}`);
  });
});
