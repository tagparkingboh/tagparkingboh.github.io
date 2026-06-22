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

function normaliseText(value: string | null | undefined): string {
  return value?.replace(/\s+/g, ' ').trim() || '';
}

export function parseMoneyToPence(value: string): number | null {
  const cleaned = value.replace(/,/g, '').match(/£?\s*(\d+(?:\.\d{1,2})?)/);
  if (!cleaned) return null;

  return Math.round(Number.parseFloat(cleaned[1]) * 100);
}

function findProductName(priceElement: Element, index: number): string {
  const container = priceElement.closest(PRODUCT_CONTAINER_SELECTOR);
  const namedElement = container?.querySelector(PRODUCT_NAME_SELECTOR);
  const name = normaliseText(namedElement?.textContent);

  return name || `Bournemouth Airport product ${index + 1}`;
}

function nameFromOptionsText(container: Element, index: number): string {
  const optionsText = normaliseText(container.querySelector('.item__options')?.textContent);
  const match = optionsText.match(/Options\s+(.+?)\s+£/);
  if (match?.[1]) return match[1].replace(/\s+Flex$/, '').trim();

  const cardText = normaliseText(container.textContent);
  const cardMatch = cardText.match(/Options\s+(.+?)\s+£/);
  if (cardMatch?.[1]) return cardMatch[1].replace(/\s+Flex$/, '').trim();

  return `Bournemouth Airport product ${index + 1}`;
}

function parseProductGroups(documentLike: Document): AirportParkingProduct[] {
  const groups = Array.from(documentLike.querySelectorAll('.product-group__item-container'));
  if (groups.length === 0) return [];

  return groups
    .map((group, index) => {
      const priceElement = group.querySelector('.item__options-price');
      const priceText = normaliseText(priceElement?.textContent);
      const pricePence = parseMoneyToPence(priceText);

      if (pricePence == null) return null;

      return {
        name: nameFromOptionsText(group, index),
        pricePence,
        priceText,
      };
    })
    .filter((product): product is AirportParkingProduct => product !== null);
}

export function parseBournemouthAirportProducts(documentLike: Document): AirportParkingProduct[] {
  const groupedProducts = parseProductGroups(documentLike);
  if (groupedProducts.length > 0) return groupedProducts;

  return Array.from(documentLike.querySelectorAll(PRICE_SELECTOR))
    .map((priceElement, index) => {
      const priceText = normaliseText(priceElement.textContent);
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
