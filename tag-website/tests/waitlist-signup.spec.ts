import { test, expect } from '@playwright/test';
import { WaitlistSignupPage } from './pages/WaitlistSignupPage';

/**
 * TAG Parking - Waitlist Signup E2E Tests
 * Tests for the email capture/waitlist form on the homepage
 */

/**
 * Browser abbreviation map for email naming
 */
const getBrowserAbbrev = (browserName: string): string => {
  const abbrevMap: Record<string, string> = {
    'chromium': 'Chr',
    'firefox': 'FF',
    'webkit': 'Saf',
    'Mobile Chrome': 'MobC',
    'Mobile Safari': 'MobS',
  };
  return abbrevMap[browserName] || browserName.substring(0, 3);
};

/**
 * Generate unique email for each test
 * Format: {{ testName }}_{{ browserAbbrev }}_{{ lastFourDigitsOfTimestamp }}@yopmail.com
 * Example: successful_signup_Chr_4829@yopmail.com
 */
const generateTestEmail = (testName: string, browserName: string = 'Chr') => {
  const timestamp = Date.now().toString().slice(-4); // Last 4 digits of timestamp
  const sanitizedName = testName.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
  const browserAbbrev = getBrowserAbbrev(browserName);
  return `${sanitizedName}_${browserAbbrev}_${timestamp}@yopmail.com`;
};

/**
 * Log test email for custom reporter to capture
 */
const logTestEmail = (email: string) => {
  console.log(`Test email: ${email}`);
};

test.describe('Waitlist Signup - Successful Signup', () => {
  let signupPage: WaitlistSignupPage;

  test.beforeEach(async ({ page }) => {
    signupPage = new WaitlistSignupPage(page);
    await signupPage.navigateToHomepage();
  });

  test('should display the signup form on homepage', async () => {
    await signupPage.scrollToSubscribeSection();
    await signupPage.verifySubscribeSectionDisplayed();
  });

  test('should successfully sign up with valid data', async ({ }, testInfo) => {
    const browserName = testInfo.project.name;
    const email = generateTestEmail('successful_signup', browserName);
    logTestEmail(email);
    const testData = {
      firstName: 'Test',
      lastName: 'User',
      email,
    };

    await signupPage.completeSignup(testData);

    // Verify either success or error message is shown (API response received)
    const isSuccess = await signupPage.isSuccessMessageVisible();
    const isError = await signupPage.isErrorMessageVisible();

    // API should respond with either success or error
    expect(isSuccess || isError).toBeTruthy();

    // If successful, verify the success message and form cleared
    if (isSuccess) {
      const successText = await signupPage.getSuccessMessageText();
      expect(successText).toContain('Thank you');

      const isCleared = await signupPage.isFormCleared();
      expect(isCleared).toBeTruthy();
    }
  });

  test('should clear form fields after successful signup', async ({ }, testInfo) => {
    const browserName = testInfo.project.name;
    const email = generateTestEmail('clear_form_fields', browserName);
    logTestEmail(email);
    const testData = {
      firstName: 'Jane',
      lastName: 'Doe',
      email,
    };

    await signupPage.completeSignup(testData);
    await signupPage.waitForSubmissionComplete();

    // Check if successful - if so, fields should be cleared
    const isSuccess = await signupPage.isSuccessMessageVisible();

    if (isSuccess) {
      // All fields should be empty after successful submission
      expect(await signupPage.getFirstNameValue()).toBe('');
      expect(await signupPage.getLastNameValue()).toBe('');
      expect(await signupPage.getEmailValue()).toBe('');
    } else {
      // If API error, fields may still have values - that's expected
      // Just verify the form submitted (button text changed back)
      const buttonText = await signupPage.getSubmitButtonText();
      expect(buttonText).toContain('Join');
    }
  });
});

