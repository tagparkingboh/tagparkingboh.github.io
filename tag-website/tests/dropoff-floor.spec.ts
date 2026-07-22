import { test, expect, Page } from '@playwright/test';

/**
 * TAG Parking — 04:00 drop-off floor E2E
 *
 * Rule (2026-07-22): customers are never offered a drop-off before 04:00.
 * Slots computing earlier clamp up to a selectable "Earliest drop-off ·
 * 04:00" card (duplicates merged). Early-morning departures:
 *   06:00 → 04:00 (clamped, merged) + 04:30
 *   06:20 → 04:00 (clamped) + 04:20 + 04:50
 * Daytime departures are unaffected.
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
 * Get to the point on Step 1 where drop-off slots are visible:
 * date picked, airline + destination chosen, departure time entered.
 */
async function fillTripToSlots(page: Page, departureTime: string): Promise<void> {
  await page.goto('/tag-it');
  await page.waitForLoadState('networkidle');

  // Dismiss Welcome Modal
  const welcomeBtn = page.locator('button.welcome-modal-btn, button:has-text("Continue to booking")');
  await welcomeBtn.waitFor({ state: 'visible', timeout: 10000 });
  await welcomeBtn.click();
  await page.waitForTimeout(500);

  // Drop-off date ~10 days out (comfortably past the lead-time gate)
  const dropoffDate = new Date();
  dropoffDate.setDate(dropoffDate.getDate() + 10);
  await page.locator('#dropoffDate').click();
  await selectDateInPicker(page, dropoffDate);
  await page.waitForTimeout(1000);

  // Airline
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

  // Destination
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

  // Departure time
  await page.locator('#manualFlightTime').click();
  await page.locator('#manualFlightTime').fill(departureTime);
  await page.keyboard.press('Tab');

  // Slot cards render
  await page.locator('label.dropoff-slot').first().waitFor({ state: 'visible', timeout: 10000 });
}

const slotTimes = (page: Page) => page.locator('label.dropoff-slot .slot-time').allTextContents();
const slotLabels = (page: Page) => page.locator('label.dropoff-slot .slot-label').allTextContents();

