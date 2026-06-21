export interface AirportParkingProduct {
  name: string;
  pricePence: number;
  priceText: string;
}

const PRICE_SELECTOR = '.item__price__val';
const PRODUCT_CONTAINER_SELECTOR = '.item, .product, .parking-product, li, article, section';
const PRODUCT_NAME_SELECTOR = [
  '.item__title',
  '.item__name',
  '.product__title',
  '.product-title',
  'h2',
  'h3',
  'h4',
].join(', ');

export function parseMoneyToPence(value: string): number | null {
  const cleaned = value.replace(/,/g, '').match(/£?\s*(\d+(?:\.\d{1,2})?)/);
  if (!cleaned) return null;

  return Math.round(Number.parseFloat(cleaned[1]) * 100);
}

function findProductName(priceElement: Element, index: number): string {
  const container = priceElement.closest(PRODUCT_CONTAINER_SELECTOR);
  const namedElement = container?.querySelector(PRODUCT_NAME_SELECTOR);
  const name = namedElement?.textContent?.replace(/\s+/g, ' ').trim();

  return name || `Bournemouth Airport product ${index + 1}`;
}

export function parseBournemouthAirportProducts(documentLike: Document): AirportParkingProduct[] {
  return Array.from(documentLike.querySelectorAll(PRICE_SELECTOR))
    .map((priceElement, index) => {
      const priceText = priceElement.textContent?.replace(/\s+/g, ' ').trim() || '';
      const pricePence = parseMoneyToPence(priceText);

      if (pricePence == null) return null;

      return {
        name: findProductName(priceElement, index),
        pricePence,
        priceText,
      };
    })
    .filter((product): product is AirportParkingProduct => product !== null);
}
