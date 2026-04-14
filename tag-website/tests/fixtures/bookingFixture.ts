import { test as base, Page } from '@playwright/test';
import {
  FlightSelectionPage,
  VehicleDetailsPage,
  CustomerDetailsPage,
  BillingDetailsPage,
  PaymentPage,
  ConfirmationPage,
} from '../pages';
import { BookingTestData, getDefaultBookingData } from '../utils/testData';

/**
 * Custom test fixtures for TAG Parking E2E tests
 * Provides pre-instantiated page objects for each test
 */

// Define the fixture types
type BookingFixtures = {
  flightSelectionPage: FlightSelectionPage;
  vehicleDetailsPage: VehicleDetailsPage;
  customerDetailsPage: CustomerDetailsPage;
  billingDetailsPage: BillingDetailsPage;
  paymentPage: PaymentPage;
  confirmationPage: ConfirmationPage;
  testData: BookingTestData;
};

/**
 * Extended test with all page object fixtures
 */
export const test = base.extend<BookingFixtures>({
  flightSelectionPage: async ({ page }, use) => {
    const flightSelectionPage = new FlightSelectionPage(page);
    await use(flightSelectionPage);
  },

  vehicleDetailsPage: async ({ page }, use) => {
    const vehicleDetailsPage = new VehicleDetailsPage(page);
    await use(vehicleDetailsPage);
  },

  customerDetailsPage: async ({ page }, use) => {
    const customerDetailsPage = new CustomerDetailsPage(page);
    await use(customerDetailsPage);
  },

  billingDetailsPage: async ({ page }, use) => {
    const billingDetailsPage = new BillingDetailsPage(page);
    await use(billingDetailsPage);
  },

  paymentPage: async ({ page }, use) => {
    const paymentPage = new PaymentPage(page);
    await use(paymentPage);
  },

  confirmationPage: async ({ page }, use) => {
    const confirmationPage = new ConfirmationPage(page);
    await use(confirmationPage);
  },

  testData: async ({}, use) => {
    const testData = getDefaultBookingData();
    await use(testData);
  },
});

export { expect } from '@playwright/test';

/**
 * Helper function to complete booking up to a specific step
 * Useful for tests that need to start from a specific step
 */
export async function navigateToStep(
  page: Page,
  targetStep: 'vehicle' | 'customer' | 'billing' | 'payment',
  testData: BookingTestData = getDefaultBookingData()
) {
  const flightPage = new FlightSelectionPage(page);
  const vehiclePage = new VehicleDetailsPage(page);
  const customerPage = new CustomerDetailsPage(page);
  const billingPage = new BillingDetailsPage(page);

  // Start at homepage
  await flightPage.navigateToBooking();
  await flightPage.clickTagIt();

  // Complete flight selection
  await flightPage.completeFlightSelection(
    testData.dates.dropoffDate,
    testData.dates.pickupDate
  );
  await flightPage.clickNext();

  if (targetStep === 'vehicle') return;

  // Complete vehicle details
  await vehiclePage.completeVehicleDetails({
    registration: testData.vehicle.registration,
    package: testData.package,
    promoCode: testData.promoCode,
  });
  await vehiclePage.clickNext();

  if (targetStep === 'customer') return;

  // Complete customer details
  await customerPage.completeCustomerDetails({
    firstName: testData.customer.firstName,
    lastName: testData.customer.lastName,
    email: testData.customer.email,
    phone: testData.customer.phone,
  });
  await customerPage.clickNext();

  if (targetStep === 'billing') return;

  // Complete billing details
  await billingPage.completeBillingWithLookup(testData.billing.postcode);
  await billingPage.clickNext();

  // Now at payment step
}

/**
 * Complete an entire booking flow
 */
export async function completeFullBooking(
  page: Page,
  testData: BookingTestData = getDefaultBookingData(),
  paymentType: 'success' | 'decline' = 'success'
) {
  await navigateToStep(page, 'payment', testData);

  const paymentPage = new PaymentPage(page);
  await paymentPage.completePayment(paymentType);

  return new ConfirmationPage(page);
}
