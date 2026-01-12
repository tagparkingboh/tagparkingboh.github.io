import '@testing-library/jest-dom'

// Mock window.gtag for Google Analytics
window.gtag = vi.fn()

// Mock window.scrollTo
window.scrollTo = vi.fn()

// Mock fetch globally
global.fetch = vi.fn()

// Reset mocks before each test
beforeEach(() => {
  vi.clearAllMocks()
})
