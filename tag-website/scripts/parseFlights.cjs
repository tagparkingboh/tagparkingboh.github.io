const XLSX = require('xlsx');
const fs = require('fs');
const path = require('path');

// Airport name to code mapping
const airportToCode = {
  'Alicante-Elche Airport': { code: 'ALC', city: 'Alicante', country: 'ES' },
  'Faro Airport': { code: 'FAO', city: 'Faro', country: 'PT' },
  'Kraków John Paul II International Airport': { code: 'KRK', city: 'Krakow', country: 'PL' },
  'Malta International Airport': { code: 'MLA', city: 'Malta', country: 'MT' },
  'Tenerife South Airport': { code: 'TFS', city: 'Tenerife-Reinasofia', country: 'ES' },
  'Fuerteventura Airport': { code: 'FUE', city: 'Fuerteventura', country: 'ES' },
  'Gran Canaria Airport': { code: 'LPA', city: 'Gran Canaria', country: 'ES' },
  'Lanzarote Airport (César Manrique-Lanzarote Airport)': { code: 'ACE', city: 'Lanzarote', country: 'ES' },
  'Málaga-Costa del Sol Airport': { code: 'AGP', city: 'Malaga', country: 'ES' },
  'Palma de Mallorca Airport': { code: 'PMI', city: 'Palma Mallorca', country: 'ES' },
  'Barcelona International Airport': { code: 'BCN', city: 'Barcelona', country: 'ES' },
  'Ibiza Airport': { code: 'IBZ', city: 'Ibiza', country: 'ES' },
  'Menorca Airport': { code: 'MAH', city: 'Menorca', country: 'ES' },
  'Reus Airport': { code: 'REU', city: 'Reus', country: 'ES' },
  'Girona Airport': { code: 'GRO', city: 'Girona', country: 'ES' },
  'Geneva Airport': { code: 'GVA', city: 'Geneva', country: 'CH' },
  'Edinburgh Airport': { code: 'EDI', city: 'Edinburgh', country: 'GB' },
  'Glasgow International Airport': { code: 'GLA', city: 'Glasgow', country: 'GB' },
  'Dublin Airport': { code: 'DUB', city: 'Dublin', country: 'IE' },
  'Shannon Airport': { code: 'SNN', city: 'Shannon', country: 'IE' },
  'Cork Airport': { code: 'ORK', city: 'Cork', country: 'IE' },
  'Václav Havel Airport Prague': { code: 'PRG', city: 'Prague', country: 'CZ' },
  'Budapest Ferenc Liszt International Airport': { code: 'BUD', city: 'Budapest', country: 'HU' },
  'Warsaw Chopin Airport': { code: 'WAW', city: 'Warsaw', country: 'PL' },
  'Nice Côte d\'Azur Airport': { code: 'NCE', city: 'Nice', country: 'FR' },
  'Paris Charles de Gaulle Airport': { code: 'CDG', city: 'Paris', country: 'FR' },
  'Amsterdam Airport Schiphol': { code: 'AMS', city: 'Amsterdam', country: 'NL' },
  'Brussels Airport': { code: 'BRU', city: 'Brussels', country: 'BE' },
  'Vienna International Airport': { code: 'VIE', city: 'Vienna', country: 'AT' },
  'Munich Airport': { code: 'MUC', city: 'Munich', country: 'DE' },
  'Frankfurt Airport': { code: 'FRA', city: 'Frankfurt', country: 'DE' },
  'Berlin Brandenburg Airport': { code: 'BER', city: 'Berlin', country: 'DE' },
  'Rome Fiumicino Airport': { code: 'FCO', city: 'Rome', country: 'IT' },
  'Milan Malpensa Airport': { code: 'MXP', city: 'Milan', country: 'IT' },
  'Venice Marco Polo Airport': { code: 'VCE', city: 'Venice', country: 'IT' },
  'Naples International Airport': { code: 'NAP', city: 'Naples', country: 'IT' },
  'Pisa International Airport': { code: 'PSA', city: 'Pisa', country: 'IT' },
  'Athens International Airport': { code: 'ATH', city: 'Athens', country: 'GR' },
  'Thessaloniki Airport': { code: 'SKG', city: 'Thessaloniki', country: 'GR' },
  'Heraklion International Airport': { code: 'HER', city: 'Heraklion', country: 'GR' },
  'Rhodes International Airport': { code: 'RHO', city: 'Rhodes', country: 'GR' },
  'Kos International Airport': { code: 'KGS', city: 'Kos', country: 'GR' },
  'Corfu International Airport': { code: 'CFU', city: 'Corfu', country: 'GR' },
  'Zakynthos International Airport': { code: 'ZTH', city: 'Zakynthos', country: 'GR' },
  'Kefalonia Airport': { code: 'EFL', city: 'Kefalonia', country: 'GR' },
  'Santorini Airport': { code: 'JTR', city: 'Santorini', country: 'GR' },
  'Mykonos Airport': { code: 'JMK', city: 'Mykonos', country: 'GR' },
  'Preveza Airport': { code: 'PVK', city: 'Preveza', country: 'GR' },
  'Istanbul Airport': { code: 'IST', city: 'Istanbul', country: 'TR' },
  'Antalya Airport': { code: 'AYT', city: 'Antalya', country: 'TR' },
  'Dalaman Airport': { code: 'DLM', city: 'Dalaman', country: 'TR' },
  'Bodrum-Milas Airport': { code: 'BJV', city: 'Bodrum', country: 'TR' },
  'Larnaca International Airport': { code: 'LCA', city: 'Larnaca', country: 'CY' },
  'Paphos International Airport': { code: 'PFO', city: 'Paphos', country: 'CY' },
  'Split Airport': { code: 'SPU', city: 'Split', country: 'HR' },
  'Dubrovnik Airport': { code: 'DBV', city: 'Dubrovnik', country: 'HR' },
  'Lisbon Airport': { code: 'LIS', city: 'Lisbon', country: 'PT' },
  'Porto Airport': { code: 'OPO', city: 'Porto', country: 'PT' },
  'Madeira Airport': { code: 'FNC', city: 'Funchal', country: 'PT' },
  'Funchal-Madeira Airport': { code: 'FNC', city: 'Funchal', country: 'PT' },
  'Cristiano Ronaldo International Airport': { code: 'FNC', city: 'Funchal', country: 'PT' },
  'Keflavík International Airport': { code: 'KEF', city: 'Reykjavik', country: 'IS' },
  'Bournemouth Airport': { code: 'BOH', city: 'Bournemouth', country: 'GB' },
  'Seville Airport': { code: 'SVQ', city: 'Seville', country: 'ES' },
  'Valencia Airport': { code: 'VLC', city: 'Valencia', country: 'ES' },
  'Murcia Airport': { code: 'RMU', city: 'Murcia', country: 'ES' },
  'Murcia International Airport': { code: 'RMU', city: 'Murcia', country: 'ES' },
  'Region de Murcia International Airport': { code: 'RMU', city: 'Murcia', country: 'ES' },
  'Bilbao Airport': { code: 'BIO', city: 'Bilbao', country: 'ES' },
  'Asturias Airport': { code: 'OVD', city: 'Asturias', country: 'ES' },
  'Seville San Pablo Airport': { code: 'SVQ', city: 'Seville', country: 'ES' },
  'Jerez Airport': { code: 'XRY', city: 'Jerez', country: 'ES' },
  'Almería Airport': { code: 'LEI', city: 'Almeria', country: 'ES' },
  'Santiago de Compostela Airport': { code: 'SCQ', city: 'Santiago', country: 'ES' },
  'La Palma Airport': { code: 'SPC', city: 'La Palma', country: 'ES' },
  'Tenerife North Airport': { code: 'TFN', city: 'Tenerife North', country: 'ES' },
  'Enfidha-Hammamet International Airport': { code: 'NBE', city: 'Enfidha', country: 'TN' },
  'Marrakech Menara Airport': { code: 'RAK', city: 'Marrakech', country: 'MA' },
  'Agadir Al Massira Airport': { code: 'AGA', city: 'Agadir', country: 'MA' },
  'Sharm El Sheikh International Airport': { code: 'SSH', city: 'Sharm El Sheikh', country: 'EG' },
  'Hurghada International Airport': { code: 'HRG', city: 'Hurghada', country: 'EG' },
  'Katowice Airport': { code: 'KTW', city: 'Katowice', country: 'PL' },
  'Wrocław Airport': { code: 'WRO', city: 'Wroclaw', country: 'PL' },
  'Poznań Airport': { code: 'POZ', city: 'Poznan', country: 'PL' },
  'Gdańsk Lech Wałęsa Airport': { code: 'GDN', city: 'Gdansk', country: 'PL' },
  'Riga International Airport': { code: 'RIX', city: 'Riga', country: 'LV' },
  'Vilnius Airport': { code: 'VNO', city: 'Vilnius', country: 'LT' },
  'Tallinn Airport': { code: 'TLL', city: 'Tallinn', country: 'EE' },
  'Oslo Airport': { code: 'OSL', city: 'Oslo', country: 'NO' },
  'Stockholm Arlanda Airport': { code: 'ARN', city: 'Stockholm', country: 'SE' },
  'Copenhagen Airport': { code: 'CPH', city: 'Copenhagen', country: 'DK' },
  'Helsinki Airport': { code: 'HEL', city: 'Helsinki', country: 'FI' },
  'Rzeszów-Jasionka Airport': { code: 'RZE', city: 'Rzeszow', country: 'PL' },
  'Szczecin-Goleniów Airport': { code: 'SZZ', city: 'Szczecin', country: 'PL' },
  'Knock Airport': { code: 'NOC', city: 'Knock', country: 'IE' },
  'Belfast International Airport': { code: 'BFS', city: 'Belfast', country: 'GB' },
  'Newcastle Airport': { code: 'NCL', city: 'Newcastle', country: 'GB' },
  'Inverness Airport': { code: 'INV', city: 'Inverness', country: 'GB' },
  'Verona Villafranca Airport': { code: 'VRN', city: 'Verona', country: 'IT' },
  'Catania-Fontanarossa Airport': { code: 'CTA', city: 'Catania', country: 'IT' },
  'Palermo Airport': { code: 'PMO', city: 'Palermo', country: 'IT' },
  'Bari Karol Wojtyła Airport': { code: 'BRI', city: 'Bari', country: 'IT' },
  'Brindisi Airport': { code: 'BDS', city: 'Brindisi', country: 'IT' },
  'Olbia Costa Smeralda Airport': { code: 'OLB', city: 'Olbia', country: 'IT' },
  'Cagliari Elmas Airport': { code: 'CAG', city: 'Cagliari', country: 'IT' },
  'Alghero-Fertilia Airport': { code: 'AHO', city: 'Alghero', country: 'IT' },
  'Trieste – Friuli Venezia Giulia Airport': { code: 'TRS', city: 'Trieste', country: 'IT' },
  'Bologna Guglielmo Marconi Airport': { code: 'BLQ', city: 'Bologna', country: 'IT' },
  'Turin Airport': { code: 'TRN', city: 'Turin', country: 'IT' },
  'Genoa Airport': { code: 'GOA', city: 'Genoa', country: 'IT' },
  'Perugia San Francesco d\'Assisi – Umbria International Airport': { code: 'PEG', city: 'Perugia', country: 'IT' },
  'Ancona Airport': { code: 'AOI', city: 'Ancona', country: 'IT' },
  'Rimini Federico Fellini International Airport': { code: 'RMI', city: 'Rimini', country: 'IT' },
  'Trapani-Birgi Airport': { code: 'TPS', city: 'Trapani', country: 'IT' },
  'Zante Airport': { code: 'ZTH', city: 'Zakynthos', country: 'GR' },
  'Izmir Adnan Menderes Airport': { code: 'ADB', city: 'Izmir', country: 'TR' },
  'Skiathos Airport': { code: 'JSI', city: 'Skiathos', country: 'GR' },
  'Chania International Airport': { code: 'CHQ', city: 'Chania', country: 'GR' },
  'Kalamata International Airport': { code: 'KLX', city: 'Kalamata', country: 'GR' },
  'Pula Airport': { code: 'PUY', city: 'Pula', country: 'HR' },
  'Zadar Airport': { code: 'ZAD', city: 'Zadar', country: 'HR' },
  'Ljubljana Jože Pučnik Airport': { code: 'LJU', city: 'Ljubljana', country: 'SI' },
  'Salzburg Airport': { code: 'SZG', city: 'Salzburg', country: 'AT' },
  'Innsbruck Airport': { code: 'INN', city: 'Innsbruck', country: 'AT' },
  'Zurich Airport': { code: 'ZRH', city: 'Zurich', country: 'CH' },
  'Basel-Mulhouse-Freiburg Airport': { code: 'BSL', city: 'Basel', country: 'CH' },
  'Lyon–Saint-Exupéry Airport': { code: 'LYS', city: 'Lyon', country: 'FR' },
  'Marseille Provence Airport': { code: 'MRS', city: 'Marseille', country: 'FR' },
  'Toulouse-Blagnac Airport': { code: 'TLS', city: 'Toulouse', country: 'FR' },
  'Bordeaux–Mérignac Airport': { code: 'BOD', city: 'Bordeaux', country: 'FR' },
  'Nantes Atlantique Airport': { code: 'NTE', city: 'Nantes', country: 'FR' },
  'Montpellier–Méditerranée Airport': { code: 'MPL', city: 'Montpellier', country: 'FR' },
  'Béziers Cap d\'Agde Airport': { code: 'BZR', city: 'Beziers', country: 'FR' },
  'Carcassonne Airport': { code: 'CCF', city: 'Carcassonne', country: 'FR' },
  'Perpignan–Rivesaltes Airport': { code: 'PGF', city: 'Perpignan', country: 'FR' },
  'Biarritz Pays Basque Airport': { code: 'BIQ', city: 'Biarritz', country: 'FR' },
  'La Rochelle – Île de Ré Airport': { code: 'LRH', city: 'La Rochelle', country: 'FR' },
  'Bergerac Dordogne Périgord Airport': { code: 'EGC', city: 'Bergerac', country: 'FR' },
  'Limoges – Bellegarde Airport': { code: 'LIG', city: 'Limoges', country: 'FR' },
  'Grenoble Alpes Isère Airport': { code: 'GNB', city: 'Grenoble', country: 'FR' },
  'Chambéry Airport': { code: 'CMF', city: 'Chambery', country: 'FR' },
  'Tarbes-Lourdes-Pyrénées Airport': { code: 'LDE', city: 'Lourdes', country: 'FR' },
  'Avignon – Provence Airport': { code: 'AVN', city: 'Avignon', country: 'FR' },
  'Dinard-Pleurtuit-Saint-Malo Airport': { code: 'DNR', city: 'Dinard', country: 'FR' },
  'Figari–Sud Corse Airport': { code: 'FSC', city: 'Figari', country: 'FR' },
  'Ajaccio Napoleon Bonaparte Airport': { code: 'AJA', city: 'Ajaccio', country: 'FR' },
  'Bastia – Poretta Airport': { code: 'BIA', city: 'Bastia', country: 'FR' },
  'Calvi-Sainte-Catherine Airport': { code: 'CLY', city: 'Calvi', country: 'FR' },
};

