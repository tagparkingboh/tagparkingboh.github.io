import { chromium, type Browser, type Page } from 'playwright';
import {
  parseBournemouthAirportProducts,
  type AirportParkingProduct,
} from './bournemouthAirportQuoteParser.ts';

const AIRPORT_COLLECT_URL =
  'https://book.bournemouthairport.com/book/BOH/Parking?parkingCmd=collectParkingDetails';
const AIRPORT_SELECT_PRODUCT_URL_PART = 'parkingCmd=selectProduct';
const AIRPORT_TIME_OPTIONS = [
  '00:01',
  ...Array.from({ length: 47 }, (_, index) => {
    const totalMinutes = 30 * (index + 1);
    const hours = Math.floor(totalMinutes / 60).toString().padStart(2, '0');
    const minutes = (totalMinutes % 60).toString().padStart(2, '0');
    return `${hours}:${minutes}`;
  }),
  '23:59',
];

export interface BournemouthAirportQuoteRequest {
  entryDate: string;
  entryTime: string;
  exitDate: string;
  exitTime: string;
  destinationId?: string;
  headless?: boolean;
  timeoutMs?: number;
}

export interface BournemouthAirportQuoteResult {
  requested: BournemouthAirportQuoteRequest;
  products: AirportParkingProduct[];
  quotedAt: string;
  sourceUrl: string;
}

function isoDateToAirportDate(value: string): string {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;

  return `${match[3]}/${match[2]}/${match[1]}`;
}

function minutesFromTime(value: string): number {
  const [hours, minutes] = value.split(':').map(Number);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    throw new Error(`Invalid time: ${value}`);
  }

  return hours * 60 + minutes;
}

export function normaliseAirportTime(value: string, direction: 'floor' | 'ceil'): string {
  if (AIRPORT_TIME_OPTIONS.includes(value)) return value;

  const requestedMinutes = minutesFromTime(value);
  const optionMinutes = AIRPORT_TIME_OPTIONS.map(minutesFromTime);

  if (direction === 'floor') {
    for (let index = optionMinutes.length - 1; index >= 0; index -= 1) {
      if (optionMinutes[index] <= requestedMinutes) return AIRPORT_TIME_OPTIONS[index];
    }

    return AIRPORT_TIME_OPTIONS[0];
  }

  for (let index = 0; index < optionMinutes.length; index += 1) {
    if (optionMinutes[index] >= requestedMinutes) return AIRPORT_TIME_OPTIONS[index];
  }

  return AIRPORT_TIME_OPTIONS[AIRPORT_TIME_OPTIONS.length - 1];
}