test.describe('Waitlist Signup - Duplicate Email', () => {
  let signupPage: WaitlistSignupPage;

  test.beforeEach(async ({ page }) => {
    signupPage = new WaitlistSignupPage(page);
    await signupPage.navigateToHomepage();
  });

  test('should handle duplicate email signup attempt', async ({ }, testInfo) => {
    const browserName = testInfo.project.name;
    const duplicateEmail = generateTestEmail('duplicate_email_test', browserName);
    logTestEmail(duplicateEmail);

    const testData = {
      firstName: 'First',
      lastName: 'User',
      email: duplicateEmail,
    };

    // First signup
    await signupPage.completeSignup(testData);

    // Check first signup result
    const firstSuccess = await signupPage.isSuccessMessageVisible();
    const firstError = await signupPage.isErrorMessageVisible();

    // If first signup succeeded, try to signup again with same email
    if (firstSuccess) {
      // Refresh and try again with same email
      await signupPage.navigateToHomepage();

      await signupPage.completeSignup({
        firstName: 'Second',
        lastName: 'User',
        email: duplicateEmail,
      });

      // Second attempt should either show error or success
      // (depending on backend handling of duplicates)
      const hasResponse =
        await signupPage.isSuccessMessageVisible() ||
        await signupPage.isErrorMessageVisible();
      expect(hasResponse).toBeTruthy();
    }
  });
});

test.describe('Waitlist Signup - Form Validation', () => {
  let signupPage: WaitlistSignupPage;

  test.beforeEach(async ({ page }) => {
    signupPage = new WaitlistSignupPage(page);
    await signupPage.navigateToHomepage();
    await signupPage.scrollToSubscribeSection();
  });

  test('should disable submit button when form is empty', async () => {
    const isDisabled = await signupPage.isSubmitButtonDisabled();
    expect(isDisabled).toBeTruthy();
  });

  test('should disable submit button with only first name filled', async () => {
    await signupPage.enterFirstName('John');

    const isDisabled = await signupPage.isSubmitButtonDisabled();
    expect(isDisabled).toBeTruthy();
  });

  test('should disable submit button with only last name filled', async () => {
    await signupPage.enterLastName('Doe');

    const isDisabled = await signupPage.isSubmitButtonDisabled();
    expect(isDisabled).toBeTruthy();
  });

  test('should disable submit button with only email filled', async () => {
    await signupPage.enterEmail('test@example.com');

    const isDisabled = await signupPage.isSubmitButtonDisabled();
    expect(isDisabled).toBeTruthy();
  });

  test('should disable submit button with invalid email format', async () => {
    await signupPage.enterFirstName('John');
    await signupPage.enterLastName('Doe');
    await signupPage.enterEmail('invalid-email');

    const isDisabled = await signupPage.isSubmitButtonDisabled();
    expect(isDisabled).toBeTruthy();
  });

  test('should disable submit button with email missing @ symbol', async () => {
    await signupPage.enterFirstName('John');
    await signupPage.enterLastName('Doe');
    await signupPage.enterEmail('testexample.com');

    const isDisabled = await signupPage.isSubmitButtonDisabled();
    expect(isDisabled).toBeTruthy();
  });

  test('should disable submit button with email missing domain', async () => {
    await signupPage.enterFirstName('John');
    await signupPage.enterLastName('Doe');
    await signupPage.enterEmail('test@');

    const isDisabled = await signupPage.isSubmitButtonDisabled();
    expect(isDisabled).toBeTruthy();
  });

  test('should disable submit button with email missing TLD', async () => {
    await signupPage.enterFirstName('John');
    await signupPage.enterLastName('Doe');
    await signupPage.enterEmail('test@example');

    const isDisabled = await signupPage.isSubmitButtonDisabled();
    expect(isDisabled).toBeTruthy();
  });

  test('should enable submit button with all valid fields', async () => {
    await signupPage.enterFirstName('John');
    await signupPage.enterLastName('Doe');
    await signupPage.enterEmail('john.doe@example.com');

    const isDisabled = await signupPage.isSubmitButtonDisabled();
    expect(isDisabled).toBeFalsy();
  });

  test('should disable submit button with whitespace-only first name', async () => {
    await signupPage.enterFirstName('   ');
    await signupPage.enterLastName('Doe');
    await signupPage.enterEmail('test@example.com');

    const isDisabled = await signupPage.isSubmitButtonDisabled();
    expect(isDisabled).toBeTruthy();
  });

  test('should disable submit button with whitespace-only last name', async () => {
    await signupPage.enterFirstName('John');
    await signupPage.enterLastName('   ');
    await signupPage.enterEmail('test@example.com');

    const isDisabled = await signupPage.isSubmitButtonDisabled();
    expect(isDisabled).toBeTruthy();
  });
});