test.describe('04:00 drop-off floor', () => {

  test('06:20 departure: customer can select the clamped 04:00 slot', async ({ page }) => {
    await fillTripToSlots(page, '06:20');

    // The motivating case: 03:35 must not exist; 04:00 must.
    expect(await slotTimes(page)).toEqual(['04:00', '04:20', '04:50']);
    expect((await slotLabels(page))[0]).toBe('Earliest drop-off');

    // Select the 04:00 card and verify the selection sticks — both the
    // checked radio (form state) and the visible lime highlight the
    // customer sees (input:checked + .slot-card styling).
    const earliestCard = page.locator('label.dropoff-slot', { hasText: '04:00' });
    await earliestCard.click();
    await expect(
      page.locator('input[name="manualDropoffSlot"]:checked')
    ).toHaveValue('165');
    await expect(earliestCard.locator('.slot-card')).toHaveCSS(
      'border-color', 'rgb(217, 255, 0)'
    );
    await page.waitForTimeout(1500); // hold the frame so headed runs are watchable
  });

  test('06:00 departure: merged 04:00 card is offered and selectable, no 03:15', async ({ page }) => {
    await fillTripToSlots(page, '06:00');

    // 2¾h (03:15) and 2h (04:00) both clamp/land on 04:00 → merged card.
    const times = await slotTimes(page);
    expect(times).toEqual(['04:00', '04:30']);
    expect(times).not.toContain('03:15');

    const earliestCard = page.locator('label.dropoff-slot', { hasText: '04:00' });
    await earliestCard.click();
    // Radio inputs are visually hidden behind the styled card — assert the
    // checked value, not visibility. The merged card keeps the '165' id.
    await expect(
      page.locator('input[name="manualDropoffSlot"]:checked')
    ).toHaveValue('165');
    await expect(earliestCard.locator('.slot-card')).toHaveCSS(
      'border-color', 'rgb(217, 255, 0)'
    );
    await page.waitForTimeout(1500); // hold the frame so headed runs are watchable

    // No pre-04:00 time anywhere in the slot list.
    for (const t of await slotTimes(page)) {
      expect(t >= '04:00').toBeTruthy();
    }
  });

  test('daytime departure is unaffected by the floor', async ({ page }) => {
    await fillTripToSlots(page, '14:30');

    expect(await slotTimes(page)).toEqual(['11:45', '12:30', '13:00']);
    expect(await slotLabels(page)).toEqual(['2¾ hours before', '2 hours before', '1½ hours before']);
  });

  test('full booking with the clamped 04:00 slot completes and issues a reference', async ({ page }) => {
    test.setTimeout(180000);
    await fillTripToSlots(page, '06:20');

    // Select the clamped 04:00 slot
    await page.locator('label.dropoff-slot', { hasText: '04:00' }).click();
    await page.waitForTimeout(300);

    // Return flight (+4 days), arrival time
    const pickupDate = new Date();
    pickupDate.setDate(pickupDate.getDate() + 14);
    const returnDatePicker = page.locator('.return-date-picker input, input[placeholder="Select return date"]');
    await returnDatePicker.click();
    await selectDateInPicker(page, pickupDate);
    await page.waitForTimeout(500);
    const arrivalTimeInput = page.locator('#manualArrivalFlightTime');
    if (await arrivalTimeInput.isVisible({ timeout: 2000 }).catch(() => false)) {
      await arrivalTimeInput.fill('18:30');
      await page.keyboard.press('Tab');
    }
    await page.waitForTimeout(500);

    // Continue → confirm times (modal shows the CLAMPED drop-off, not 03:35)
    await page.locator('button.next-btn, button:has-text("Continue")').first().click();
    const timeConfirmModal = page.locator('.time-confirm-modal');
    if (await timeConfirmModal.isVisible({ timeout: 3000 }).catch(() => false)) {
      await expect(timeConfirmModal).toContainText('04:00');
      await expect(timeConfirmModal).not.toContainText('03:35');
      await page.locator('.time-confirm-btn-primary, button:has-text("Yes, times are correct")').click();
    }
    await page.waitForTimeout(500);

    // Step 2: package
    const step2Continue = page.locator('button.next-btn, button:has-text("Continue")').first();
    if (await step2Continue.isVisible({ timeout: 3000 }).catch(() => false)) {
      await step2Continue.click();
      await page.waitForTimeout(1000);
    }

    // Step 3: customer / address / vehicle
    await page.locator('#firstName').fill('Mark');
    await page.locator('#lastName').fill('Testing');
    await page.locator('#email').fill('qa.orca.contact@gmail.com');
    const phoneInput = page.locator('.phone-input input[type="tel"]');
    await phoneInput.click();
    await phoneInput.fill('+447415693489');
    await page.keyboard.press('Tab');
    await page.waitForTimeout(500);

    await page.locator('#billingPostcode').fill('BH10 5BW');
    await page.locator('button:has-text("Find Address")').click();
    await page.waitForTimeout(2000);
    const manualEntryBtn = page.locator('button.manual-entry-link');
    if (await manualEntryBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await manualEntryBtn.click();
      await page.waitForTimeout(500);
    }
    await page.locator('#billingAddress1').fill('40 Western Ave');
    await page.locator('#billingCity').fill('Bournemouth');
    await page.locator('#registration').fill('AA19MOT');
    await page.locator('button.validate-btn:has-text("Lookup")').click();
    await page.waitForTimeout(3000);

    await page.locator('button:has-text("Continue to Payment")').click();
    await page.waitForTimeout(3000);
    const heardAboutSelect = page.locator('.heard-about-us-section select');
    if (await heardAboutSelect.isVisible({ timeout: 3000 }).catch(() => false)) {
      await heardAboutSelect.selectOption('google');
      await page.locator('button.heard-about-us-submit').click();
      await page.waitForTimeout(1000);
    }

    // Step 4: pay with the Stripe test card
    const termsCheckbox = page.locator('input[name="terms"]');
    if (!(await termsCheckbox.isChecked())) {
      await termsCheckbox.check();
      await page.waitForTimeout(1000);
    }
    await page.locator('.stripe-form').waitFor({ state: 'visible', timeout: 15000 });
    await page.waitForTimeout(2000);
    const stripeFrame = page.frameLocator('iframe[title*="Secure"]').first();
    await stripeFrame.locator('input[name="number"]').fill('4242424242424242');
    await stripeFrame.locator('input[name="expiry"]').fill('1065');
    await stripeFrame.locator('input[name="cvc"]').fill('321');
    await page.locator('button.stripe-pay-btn').click();

    // Confirmation: booking reference issued
    const refLocator = page.locator('text=/TAG-[A-Z]{3}[0-9]{5}/').first();
    await refLocator.waitFor({ state: 'visible', timeout: 45000 });
    const refText = (await refLocator.textContent()) || '';
    const bookingRef = refText.match(/TAG-[A-Z]{3}[0-9]{5}/)?.[0];
    expect(bookingRef).toBeTruthy();
    console.log(`FLOOR-E2E BOOKING REF: ${bookingRef}`);
    await page.waitForTimeout(1500);
  });
});
