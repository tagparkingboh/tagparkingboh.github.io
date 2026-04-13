import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Billing Details Page Object Model
 * Step 4 (or Step 5): Enter billing address
 */
export class BillingDetailsPage extends BasePage {
  // Postcode lookup
  readonly postcodeInput: Locator;
  readonly lookupButton: Locator;
  readonly addressSelect: Locator;
  readonly manualEntryLink: Locator;

  // Address fields
  readonly address1Input: Locator;
  readonly address2Input: Locator;
  readonly cityInput: Locator;
  readonly countyInput: Locator;
  readonly countrySelect: Locator;

  // Form validation
  readonly postcodeError: Locator;
  readonly address1Error: Locator;
  readonly cityError: Locator;

  constructor(page: Page) {
    super(page);

    // Postcode lookup
    this.postcodeInput = page.locator('input[name="billingPostcode"], input[name="postcode"], input[placeholder*="postcode"], input[placeholder*="Postcode"]');
    this.lookupButton = page.locator('button:has-text("Find Address"), button:has-text("Lookup"), button:has-text("Search")');
    this.addressSelect = page.locator('select[name="addressSelect"], .address-dropdown, select:has-text("Select an address")');
    this.manualEntryLink = page.locator('button:has-text("Enter manually"), a:has-text("Enter manually"), .manual-entry');

    // Address fields
    this.address1Input = page.locator('input[name="billingAddress1"], input[name="address1"], input[placeholder*="Address line 1"]');
    this.address2Input = page.locator('input[name="billingAddress2"], input[name="address2"], input[placeholder*="Address line 2"]');
    this.cityInput = page.locator('input[name="billingCity"], input[name="city"], input[placeholder*="City"], input[placeholder*="Town"]');
    this.countyInput = page.locator('input[name="billingCounty"], input[name="county"], input[placeholder*="County"]');
    this.countrySelect = page.locator('select[name="billingCountry"], select[name="country"]');

    // Form validation errors
    this.postcodeError = page.locator('[data-error="postcode"], .postcode-error');
    this.address1Error = page.locator('[data-error="address1"], .address1-error');
    this.cityError = page.locator('[data-error="city"], .city-error');
  }

  /**
   * Enter postcode
   */
  async enterPostcode(postcode: string) {
    await this.postcodeInput.clear();
    await this.postcodeInput.fill(postcode);
  }

  /**
   * Click lookup button and wait for addresses
   */
  async lookupAddress() {
    await this.lookupButton.click();
    await this.waitForLoadingComplete();
    await this.page.waitForTimeout(1500);
  }

  /**
   * Enter postcode and lookup address
   */
  async enterAndLookupPostcode(postcode: string) {
    await this.enterPostcode(postcode);
    await this.lookupAddress();
  }

  /**
   * Select an address from the dropdown by index
   */
  async selectAddressByIndex(index: number) {
    await this.addressSelect.selectOption({ index });
    await this.page.waitForTimeout(500);
  }

  /**
   * Select an address from the dropdown by partial text match
   */
  async selectAddressByText(partialText: string) {
    const options = await this.addressSelect.locator('option').all();
    for (let i = 0; i < options.length; i++) {
      const text = await options[i].textContent();
      if (text?.includes(partialText)) {
        await this.addressSelect.selectOption({ index: i });
        break;
      }
    }
  }

  /**
   * Click manual entry link
   */
  async clickManualEntry() {
    await this.manualEntryLink.click();
    await this.page.waitForTimeout(300);
  }

  /**
   * Enter address line 1
   */
  async enterAddress1(address1: string) {
    await this.address1Input.clear();
    await this.address1Input.fill(address1);
  }

  /**
   * Enter address line 2
   */
  async enterAddress2(address2: string) {
    await this.address2Input.clear();
    await this.address2Input.fill(address2);
  }

  /**
   * Enter city/town
   */
  async enterCity(city: string) {
    await this.cityInput.clear();
    await this.cityInput.fill(city);
  }

  /**
   * Enter county
   */
  async enterCounty(county: string) {
    await this.countyInput.clear();
    await this.countyInput.fill(county);
  }

  /**
   * Select country from dropdown
   */
  async selectCountry(country: string) {
    await this.countrySelect.selectOption({ label: country });
  }

  /**
   * Get the entered postcode
   */
  async getPostcode(): Promise<string> {
    return await this.postcodeInput.inputValue();
  }

  /**
   * Get the entered address line 1
   */
  async getAddress1(): Promise<string> {
    return await this.address1Input.inputValue();
  }

  /**
   * Get the entered city
   */
  async getCity(): Promise<string> {
    return await this.cityInput.inputValue();
  }

  /**
   * Check if address dropdown is visible
   */
  async isAddressDropdownVisible(): Promise<boolean> {
    return await this.addressSelect.isVisible({ timeout: 2000 }).catch(() => false);
  }

  /**
   * Get number of addresses in dropdown
   */
  async getAddressCount(): Promise<number> {
    if (!(await this.isAddressDropdownVisible())) return 0;
    const options = await this.addressSelect.locator('option').count();
    return Math.max(0, options - 1); // Exclude placeholder option
  }

  /**
   * Verify billing details step is displayed
   */
  async verifyStepDisplayed() {
    await expect(this.postcodeInput).toBeVisible();
  }

  /**
   * Complete billing details using postcode lookup
   */
  async completeBillingWithLookup(postcode: string, addressIndex: number = 1) {
    await this.enterAndLookupPostcode(postcode);

    // Wait for and select from address dropdown
    if (await this.isAddressDropdownVisible()) {
      await this.selectAddressByIndex(addressIndex);
    }
  }

  /**
   * Complete billing details manually
   */
  async completeBillingManually(billingData: {
    address1: string;
    address2?: string;
    city: string;
    county?: string;
    postcode: string;
    country?: string;
  }) {
    // Try to click manual entry if available
    if (await this.manualEntryLink.isVisible({ timeout: 1000 }).catch(() => false)) {
      await this.clickManualEntry();
    }

    await this.enterPostcode(billingData.postcode);
    await this.enterAddress1(billingData.address1);

    if (billingData.address2) {
      await this.enterAddress2(billingData.address2);
    }

    await this.enterCity(billingData.city);

    if (billingData.county) {
      await this.enterCounty(billingData.county);
    }

    if (billingData.country) {
      await this.selectCountry(billingData.country);
    }
  }
}