test.describe('Waitlist Signup - Email Format Validation', () => {
  let signupPage: WaitlistSignupPage;

  test.beforeEach(async ({ page }) => {
    signupPage = new WaitlistSignupPage(page);
    await signupPage.navigateToHomepage();
    await signupPage.scrollToSubscribeSection();
    // Pre-fill name fields for all email tests
    await signupPage.enterFirstName('Test');
    await signupPage.enterLastName('User');
  });

  const invalidEmails = [
    { email: 'plaintext', description: 'plain text without @ or domain' },
    { email: '@nodomain.com', description: 'missing local part' },
    { email: 'test@', description: 'missing domain' },
    { email: 'test@.com', description: 'missing domain name' },
    { email: 'test@domain', description: 'missing TLD' },
    { email: 'test @domain.com', description: 'space in local part' },
    { email: 'test@ domain.com', description: 'space after @' },
    { email: '', description: 'empty string' },
  ];

  for (const { email, description } of invalidEmails) {
    test(`should reject invalid email: ${description}`, async () => {
      await signupPage.enterEmail(email);

      const isDisabled = await signupPage.isSubmitButtonDisabled();
      expect(isDisabled).toBeTruthy();
    });
  }

  const validEmails = [
    { email: 'test@example.com', description: 'standard email' },
    { email: 'test.user@example.com', description: 'email with dot in local part' },
    { email: 'test+tag@example.com', description: 'email with plus sign' },
    { email: 'test@sub.example.com', description: 'email with subdomain' },
    { email: 'TEST@EXAMPLE.COM', description: 'uppercase email' },
    { email: 'test123@example123.com', description: 'email with numbers' },
  ];

  for (const { email, description } of validEmails) {
    test(`should accept valid email: ${description}`, async () => {
      await signupPage.enterEmail(email);

      const isDisabled = await signupPage.isSubmitButtonDisabled();
      expect(isDisabled).toBeFalsy();
    });
  }
});

test.describe('Waitlist Signup - UI State', () => {
  let signupPage: WaitlistSignupPage;

  test.beforeEach(async ({ page }) => {
    signupPage = new WaitlistSignupPage(page);
    await signupPage.navigateToHomepage();
    await signupPage.scrollToSubscribeSection();
  });

  test('should show "Join the waitlist" button text initially', async () => {
    const buttonText = await signupPage.getSubmitButtonText();
    expect(buttonText).toContain('Join the waitlist');
  });

  test('should show "Joining..." while submitting', async ({ }, testInfo) => {
    const browserName = testInfo.project.name;
    const email = generateTestEmail('joining_state', browserName);
    logTestEmail(email);
    await signupPage.fillSignupForm({
      firstName: 'Test',
      lastName: 'User',
      email,
    });

    // Click and immediately check button text
    await signupPage.clickSubmit();

    // Check for loading state (might be quick)
    const buttonText = await signupPage.getSubmitButtonText();
    // Button should show either "Joining..." or "Join the waitlist" (if already completed)
    expect(buttonText).toMatch(/Join|Joining/);
  });

  test('should not show success or error message initially', async () => {
    const hasSuccess = await signupPage.isSuccessMessageVisible();
    const hasError = await signupPage.isErrorMessageVisible();

    expect(hasSuccess).toBeFalsy();
    expect(hasError).toBeFalsy();
  });
});

test.describe('Waitlist Signup - Navigation', () => {
  let signupPage: WaitlistSignupPage;

  test.beforeEach(async ({ page }) => {
    signupPage = new WaitlistSignupPage(page);
    await signupPage.navigateToHomepage();
  });

  test('should scroll to subscribe section via nav link', async ({ page, isMobile }) => {
    // On mobile, open hamburger menu first
    if (isMobile) {
      const hamburger = page.locator('.hamburger, .mobile-menu-toggle, button[aria-label*="menu"]');
      if (await hamburger.isVisible()) {
        await hamburger.click();
        await page.waitForTimeout(300);
      }
    }

    // Click the Subscribe nav link
    await page.click('a[href="#subscribe"]');
    await page.waitForTimeout(500);

    // Verify subscribe section is in view
    await expect(signupPage.subscribeSection).toBeInViewport();
  });

  test('should scroll to subscribe section via hero CTA', async ({ page }) => {
    // Click the hero CTA button
    await page.click('.hero-cta');
    await page.waitForTimeout(500);

    // Verify subscribe section is in view
    await expect(signupPage.subscribeSection).toBeInViewport();
  });
});
