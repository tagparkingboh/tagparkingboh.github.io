// Shared utilities for Admin pages

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Photo slots - must match Employee.jsx
export const PHOTO_SLOTS = [
  { key: 'front', label: 'Front' },
  { key: 'rear', label: 'Rear' },
  { key: 'driver_side', label: 'Driver Side' },
  { key: 'passenger_side', label: 'Passenger Side' },
  { key: 'additional_1', label: 'Additional 1' },
  { key: 'additional_2', label: 'Additional 2' },
]

// UK date format helpers (DD/MM/YYYY)
export const isoToUkDate = (isoDate) => {
  if (!isoDate) return ''
  const [year, month, day] = isoDate.split('-')
  return `${day}/${month}/${year}`
}

export const ukToIsoDate = (ukDate) => {
  if (!ukDate) return ''
  const parts = ukDate.split('/')
  if (parts.length !== 3) return ''
  const [day, month, year] = parts
  return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`
}

// Format marketing source for display
export const formatMarketingSource = (source) => {
  if (!source) return '-'
  const sourceMap = {
    'google': 'Google',
    'facebook': 'Facebook',
    'instagram': 'Instagram',
    'linkedin': 'LinkedIn',
    'newspaper': 'Newspaper',
    'afc_bournemouth': 'AFC Bournemouth',
    'word_of_mouth': 'Word of mouth',
    'other': 'Other',
  }
  return sourceMap[source] || source
}

// Test email domains to filter out
export const testEmailDomains = ['yopmail.com', 'mailinator.com', 'guerrillamail.com', 'tempmail.com', 'fakeinbox.com', 'test.com', 'example.com', 'staging.tag.com']

export const isTestEmail = (email) => {
  if (!email) return false
  const domain = email.toLowerCase().split('@')[1]
  return testEmailDomains.includes(domain) || domain?.includes('test') || domain?.includes('staging')
}

// Group items by month (for bookings, leads, etc.)
export const groupByMonth = (items, dateField = 'dropoff_date') => {
  const groups = {}

  items.forEach(item => {
    const dateStr = item[dateField]
    if (!dateStr) return

    // Parse the date directly to avoid timezone issues
    const [year, month] = dateStr.split('-')
    const monthKey = `${year}-${month}`
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    const monthLabel = `${monthNames[parseInt(month) - 1]} ${year}`

    if (!groups[monthKey]) {
      groups[monthKey] = { label: monthLabel, items: [] }
    }
    groups[monthKey].items.push(item)
  })

  return groups
}

// Format date for display (DD Mon YYYY) - parse directly to avoid timezone issues
export const formatDateDisplay = (isoDate) => {
  if (!isoDate) return ''
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const parts = isoDate.split('-')
  if (parts.length !== 3) return isoDate
  const year = parts[0]
  const monthIndex = parseInt(parts[1], 10) - 1
  const day = parts[2]
  return `${parseInt(day)} ${monthNames[monthIndex]} ${year}`
}
