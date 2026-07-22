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
});
