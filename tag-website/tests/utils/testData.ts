/**
 * Test Data for TAG Parking E2E Tests
 */

/**
 * Test customer data
 */
export const testCustomers = {
  valid: {
    firstName: 'John',
    lastName: 'Test',
    email: 'john.test@example.com',
    phone: '7700900000',
    countryCode: 'GB',
  },
  alternateEmail: {
    firstName: 'Jane',
    lastName: 'Automation',
    email: 'jane.automation@test.com',
    phone: '7700900001',
    countryCode: 'GB',
  },
  invalidEmail: {
    firstName: 'Invalid',
    lastName: 'Email',
    email: 'not-an-email',
    phone: '7700900002',
    countryCode: 'GB',
  },
};

/**
 * Test vehicle data
 */
export const testVehicles = {
  valid: {
    registration: 'TE57 VRN',
    make: 'Ford',
    model: 'Focus',
    colour: 'Blue',
  },
  bmw: {
    registration: 'AB12 CDE',
    make: 'BMW',
    model: '3 Series',
    colour: 'Black',
  },
  mercedes: {
    registration: 'XY19 ZZZ',
    make: 'Mercedes',
    model: 'A-Class',
    colour: 'Silver',
  },
  custom: {
    registration: 'CU51 TOM',
    make: 'Other',
    customMake: 'Tesla',
    model: 'Other',
    customModel: 'Model 3',
    colour: 'White',
  },
};

/**
 * Test billing addresses
 */
export const testAddresses = {
  uk: {
    postcode: 'BH23 6AA',
    address1: '1 Test Street',
    address2: 'Test Area',
    city: 'Christchurch',
    county: 'Dorset',
    country: 'United Kingdom',
  },
  london: {
    postcode: 'SW1A 1AA',
    address1: '10 Downing Street',
    address2: '',
    city: 'London',
    county: 'Greater London',
    country: 'United Kingdom',
  },
  manual: {
    postcode: 'TE5T 1NG',
    address1: '123 Manual Entry Lane',
    address2: 'Suite 100',
    city: 'Test Town',
    county: 'Test County',
    country: 'United Kingdom',
  },
};

/**
 * Test promo codes (staging environment only)
 * These are reusable unlimited-use codes created specifically for E2E testing.
 *
 * Discount Types:
 * - 'percentage': Standard percentage discount (e.g., 10% off total price)
 * - 'free_week': "1 Week Free Parking" - deducts week1_price (free for ≤7 days, partial for >7 days)
 * - 'free_100': "100% Off" - completely free regardless of trip length
 */
export const testPromoCodes = {
  // ---- PERCENTAGE TYPE ----
  // 10% discount - can be used unlimited times
  tenPercent: 'TEST10',
  // 20% discount (if available)
  twentyPercent: 'TEST20',

  // ---- FREE_WEEK TYPE ----
  // 100% discount but only deducts week1 price for trips > 7 days
  // - Free for stays ≤7 days
  // - Deducts £79 (week1 price) for longer stays, customer pays remainder
  freeWeek: 'FREEWEEK',

  // ---- FREE_100 TYPE ----
  // 100% discount - completely free regardless of trip length
  // - Free for ALL trip durations (1-60 days)
  free100: 'FREE100',

  // ---- INVALID CODES ----
  invalid: 'INVALIDCODE123',
  expired: 'EXPIRED2023',

  // ---- LEGACY CODES ----
  // Legacy codes from marketing_subscribers table (may not exist in staging)
  legacy: 'TESTCODE',
};

/**
 * Expected behavior for each promo code type by trip duration
 */
export const promoCodeExpectations = {
  percentage: {
    type: 'percentage',
    description: 'Standard percentage discount',
    shortTrip: { isFree: false, discountCalculation: '10% of total' },
    longTrip: { isFree: false, discountCalculation: '10% of total' },
  },
  freeWeek: {
    type: 'free_week',
    description: '1 Week Free - deducts week1 price',
    shortTrip: { isFree: true, discountCalculation: '100% (full amount)' },
    longTrip: { isFree: false, discountCalculation: '£79 (week1 price) deducted' },
  },
  free100: {
    type: 'free_100',
    description: '100% Off - always free',
    shortTrip: { isFree: true, discountCalculation: '100% (full amount)' },
    longTrip: { isFree: true, discountCalculation: '100% (full amount)' },
  },
};

/**
 * Stripe test cards
 * See: https://stripe.com/docs/testing#cards
 */
