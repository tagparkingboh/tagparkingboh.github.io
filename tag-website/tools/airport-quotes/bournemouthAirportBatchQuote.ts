import { readFile, writeFile } from 'node:fs/promises';
import { fetchBournemouthAirportQuote, type BournemouthAirportQuoteRequest } from './bournemouthAirportQuote.ts';

interface BatchQuoteInput extends BournemouthAirportQuoteRequest {
  reference: string;
  tagPaidPence?: number;
  destination?: string;
}

function readCliArg(name: string): string | undefined {
  const prefix = `--${name}=`;
  return process.argv.find((arg) => arg.startsWith(prefix))?.slice(prefix.length);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main(): Promise<void> {
  const inputPath = readCliArg('input');
  const outputPath = readCliArg('output');
  const delayMs = Number.parseInt(readCliArg('delay-ms') || '750', 10);

  if (!inputPath) {
    throw new Error('Usage: node --experimental-strip-types tools/airport-quotes/bournemouthAirportBatchQuote.ts --input=/tmp/quotes.json');
  }

  const rows = JSON.parse(await readFile(inputPath, 'utf8')) as BatchQuoteInput[];
  const results = [];

  for (const row of rows) {
    try {
      const quote = await fetchBournemouthAirportQuote({
        entryDate: row.entryDate,
        entryTime: row.entryTime,
        exitDate: row.exitDate,
        exitTime: row.exitTime,
        destinationId: row.destinationId,
        headless: true,
      });

      results.push({
        reference: row.reference,
        destination: row.destination,
        tagPaidPence: row.tagPaidPence,
        requested: quote.requested,
        products: quote.products,
        lowestAirportPence: quote.products.length
          ? Math.min(...quote.products.map((product) => product.pricePence))
          : null,
        quotedAt: quote.quotedAt,
      });
    } catch (error) {
      results.push({
        reference: row.reference,
        destination: row.destination,
        tagPaidPence: row.tagPaidPence,
        requested: row,
        error: error instanceof Error ? error.message : String(error),
      });
    }

    if (delayMs > 0) await sleep(delayMs);
  }

  const body = `${JSON.stringify(results, null, 2)}\n`;
  if (outputPath) {
    await writeFile(outputPath, body);
    process.stderr.write(`Wrote ${results.length} quote results to ${outputPath}\n`);
  } else {
    process.stdout.write(body);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
