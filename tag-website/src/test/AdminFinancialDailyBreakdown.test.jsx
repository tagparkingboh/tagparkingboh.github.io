/**
 * Render tests for the daily carets inside the financial Monthly Breakdown
 * (ReportsSectionPage.jsx, Reports → Financial).
 *
 * An expanded month no longer lists every booking row flat — bookings are
 * grouped by paid date under clickable day rows so a single transaction can
 * be found without scanning ~300 rows:
 *  - each day renders a header row with date, booking count and Paid/Revenue totals
 *  - booking rows are hidden until the day is expanded
 *  - the Refunds total only appears on days that have a refund
 *  - clicking the day row again collapses it
 */
import { describe, it, expect, afterEach } from 'vitest'
import { render, fireEvent, cleanup } from '@testing-library/react'
import ReportsSectionPage from '../components/admin/reports/ReportsSectionPage'

const makeBooking = (overrides = {}) => ({
  id: 1,
  reference: 'TAG-AAA11111',
  paidDate: '01/07/2026',
  paidDateSort: '2026-07-01',
  customerName: 'Jon Burt',
  tripDays: 7,
  grossPrice: '£95.81',
  grossPence: 9581,
  promoCode: 'JULY10',
  discountPercent: 10,
  discountAmount: '£9.58',
  discountPence: 958,
  netPrice: '£86.23',
  netPence: 8623,
  refundAmount: null,
  refundPence: 0,
  netRevenue: '£86.23',
  finalRevenuePence: 8623,
  status: 'confirmed',
  paymentStatus: 'paid',
  needsOverride: false,
  hasOverride: false,
  bookingSource: 'online',
  canEditFinancials: true,
  ...overrides,
})

// Two bookings on 01/07 (one with a refund), one on 02/07 — sorted ASC like the API
const bookings = [
  makeBooking(),
  makeBooking({
    id: 2,
    reference: 'TAG-BBB22222',
    customerName: 'Craig Parker',
    refundAmount: '£10.00',
    refundPence: 1000,
    netRevenue: '£76.23',
    finalRevenuePence: 7623,
    paymentStatus: 'partially_refunded',
  }),
  makeBooking({
    id: 3,
    reference: 'TAG-CCC33333',
    customerName: 'Gemma Mcdowell',
    paidDate: '02/07/2026',
    paidDateSort: '2026-07-02',
  }),
]

const financialData = {
  summary: {
    totalBookings: 3,
    totalGross: '£287.43',
    totalDiscount: '£28.74',
    totalNet: '£258.69',
    totalRefunds: '£10.00',
    totalRevenue: '£248.69',
  },
  monthlyData: [
    {
      monthKey: '2026-07',
      monthLabel: 'July 2026',
      bookingCount: 3,
      totalGross: '£287.43',
      totalDiscount: '£28.74',
      totalNet: '£258.69',
      totalRefunds: '£10.00',
      totalRevenue: '£248.69',
      bookings,
    },
  ],
}

const noop = () => {}

function renderFinancial() {
  return render(
    <ReportsSectionPage
      activeTab="reports"
      reportsSubTab="financial"
      loadingFinancial={false}
      financialData={financialData}
      expandedFinancialMonths={{ '2026-07': true }}
      setExpandedFinancialMonths={noop}
      editingFinancialBooking={null}
      setEditingFinancialBooking={noop}
      saveFinancialOverride={noop}
      savingFinancialOverride={false}
      fetchFinancialReport={noop}
      exportFinancialCSV={noop}
      exportingFinancial={false}
      financialFromDate=""
      setFinancialFromDate={noop}
      financialToDate=""
      setFinancialToDate={noop}
      financialStatusFilter="all"
      setFinancialStatusFilter={noop}
      financialPromoFilter="all"
      setFinancialPromoFilter={noop}
      formatDateInput={(v) => v}
      parseUkDate={() => null}
      dateToUkString={() => ''}
      revenueChartType="monthly"
      setRevenueChartType={noop}
      revenueWeeklyPageIndex={0}
      setRevenueWeeklyPageIndex={noop}
      expandedRevenueDailyMonths={{}}
      setExpandedRevenueDailyMonths={noop}
    />
  )
}

describe('Financial Monthly Breakdown — daily carets', () => {
  afterEach(cleanup)

  it('groups an expanded month into day rows with counts and totals', () => {
    const { container, getByText } = renderFinancial()

    const dayRows = container.querySelectorAll('.financial-day-row')
    expect(dayRows.length).toBe(2)

    // 01/07 has 2 bookings: Paid £86.23 + £86.23, Revenue £86.23 + £76.23
    expect(getByText('2 bookings')).toBeTruthy()
    expect(getByText('Paid: £172.46')).toBeTruthy()
    expect(getByText('Revenue: £162.46')).toBeTruthy()
    // 02/07 has 1 booking
    expect(getByText('1 booking')).toBeTruthy()
  })

  it('hides booking rows until the day is expanded, then shows only that day', () => {
    const { container, queryByText, getByText } = renderFinancial()

    expect(queryByText('TAG-AAA11111')).toBeNull()
    expect(queryByText('TAG-CCC33333')).toBeNull()

    fireEvent.click(getByText('01/07/2026').closest('tr'))

    expect(getByText('TAG-AAA11111')).toBeTruthy()
    expect(getByText('TAG-BBB22222')).toBeTruthy()
    expect(queryByText('TAG-CCC33333')).toBeNull()

    fireEvent.click(getByText('02/07/2026').closest('tr'))
    expect(getByText('TAG-CCC33333')).toBeTruthy()
  })

  it('shows a Refunds total only on days that have refunds', () => {
    const { container } = renderFinancial()

    const refundSpans = container.querySelectorAll('.financial-day-row .day-refunds')
    expect(refundSpans.length).toBe(1) // only 01/07 carries a refund
    expect(refundSpans[0].textContent).toBe('Refunds: £10.00')
  })

  it('clicking an expanded day row collapses it again', () => {
    const { queryByText, getByText } = renderFinancial()

    const dayRow = getByText('01/07/2026').closest('tr')
    fireEvent.click(dayRow)
    expect(getByText('TAG-AAA11111')).toBeTruthy()

    fireEvent.click(dayRow)
    expect(queryByText('TAG-AAA11111')).toBeNull()
  })
})
