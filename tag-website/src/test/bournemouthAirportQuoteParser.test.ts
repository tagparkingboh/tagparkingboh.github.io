import { describe, expect, it } from 'vitest';
import {
  parseBournemouthAirportProducts,
  parseMoneyToPence,
} from '../../tools/airport-quotes/bournemouthAirportQuoteParser';

describe('Bournemouth airport quote parser', () => {
  it('parses the airport price spans into pence', () => {
    document.body.innerHTML = `
      <article class="item">
        <h3>Car Park 7</h3>
        <span class="item__price__val 7">£148.05</span>
      </article>
      <article class="item">
        <h3>Car Park 5</h3>
        <span class="item__price__val 5">£149.94</span>
      </article>
      <article class="item">
        <h3>Car Park 1</h3>
        <span class="item__price__val 1">£169.20</span>
      </article>
      <article class="item">
        <h3>Premium</h3>
        <span class="item__price__val 3">£255.00</span>
      </article>
    `;

    expect(parseBournemouthAirportProducts(document)).toEqual([
      { name: 'Car Park 7', pricePence: 14805, priceText: '£148.05' },
      { name: 'Car Park 5', pricePence: 14994, priceText: '£149.94' },
      { name: 'Car Park 1', pricePence: 16920, priceText: '£169.20' },
      { name: 'Premium', pricePence: 25500, priceText: '£255.00' },
    ]);
  });

  it('ignores non-money price nodes', () => {
    document.body.innerHTML = `
      <article class="item">
        <h3>Unavailable product</h3>
        <span class="item__price__val">Sold out</span>
      </article>
    `;

    expect(parseBournemouthAirportProducts(document)).toEqual([]);
  });

  it('handles comma-formatted values', () => {
    expect(parseMoneyToPence('£1,234.50')).toBe(123450);
  });
});