export const stripeTestCards = {
  success: {
    number: '4242424242424242',
    expiry: '12/30',
    cvc: '123',
    zip: '12345',
  },
  decline: {
    number: '4000000000000002',
    expiry: '12/30',
    cvc: '123',
    zip: '12345',
  },
  insufficientFunds: {
    number: '4000000000009995',
    expiry: '12/30',
    cvc: '123',
    zip: '12345',
  },
  authRequired: {
    number: '4000002500003155',
    expiry: '12/30',
    cvc: '123',
    zip: '12345',
  },
  expiredCard: {
    number: '4000000000000069',
    expiry: '12/30',
    cvc: '123',
    zip: '12345',
  },
};

/**
 * Generate future dates for testing
 * @param daysFromNow - Days from now for drop-off
 * @param tripDuration - Duration of trip in days (default 7)
 */
export function generateTestDates(daysFromNow: number = 14, tripDuration: number = 7) {
  const dropoffDate = new Date();
  dropoffDate.setDate(dropoffDate.getDate() + daysFromNow);

  const pickupDate = new Date(dropoffDate);
  pickupDate.setDate(pickupDate.getDate() + tripDuration);

  return {
    dropoffDate,
    pickupDate,
    formattedDropoff: formatDate(dropoffDate),
    formattedPickup: formatDate(pickupDate),
    tripDuration,
  };
}

/**
 * Find next occurrence of a specific day of week
 * @param dayOfWeek - 0=Sunday, 1=Monday, ..., 6=Saturday
 * @param fromDate - Start searching from this date
 */
export function findNextDayOfWeek(dayOfWeek: number, fromDate: Date = new Date()): Date {
  const result = new Date(fromDate);
  result.setDate(result.getDate() + 14); // Start at least 2 weeks out
  while (result.getDay() !== dayOfWeek) {
    result.setDate(result.getDate() + 1);
  }
  return result;
}

/**
 * Generate dates for peak day pricing tests
 * Peak days: Drop-off on Fri/Sat OR Pick-up on Sun/Mon/Tue
 */
export function generatePeakDayDates() {
  // Find next Friday for drop-off (peak day)
  const fridayDropoff = findNextDayOfWeek(5); // Friday
  const fridayPickup = new Date(fridayDropoff);
  fridayPickup.setDate(fridayPickup.getDate() + 7);

  // Find next Saturday for drop-off (peak day)
  const saturdayDropoff = findNextDayOfWeek(6); // Saturday
  const saturdayPickup = new Date(saturdayDropoff);
  saturdayPickup.setDate(saturdayPickup.getDate() + 7);

  // Find dates where pickup falls on Sunday (peak day)
  const sundayPickup = findNextDayOfWeek(0); // Sunday
  const sundayDropoff = new Date(sundayPickup);
  sundayDropoff.setDate(sundayDropoff.getDate() - 7);

  // Find dates where pickup falls on Monday (peak day)
  const mondayPickup = findNextDayOfWeek(1); // Monday
  const mondayDropoff = new Date(mondayPickup);
  mondayDropoff.setDate(mondayDropoff.getDate() - 7);

  // Non-peak: Wednesday drop-off, Thursday pickup
  const wednesdayDropoff = findNextDayOfWeek(3); // Wednesday
  const thursdayPickup = new Date(wednesdayDropoff);
  thursdayPickup.setDate(thursdayPickup.getDate() + 8); // 8 days = Thu

  return {
    peakDropoffFriday: {
      dropoffDate: fridayDropoff,
      pickupDate: fridayPickup,
      formattedDropoff: formatDate(fridayDropoff),
      formattedPickup: formatDate(fridayPickup),
      isPeakDay: true,
      reason: 'Drop-off on Friday',
    },
    peakDropoffSaturday: {
      dropoffDate: saturdayDropoff,
      pickupDate: saturdayPickup,
      formattedDropoff: formatDate(saturdayDropoff),
      formattedPickup: formatDate(saturdayPickup),
      isPeakDay: true,
      reason: 'Drop-off on Saturday',
    },
    peakPickupSunday: {
      dropoffDate: sundayDropoff,
      pickupDate: sundayPickup,
      formattedDropoff: formatDate(sundayDropoff),
      formattedPickup: formatDate(sundayPickup),
      isPeakDay: true,
      reason: 'Pick-up on Sunday',
    },
    peakPickupMonday: {
      dropoffDate: mondayDropoff,
      pickupDate: mondayPickup,
      formattedDropoff: formatDate(mondayDropoff),
      formattedPickup: formatDate(mondayPickup),
      isPeakDay: true,
      reason: 'Pick-up on Monday',
    },
    nonPeak: {
      dropoffDate: wednesdayDropoff,
      pickupDate: thursdayPickup,
      formattedDropoff: formatDate(wednesdayDropoff),
      formattedPickup: formatDate(thursdayPickup),
      isPeakDay: false,
      reason: 'Mid-week (Wed drop-off, Thu pickup)',
    },
  };
}

