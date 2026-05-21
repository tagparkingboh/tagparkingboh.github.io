/**
 * E2E verification for the new `flight_arrival_date` column on bookings.
 *
 * Three scenarios, all booking dropoff = Wed 1 Jul 2026 + a return flight
 * landing in the rollover window:
 *
 *   1. Return Wed 8 Jul 2026 @ 23:30  — rollover fires (pickup → 9 Jul 00:00)
 *   2. Return Wed 8 Jul 2026 @ 23:59  — rollover fires (pickup → 9 Jul 00:29)
 *   3. Return Thu 9 Jul 2026 @ 01:30  — no rollover (pickup → 9 Jul 02:00)
 *
 * What we capture & assert per scenario:
 *   - Time-confirmation modal screenshot (visual proof that Arrival vs
 *     Pick-up dates render correctly client-side post-fix)
 *   - The exact /api/payments/create-intent request body, asserting
 *     `flight_arrival_date` is the un-rolled landing day
 *   - The /api/payments/create-intent response's booking_reference, so we
 *     can verify the persisted row from a follow-up DB query
 *
 * Serial mode (workers=1) because each test does a full booking write.
 */
import { test, expect, Page } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

const TEST_CUSTOMER = {
  firstName: 'Mark',
  lastName: 'Testing',
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

// Date helpers — local-time construction so the picker selects the same calendar day.
const D = (y: number, m: number, d: number) => new Date(y, m - 1, d);

interface Scenario {
  label: string;
  dropoffDate: Date;
  pickupDate: Date;
  arrivalTime: string;          // HH:MM as typed into #manualArrivalFlightTime
  // Manual-entry path: the frontend sends the un-rolled landing day for both
  // pickup_date and flight_arrival_date; the backend then rolls pickup_date
  // forward by a day when arrival_time + 30 ≥ midnight.
  reqArrivalDate: string;       // yyyy-MM-dd — value sent in the request body
  reqPickupDate: string;        // yyyy-MM-dd — value sent in the request body
  storedPickupDate: string;     // yyyy-MM-dd — what the DB row should have after backend rollover
  storedFlightArrivalDate: string; // yyyy-MM-dd — what the DB row should have (canonical landing day)
  storedPickupTime: string;     // HH:MM the backend should compute
}

const scenarios: Scenario[] = [
  {
    label: '23:30 Wed 8 Jul — rollover boundary',
    dropoffDate: D(2026, 7, 1),
    pickupDate:  D(2026, 7, 8),
    arrivalTime: '23:30',
    reqArrivalDate:          '2026-07-08',
    reqPickupDate:           '2026-07-08',
    storedPickupDate:        '2026-07-09',
    storedFlightArrivalDate: '2026-07-08',
    storedPickupTime:        '00:00',
  },
  {
    label: '23:59 Wed 8 Jul — last-minute pre-midnight',
    dropoffDate: D(2026, 7, 1),
    pickupDate:  D(2026, 7, 8),
    arrivalTime: '23:59',
    reqArrivalDate:          '2026-07-08',
    reqPickupDate:           '2026-07-08',
    storedPickupDate:        '2026-07-09',
    storedFlightArrivalDate: '2026-07-08',
    storedPickupTime:        '00:29',
  },
  {
    label: '01:30 Thu 9 Jul — already past midnight, no roll',
    dropoffDate: D(2026, 7, 1),
    pickupDate:  D(2026, 7, 9),
    arrivalTime: '01:30',
    reqArrivalDate:          '2026-07-09',
    reqPickupDate:           '2026-07-09',
    storedPickupDate:        '2026-07-09',
    storedFlightArrivalDate: '2026-07-09',
    storedPickupTime:        '02:00',
  },
];

// Capture state per test
const capturedReferences: string[] = [];

async function selectDateInPicker(page: Page, date: Date): Promise<void> {
  await page.waitForSelector('.react-datepicker', { timeout: 5000 });
  for (let i = 0; i < 24; i++) {
    const currentMonth = await page.locator('.react-datepicker__current-month').textContent();
    if (
      currentMonth?.includes(date.toLocaleString('en-GB', { month: 'long' })) &&
      currentMonth?.includes(date.getFullYear().toString())
    ) {
      break;
    }
    await page.locator('.react-datepicker__navigation--next').click();
    await page.waitForTimeout(150);
  }
  const dayStr = date.getDate().toString();
  const dayLocator = page.locator(
    `.react-datepicker__day:not(.react-datepicker__day--outside-month):has-text("${dayStr}")`,
  ).first();
  await dayLocator.click();
}

async function runScenario(page: Page, sc: Scenario, index: number): Promise<void> {
  const step = (msg: string) => console.log(`[${index + 1}/${scenarios.length} ${sc.arrivalTime}] ${msg}`);

  // Capture the create-intent request body + response for assertion.
  const capture: { body: any | null; reference: string | null } = { body: null, reference: null };
  page.on('request', async (req) => {
    if (req.url().includes('/api/payments/create-intent') && req.method() === 'POST') {
      try {
        capture.body = JSON.parse(req.postData() || '{}');
      } catch {
        // ignore
      }
    }
  });
  page.on('response', async (res) => {
    if (res.url().includes('/api/payments/create-intent') && res.request().method() === 'POST') {
      try {
        const json = await res.json();
        if (json?.booking_reference) capture.reference = json.booking_reference;
      } catch {
        // ignore
      }
    }
  });

  step('Navigating to /tag-it');
  await page.goto('/tag-it');
  await page.waitForLoadState('networkidle');

  step('Dismissing Welcome modal');
  const welcomeBtn = page.locator('button.welcome-modal-btn, button:has-text("Continue to booking")');
  await welcomeBtn.waitFor({ state: 'visible', timeout: 10000 });
  await welcomeBtn.click();
  await page.waitForTimeout(500);

  step(`Picking drop-off date: ${sc.dropoffDate.toDateString()}`);
  await page.locator('#dropoffDate').click();
  await selectDateInPicker(page, sc.dropoffDate);
  await page.waitForTimeout(800);

  step('Selecting departure airline');
  const airlineSelect = page.locator('#manualAirline');
  await airlineSelect.waitFor({ state: 'visible', timeout: 10000 });
  await page.waitForFunction(() => {
    const el = document.querySelector('#manualAirline') as HTMLSelectElement | null;
    return !!el && el.options.length > 2;
  }, { timeout: 10000 });
  const airlineOptions = await airlineSelect.locator('option').allTextContents();
  const realAirline = airlineOptions.find(o => o && o !== 'Select airline' && o !== 'Other');
  if (realAirline) await airlineSelect.selectOption({ label: realAirline });
  await page.waitForTimeout(300);

  step('Selecting departure destination');
  const destSelect = page.locator('#manualDestination');
  await page.waitForFunction(() => {
    const el = document.querySelector('#manualDestination') as HTMLSelectElement | null;
    return !!el && el.options.length > 2;
  }, { timeout: 10000 });
  const destOptions = await destSelect.locator('option').allTextContents();
  const realDest = destOptions.find(o => o && o !== 'Select destination' && o !== 'Other');
  if (realDest) await destSelect.selectOption({ label: realDest });
  await page.waitForTimeout(300);

  step('Entering departure time 14:30');
  await page.locator('#manualFlightTime').click();
  await page.locator('#manualFlightTime').fill('14:30');
  await page.keyboard.press('Tab');
  await page.waitForTimeout(800);

  step('Selecting drop-off slot (early)');
  const slotCards = page.locator('label.dropoff-slot');
  await slotCards.first().waitFor({ state: 'visible', timeout: 10000 });
  await slotCards.first().click();
  await page.waitForTimeout(400);

  step(`Picking return date: ${sc.pickupDate.toDateString()}`);
  const returnDatePicker = page.locator('.return-date-picker input, input[placeholder="Select return date"]');
  await returnDatePicker.click();
  await selectDateInPicker(page, sc.pickupDate);
  await page.waitForTimeout(500);

  // Return airline + origin (manual entry uses same dropdown pattern as departure)
  step('Selecting return airline');
  const returnAirlineSelect = page.locator('#manualArrivalAirline');
  if (await returnAirlineSelect.isVisible({ timeout: 2000 }).catch(() => false)) {
    await page.waitForFunction(() => {
      const el = document.querySelector('#manualArrivalAirline') as HTMLSelectElement | null;
      return !!el && el.options.length > 2;
    }, { timeout: 10000 });
    const opts = await returnAirlineSelect.locator('option').allTextContents();
    const real = opts.find(o => o && o !== 'Select airline' && o !== 'Other');
    if (real) await returnAirlineSelect.selectOption({ label: real });
    await page.waitForTimeout(300);
  }

  step('Selecting return origin');
  const returnOriginSelect = page.locator('#manualArrivalOrigin');
  if (await returnOriginSelect.isVisible({ timeout: 2000 }).catch(() => false)) {
    await page.waitForFunction(() => {
      const el = document.querySelector('#manualArrivalOrigin') as HTMLSelectElement | null;
      return !!el && el.options.length > 2;
    }, { timeout: 10000 });
    const opts = await returnOriginSelect.locator('option').allTextContents();
    const real = opts.find(o => o && o !== 'Select origin' && o !== 'Other');
    if (real) await returnOriginSelect.selectOption({ label: real });
    await page.waitForTimeout(300);
  }

  step(`Entering arrival time: ${sc.arrivalTime}`);
  const arrivalTimeInput = page.locator('#manualArrivalFlightTime');
  await arrivalTimeInput.waitFor({ state: 'visible', timeout: 10000 });
  await arrivalTimeInput.click();
  await arrivalTimeInput.fill(sc.arrivalTime);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(800);

  step('Continuing past Step 1');
  await page.locator('button.next-btn, button:has-text("Continue")').first().click();
  await page.waitForTimeout(800);

  // Time-confirmation modal — capture screenshot showing the date split.
  const timeConfirmModal = page.locator('.time-confirm-modal');
  if (await timeConfirmModal.isVisible({ timeout: 3000 }).catch(() => false)) {
    step('Time-confirm modal visible — screenshotting');
    await timeConfirmModal.screenshot({
      path: `test-results/flight-arrival-date/scenario-${index + 1}-time-confirm.png`,
    });
    const confirmBtn = page.locator('.time-confirm-btn-primary, button:has-text("Yes")').first();
    await confirmBtn.click();
    await page.waitForTimeout(500);
  } else {
    step('No time-confirm modal — continuing');
  }

  // Step 2 → Continue (package selection — auto-select default)
  step('Stepping past Step 2 (package)');
  const step2Continue = page.locator('button.next-btn, button:has-text("Continue")').first();
  if (await step2Continue.isVisible({ timeout: 3000 }).catch(() => false)) {
    await step2Continue.click();
    await page.waitForTimeout(1000);
  }

  step('Filling customer details');
  await page.locator('#firstName').fill(TEST_CUSTOMER.firstName);
  await page.locator('#lastName').fill(TEST_CUSTOMER.lastName);
  await page.locator('#email').fill(TEST_CUSTOMER.email);
  const phoneInput = page.locator('.phone-input input[type="tel"]');
  await phoneInput.click();
  await phoneInput.fill(TEST_CUSTOMER.phone);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(500);

  step('Filling billing address');
  await page.locator('#billingPostcode').fill(TEST_ADDRESS.postcode);
  await page.locator('button:has-text("Find Address")').click();
  await page.waitForTimeout(2000);
  const manualEntryBtn = page.locator('button.manual-entry-link');
  if (await manualEntryBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await manualEntryBtn.click();
    await page.waitForTimeout(300);
  }
  await page.locator('#billingAddress1').fill(TEST_ADDRESS.address1);
  await page.locator('#billingCity').fill(TEST_ADDRESS.city);
  await page.waitForTimeout(300);

  step('Vehicle lookup');
  await page.locator('#registration').fill(TEST_VEHICLE.registration);
  await page.waitForTimeout(300);
  await page.locator('button.validate-btn:has-text("Lookup")').click();
  await page.waitForTimeout(3000);

  step('Clicking Continue to Payment');
  await page.locator('button:has-text("Continue to Payment")').click();
  await page.waitForTimeout(3000);

  step('Submitting "Where did you hear about us?"');
  const heardAboutSelect = page.locator('.heard-about-us-section select');
  if (await heardAboutSelect.isVisible({ timeout: 5000 }).catch(() => false)) {
    await heardAboutSelect.selectOption('google');
    await page.waitForTimeout(300);
    const submitBtn = page.locator('button.heard-about-us-submit');
    if (await submitBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await submitBtn.click();
      await page.waitForTimeout(1500);
    }
  }

  step('Ticking T&Cs — this mounts <StripePayment> and fires /api/payments/create-intent');
  const termsCheckbox = page.locator('input[name="terms"]');
  await termsCheckbox.waitFor({ state: 'visible', timeout: 10000 });
  if (!(await termsCheckbox.isChecked())) {
    await termsCheckbox.check();
  }
  await page.waitForTimeout(500);

  // Wait for the create-intent request to actually fire and be captured.
  step('Waiting for create-intent to fire');
  await page.waitForResponse(
    (res) => res.url().includes('/api/payments/create-intent') && res.request().method() === 'POST',
    { timeout: 30000 },
  );
  // Give the handler an extra tick to populate capture.body.
  await page.waitForTimeout(1500);

  step('Verifying captured create-intent body');
  expect(capture.body, 'create-intent request body was not captured').not.toBeNull();
  expect(capture.body.flight_arrival_date, 'flight_arrival_date missing from payload').toBe(sc.reqArrivalDate);
  expect(capture.body.pickup_date, 'pickup_date in request should be un-rolled landing day for manual entry').toBe(sc.reqPickupDate);
  expect(capture.body.flight_arrival_time, 'arrival_time mismatch').toBe(sc.arrivalTime);

  if (capture.reference) {
    console.log(`[${index + 1}/${scenarios.length}] Booking reference captured: ${capture.reference}`);
    capturedReferences.push(capture.reference);
  } else {
    console.log(`[${index + 1}/${scenarios.length}] ⚠️  No booking_reference captured from response`);
  }

  console.log(
    `[${index + 1}/${scenarios.length}] PAYLOAD: ` +
    `flight_arrival_date=${capture.body.flight_arrival_date}, ` +
    `pickup_date=${capture.body.pickup_date}, ` +
    `flight_arrival_time=${capture.body.flight_arrival_time}, ` +
    `pickup_flight_time=${capture.body.pickup_flight_time}`,
  );

  // Complete payment so the booking reaches CONFIRMED status and we can
  // query the persisted row to verify the backend rollover.
  step('Waiting for Stripe form to mount');
  await page.locator('.stripe-form').waitFor({ state: 'visible', timeout: 15000 });
  await page.waitForTimeout(2000);

  step('Filling Stripe test card (4242 4242 4242 4242 / 10/65 / 321)');
  // PaymentElement renders fields inside a Stripe-hosted iframe. fill() can
  // race with Stripe's internal validation — pressSequentially with a small
  // per-character delay matches real keystrokes and gives Stripe time to
  // process each one. Each input gets an explicit waitFor + click to ensure
  // focus before keys are sent.
  const stripeFrame = page.frameLocator('iframe[title*="Secure"]').first();

  const cardInput = stripeFrame.locator('input[name="number"]');
  await cardInput.waitFor({ state: 'visible', timeout: 15000 });
  await cardInput.click();
  await cardInput.pressSequentially('4242424242424242', { delay: 60 });
  await page.waitForTimeout(600);

  const expiryInput = stripeFrame.locator('input[name="expiry"]');
  await expiryInput.waitFor({ state: 'visible', timeout: 5000 });
  await expiryInput.click();
  await expiryInput.pressSequentially('1065', { delay: 60 });
  await page.waitForTimeout(600);

  const cvcInput = stripeFrame.locator('input[name="cvc"]');
  await cvcInput.waitFor({ state: 'visible', timeout: 5000 });
  await cvcInput.click();
  await cvcInput.pressSequentially('321', { delay: 60 });
  await page.waitForTimeout(800);

  // Sanity: confirm Stripe accepted the card before clicking Pay — the
  // "Pay" button stays disabled until card data validates. Polling avoids a
  // race where pressSequentially returns before Stripe finishes validating.
  step('Waiting for Pay button to enable');
  const payBtn = page.locator('button.stripe-pay-btn');
  await expect(payBtn).toBeEnabled({ timeout: 10000 });

  step('Clicking Pay');
  await payBtn.click();

  step('Waiting for payment success');
  const successLocator = page.locator('text=Payment Successful!');
  await successLocator.waitFor({ state: 'visible', timeout: 60000 });
  console.log(`[${index + 1}/${scenarios.length}] ✅ Payment succeeded — booking confirmed`);
}

test.describe('flight_arrival_date — boundary scenarios', () => {
  for (const [i, sc] of scenarios.entries()) {
    test(`scenario ${i + 1}: ${sc.label}`, async ({ page }) => {
      await runScenario(page, sc, i);
    });
  }

  test.afterAll(async () => {
    console.log('\n=========================================');
    console.log('All scenarios complete. Booking references for DB verification:');
    capturedReferences.forEach((ref, i) => {
      const sc = scenarios[i];
      console.log(
        `  scenario ${i + 1}: ${ref}\n` +
        `    expected stored: flight_arrival_date=${sc.storedFlightArrivalDate}, ` +
        `pickup_date=${sc.storedPickupDate}, pickup_time=${sc.storedPickupTime}`,
      );
    });
    console.log('=========================================\n');
  });
});