async function setReadonlyDate(page: Page, selector: string, value: string): Promise<void> {
  await page.locator(selector).waitFor({ state: 'attached' });
  await page.locator(selector).evaluate((input, args) => {
    if (!(input instanceof HTMLInputElement)) {
      throw new Error(`${args.selector} did not resolve to an input`);
    }

    input.value = args.value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, { selector, value });
}

async function submitParkingSearch(page: Page, request: BournemouthAirportQuoteRequest): Promise<void> {
  await page.goto(AIRPORT_COLLECT_URL, { waitUntil: 'domcontentloaded' });

  await setReadonlyDate(page, '#changeEntryDate', isoDateToAirportDate(request.entryDate));
  await page.locator('#changeEntryTime').selectOption(normaliseAirportTime(request.entryTime, 'ceil'));

  await setReadonlyDate(page, '#changeExitDate', isoDateToAirportDate(request.exitDate));
  await page.locator('#changeExitTime').selectOption(normaliseAirportTime(request.exitTime, 'ceil'));
  await page.locator('#selectDestination').selectOption(request.destinationId || '2182');

  await Promise.all([
    page.waitForLoadState('domcontentloaded'),
    page.locator('form').first().evaluate((form) => {
      if (!(form instanceof HTMLFormElement)) {
        throw new Error('Parking search form not found');
      }

      form.submit();
    }),
  ]);

  try {
    await page.locator('.item__price__val, .item__options-price').first().waitFor({
      state: 'attached',
      timeout: 15_000,
    });
  } catch {
    const bodyText = await page.locator('body').innerText();
    throw new Error(
      `Bournemouth Airport did not return product prices: ${bodyText.replace(/\s+/g, ' ').slice(0, 300)}`,
    );
  }
}

export async function fetchBournemouthAirportQuote(
  request: BournemouthAirportQuoteRequest,
): Promise<BournemouthAirportQuoteResult> {
  let browser: Browser | null = null;
  const timeoutMs = request.timeoutMs ?? 30_000;

  try {
    browser = await chromium.launch({
      headless: request.headless ?? true,
    });
    const page = await browser.newPage();
    page.setDefaultTimeout(timeoutMs);
    page.setDefaultNavigationTimeout(timeoutMs);

    await submitParkingSearch(page, request);
    await page.locator('.item__price__val').first().waitFor({ state: 'attached' });

    const products = await page.evaluate(() => {
      const parser = (window as typeof window & {
        __parseBournemouthAirportProducts?: () => AirportParkingProduct[];
      }).__parseBournemouthAirportProducts;

      if (parser) return parser();

      const moneyToPence = (value: string) => {
        const match = value.replace(/,/g, '').match(/£?\s*(\d+(?:\.\d{1,2})?)/);
        return match ? Math.round(Number.parseFloat(match[1]) * 100) : 0;
      };
      const normaliseText = (value: string | null | undefined) => value?.replace(/\s+/g, ' ').trim() || '';
      const groups = Array.from(document.querySelectorAll('.product-group__item-container'));

      if (groups.length > 0) {
        return groups.map((group, index) => {
          const priceElement = group.querySelector('.item__options-price');
          const priceText = normaliseText(priceElement?.textContent);
          const optionsText = normaliseText(group.querySelector('.item__options')?.textContent);
          const name = optionsText.match(/Options\s+(.+?)\s+£/)?.[1]?.replace(/\s+Flex$/, '').trim()
            || `Bournemouth Airport product ${index + 1}`;

          return {
            name,
            pricePence: moneyToPence(priceText),
            priceText,
          };
        }).filter((product) => product.pricePence > 0);
      }

      return Array.from(document.querySelectorAll('.item__price__val')).map((priceElement, index) => {
        const priceText = priceElement.textContent?.replace(/\s+/g, ' ').trim() || '';
        const container = priceElement.closest('.item, .product, .parking-product, li, article, section');
        const namedElement = container?.querySelector(
          '.item__title, .item__name, .product__title, .product-title, h2, h3, h4',
        );
        const name = namedElement?.textContent?.replace(/\s+/g, ' ').trim()
          || `Bournemouth Airport product ${index + 1}`;

        return {
          name,
          pricePence: moneyToPence(priceText),
          priceText,
        };
      }).filter((product) => product.pricePence > 0);
    });

    return {
      requested: request,
      products,
      quotedAt: new Date().toISOString(),
      sourceUrl: page.url(),
    };
  } finally {
    await browser?.close();
  }
}

function readCliArg(name: string): string | undefined {
  const prefix = `--${name}=`;
  return process.argv.find((arg) => arg.startsWith(prefix))?.slice(prefix.length);
}

async function main(): Promise<void> {
  const entryDate = readCliArg('entry-date');
  const entryTime = readCliArg('entry-time') || '06:00';
  const exitDate = readCliArg('exit-date');
  const exitTime = readCliArg('exit-time') || '06:00';
  const destinationId = readCliArg('destination-id');

  if (!entryDate || !exitDate) {
    throw new Error(
      'Usage: npm run quote:bournemouth -- --entry-date=2026-07-06 --entry-time=06:00 --exit-date=2026-07-13 --exit-time=22:00',
    );
  }

  const result = await fetchBournemouthAirportQuote({
    entryDate,
    entryTime,
    exitDate,
    exitTime,
    destinationId,
    headless: readCliArg('headed') !== 'true',
  });

  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}

export { parseBournemouthAirportProducts };
