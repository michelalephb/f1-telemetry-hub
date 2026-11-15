// Host country (as Jolpica names it) to ISO 3166 alpha 2. Covers every country that has hosted
// or is scheduled to host a championship round, so new calendars need no change.
export const COUNTRY_ISO: Record<string, string> = {
  Argentina: 'AR', Australia: 'AU', Austria: 'AT', Azerbaijan: 'AZ', Bahrain: 'BH', Belgium: 'BE', Brazil: 'BR',
  Canada: 'CA', China: 'CN', France: 'FR', Germany: 'DE', Hungary: 'HU', India: 'IN', Italy: 'IT', Japan: 'JP',
  Korea: 'KR', 'South Korea': 'KR', Malaysia: 'MY', Mexico: 'MX', Monaco: 'MC', Morocco: 'MA', Netherlands: 'NL',
  Portugal: 'PT', Qatar: 'QA', Russia: 'RU', 'Saudi Arabia': 'SA', Singapore: 'SG', 'South Africa': 'ZA',
  Spain: 'ES', Sweden: 'SE', Switzerland: 'CH', Thailand: 'TH', Turkey: 'TR', 'Türkiye': 'TR', UAE: 'AE',
  'United Arab Emirates': 'AE', UK: 'GB', 'United Kingdom': 'GB', 'Great Britain': 'GB', USA: 'US',
  'United States': 'US', Vietnam: 'VN', Rwanda: 'RW',
}

export const flagIso = (country: string | null | undefined) => (country ? COUNTRY_ISO[country] ?? null : null)