/**
 * Generate dates for pricing tier boundary tests
 * Early: >14 days before
 * Standard: 7-14 days before
 * Late: <7 days before
 */
export function generateTierBoundaryDates() {
  const now = new Date();

  // Early tier: 15 days from now
  const earlyDropoff = new Date(now);
  earlyDropoff.setDate(earlyDropoff.getDate() + 15);
  const earlyPickup = new Date(earlyDropoff);
  earlyPickup.setDate(earlyPickup.getDate() + 7);

  // Standard tier: 10 days from now
  const standardDropoff = new Date(now);
  standardDropoff.setDate(standardDropoff.getDate() + 10);
  const standardPickup = new Date(standardDropoff);
  standardPickup.setDate(standardPickup.getDate() + 7);

  // Late tier: 5 days from now
  const lateDropoff = new Date(now);
  lateDropoff.setDate(lateDropoff.getDate() + 5);
  const latePickup = new Date(lateDropoff);
  latePickup.setDate(latePickup.getDate() + 7);

  // Boundary: exactly 14 days (should be Standard)
  const boundary14Dropoff = new Date(now);
  boundary14Dropoff.setDate(boundary14Dropoff.getDate() + 14);
  const boundary14Pickup = new Date(boundary14Dropoff);
  boundary14Pickup.setDate(boundary14Pickup.getDate() + 7);

  // Boundary: exactly 7 days (should be Late)
  const boundary7Dropoff = new Date(now);
  boundary7Dropoff.setDate(boundary7Dropoff.getDate() + 7);
  const boundary7Pickup = new Date(boundary7Dropoff);
  boundary7Pickup.setDate(boundary7Pickup.getDate() + 7);

  return {
    early: {
      dropoffDate: earlyDropoff,
      pickupDate: earlyPickup,
      formattedDropoff: formatDate(earlyDropoff),
      formattedPickup: formatDate(earlyPickup),
      tier: 'early',
      daysUntilDropoff: 15,
    },
    standard: {
      dropoffDate: standardDropoff,
      pickupDate: standardPickup,
      formattedDropoff: formatDate(standardDropoff),
      formattedPickup: formatDate(standardPickup),
      tier: 'standard',
      daysUntilDropoff: 10,
    },
    late: {
      dropoffDate: lateDropoff,
      pickupDate: latePickup,
      formattedDropoff: formatDate(lateDropoff),
      formattedPickup: formatDate(latePickup),
      tier: 'late',
      daysUntilDropoff: 5,
    },
    boundary14Days: {
      dropoffDate: boundary14Dropoff,
      pickupDate: boundary14Pickup,
      formattedDropoff: formatDate(boundary14Dropoff),
      formattedPickup: formatDate(boundary14Pickup),
      tier: 'standard', // At exactly 14 days, should be standard
      daysUntilDropoff: 14,
    },
    boundary7Days: {
      dropoffDate: boundary7Dropoff,
      pickupDate: boundary7Pickup,
      formattedDropoff: formatDate(boundary7Dropoff),
      formattedPickup: formatDate(boundary7Pickup),
      tier: 'late', // At exactly 7 days, should be late
      daysUntilDropoff: 7,
    },
  };
}

/**
 * Format date as DD/MM/YYYY
 */
export function formatDate(date: Date): string {
  const day = date.getDate().toString().padStart(2, '0');
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const year = date.getFullYear();
  return `${day}/${month}/${year}`;
}

/**
 * Generate a random email for testing
 */
export function generateRandomEmail(): string {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substring(7);
  return `test.${timestamp}.${random}@automation.test`;
}

/**
 * Generate a random UK phone number
 */
export function generateRandomPhone(): string {
  const suffix = Math.floor(Math.random() * 9000000) + 1000000;
  return `77${suffix}`;
}

/**
 * Complete booking test data
 */
export interface BookingTestData {
  customer: typeof testCustomers.valid;
  vehicle: typeof testVehicles.valid;
  billing: typeof testAddresses.uk;
  dates: ReturnType<typeof generateTestDates>;
  package: 'hand-wash' | 'valet' | 'none';
  promoCode?: string;
}

/**
 * Get default booking test data
 */
export function getDefaultBookingData(): BookingTestData {
  return {
    customer: testCustomers.valid,
    vehicle: testVehicles.valid,
    billing: testAddresses.uk,
    dates: generateTestDates(14),
    package: 'none',
  };
}

/**
 * Get booking data with specific configuration
 */
export function getBookingData(options: Partial<BookingTestData> = {}): BookingTestData {
  return {
    ...getDefaultBookingData(),
    ...options,
  };
}