// Airline code extraction
function extractAirlineInfo(airlineString) {
  if (!airlineString) return { code: '', name: '' };
  const parts = airlineString.split(' : ');
  return {
    code: parts[0]?.trim() || '',
    name: parts[1]?.trim() || airlineString
  };
}

// Get airport info - try to match the airport name
function getAirportInfo(airportName) {
  if (!airportName) return null;

  // Direct match
  if (airportToCode[airportName]) {
    return airportToCode[airportName];
  }

  // Try partial match
  const lowerName = airportName.toLowerCase();
  for (const [name, info] of Object.entries(airportToCode)) {
    if (lowerName.includes(name.toLowerCase().split(' ')[0]) ||
        name.toLowerCase().includes(lowerName.split(' ')[0])) {
      return info;
    }
  }

  console.warn('Unknown airport:', airportName);
  return null;
}

// Format time - handle Excel serial numbers or string times
function formatTime(timeValue) {
  if (typeof timeValue === 'number') {
    // Excel time serial - multiply by 24 hours
    const totalMinutes = Math.round(timeValue * 24 * 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
  }
  if (typeof timeValue === 'string') {
    // Already a string, just return it
    return timeValue;
  }
  return null;
}

// Read the Excel file
const workbook = XLSX.readFile(path.join(__dirname, '../src/Bournemouth_Flight_Schedule_1 week model.xlsx'));
const worksheet = workbook.Sheets[workbook.SheetNames[0]];
const data = XLSX.utils.sheet_to_json(worksheet, { header: 1 });

// Filter dates: Feb 1, 2026 to May 31, 2026
const startDate = new Date('2026-02-01');
const endDate = new Date('2026-05-31');

const flights = [];
const unknownAirports = new Set();

// Skip header rows (rows 0-3)
for (let i = 4; i < data.length; i++) {
  const row = data[i];
  if (!row || !row[0]) continue;

  // Parse date
  let dateStr = row[0];
  if (typeof dateStr === 'number') {
    // Excel date serial number
    const date = XLSX.SSF.parse_date_code(dateStr);
    dateStr = `${date.y}-${String(date.m).padStart(2, '0')}-${String(date.d).padStart(2, '0')}`;
  }

  const rowDate = new Date(dateStr);
  if (isNaN(rowDate.getTime())) continue;

  // Check if within date range
  if (rowDate < startDate || rowDate > endDate) continue;

  const type = row[2]?.toLowerCase();
  if (type !== 'arrival' && type !== 'departure') continue;

  const airlineInfo = extractAirlineInfo(row[3]);
  const flightNumber = row[9]?.toString();
  const depTime = formatTime(row[20]);
  const arrTime = formatTime(row[21]);

  if (type === 'departure') {
    // Departure: from Bournemouth to destination (column 7)
    const destAirport = getAirportInfo(row[7]);
    if (!destAirport) {
      unknownAirports.add(row[7]);
      continue;
    }

    flights.push({
      date: dateStr,
      type: 'departure',
      time: depTime,
      airlineCode: airlineInfo.code,
      airlineName: airlineInfo.name,
      destinationCode: destAirport.code,
      destinationName: `${destAirport.city}, ${destAirport.country}`,
      flightNumber: flightNumber
    });
  } else {
    // Arrival: from origin (column 6) to Bournemouth
    const originAirport = getAirportInfo(row[6]);
    if (!originAirport) {
      unknownAirports.add(row[6]);
      continue;
    }

    flights.push({
      date: dateStr,
      type: 'arrival',
      time: arrTime, // Arrival time at Bournemouth
      airlineCode: airlineInfo.code,
      airlineName: airlineInfo.name,
      originCode: originAirport.code,
      originName: `${originAirport.city}, ${originAirport.country}`,
      flightNumber: flightNumber,
      departureTime: depTime // When flight departed from origin
    });
  }
}

// Sort flights by date then time
flights.sort((a, b) => {
  const dateCompare = a.date.localeCompare(b.date);
  if (dateCompare !== 0) return dateCompare;
  return (a.time || '').localeCompare(b.time || '');
});

// Write output
const outputPath = path.join(__dirname, '../src/data/flightSchedule.json');
fs.writeFileSync(outputPath, JSON.stringify(flights, null, 2));

console.log(`\nProcessed ${flights.length} flights`);
console.log(`Output written to: ${outputPath}`);

if (unknownAirports.size > 0) {
  console.log('\nUnknown airports (need to add mappings):');
  for (const airport of unknownAirports) {
    console.log(`  - ${airport}`);
  }
}

// Stats
const departures = flights.filter(f => f.type === 'departure');
const arrivals = flights.filter(f => f.type === 'arrival');
console.log(`\nStats:`);
console.log(`  Departures: ${departures.length}`);
console.log(`  Arrivals: ${arrivals.length}`);

// Show sample output
console.log('\nSample departure:');
console.log(JSON.stringify(departures[0], null, 2));
console.log('\nSample arrival:');
console.log(JSON.stringify(arrivals[0], null, 2));
