import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const adminSource = fs.readFileSync(path.resolve(__dirname, '../Admin.jsx'), 'utf8')

const filterReferralCustomers = (rows, filter) => {
  if (filter === 'all') return rows
  return rows.filter(row => {
    if (filter === 'awaiting_response') return ['invited', 'reminded'].includes(row.status)
    if (filter === 'opted_in') return row.status === 'opted_in'
    if (filter === 'opted_out') return row.status === 'opted_out'
    if (filter === 'has_code_usage') return (row.uses || 0) > 0
    if (filter === 'has_qualified') return (row.qualified || 0) > 0
    if (filter === 'reward_earned') return row.reward_earned
    if (filter === 'self_use_only') return row.has_self_use_only && (row.uses || 0) > 0 && (row.qualified || 0) === 0
    if (filter === 'disqualified_usage') return row.has_disqualified_usage
    return true
  })
}

const filterReferralUsage = (rows, filter, searchTerm = '') => {
  let filtered = rows
  if (filter !== 'all') {
    filtered = filtered.filter(row => {
      if (filter === 'pending') return row.attribution_status === 'pending'
      if (filter === 'qualified') return row.attribution_status === 'qualified'
      if (filter === 'disqualified') return row.attribution_status === 'disqualified'
      if (filter === 'self_use') return row.self_use
      if (filter === 'completed') return row.booking_status === 'completed'
      if (filter === 'open_bookings') return ['pending', 'confirmed'].includes(row.booking_status)
      return true
    })
  }
  if (searchTerm.trim()) {
    const search = searchTerm.toLowerCase().trim()
    filtered = filtered.filter(row =>
      row.code?.toLowerCase().includes(search) ||
      row.booking_reference?.toLowerCase().includes(search) ||
      row.referrer?.toLowerCase().includes(search) ||
      row.used_by?.toLowerCase().includes(search)
    )
  }
  return filtered
}

describe('Admin referrals dashboard', () => {
  it('adds Referrals under Marketing and fetches the dedicated API', () => {
    expect(adminSource).toContain("{ id: 'referrals', label: 'Referrals' }")
    expect(adminSource).toContain("setMarketingSubTab('referrals')")
    expect(adminSource).toContain('/api/admin/marketing/referrals')
    expect(adminSource).toContain('/api/admin/marketing/referrals/manual-invite')
  })

  it('renders overview, customer, and code usage sections', () => {
    expect(adminSource).toContain('Referral Program')
    expect(adminSource).toContain('Social referral invite')
    expect(adminSource).toContain('Send Invite')
    expect(adminSource).toContain('Referral Customers')
    expect(adminSource).toContain('<th>Source</th>')
    expect(adminSource).toContain('referral-source-pill')
    expect(adminSource).toContain('invite_source_label')
    expect(adminSource).toContain('Code Usage / Bookings')
    expect(adminSource).toContain('Self-use / disqualified')
    expect(adminSource).toContain('Response opt-in rate')
    expect(adminSource).toContain('customer_filter')
    expect(adminSource).toContain('customer_search')
    expect(adminSource).toContain('referralsCustomerSearchQuery')
    expect(adminSource).toContain('setReferralsCustomerSearchQuery(referralsCustomerSearch.trim())')
    expect(adminSource).toContain('usage_filter')
    expect(adminSource).toContain('usage_search')
    expect(adminSource).toContain('referralsUsageSearchQuery')
    expect(adminSource).toContain('setReferralsUsageSearchQuery(referralsUsageSearch.trim())')
    expect(adminSource).toContain('}, 350)')
    expect(adminSource).toContain('referralsDashboardHasLoaded')
    expect(adminSource).toContain("aria-busy={loadingReferrals ? 'true' : 'false'}")
    expect(adminSource).toContain('Showing {referralCustomerStart}-{referralCustomerEnd}')
    expect(adminSource).toContain('Showing {referralUsageStart}-{referralUsageEnd}')
    expect(adminSource).toContain('REFERRALS_PAGE_SIZE_OPTIONS')
    expect(adminSource).toContain('REFERRALS_DEFAULT_PAGE_SIZE = 10')
    expect(adminSource).toContain('referrals-page-button')
    expect(adminSource).toContain('referrals-page-size')
    expect(adminSource).toContain('Code Email Sent')
    expect(adminSource).toContain('Reminder Sent')
    expect(adminSource).toContain('Reward Earned')
    expect(adminSource).toContain('Reward Email Sent')
    expect(adminSource).toContain('Attribution')
    expect(adminSource).toContain('Customer, email, code')
    expect(adminSource).toContain('referrals-refresh-button')
    expect(adminSource).toContain('referral-stat-card-')
    expect(adminSource).toContain('referrals-usage-search')
    expect(adminSource).toContain('referralUsageTableRef.current?.scrollIntoView')
    expect(adminSource).toContain('setReferralsUsageOffset(0)')
    expect(adminSource).toContain('referralDashboardActionInFlightRef.current')
    expect(adminSource).toContain('referral-action-button-neutral')
    expect(adminSource).toContain('referral-action-button-success')
    expect(adminSource).toContain('referral-action-button-danger')
  })

  it('keeps customer detail compact with a referral details link', () => {
    expect(adminSource).toContain('referral-summary-line')
    expect(adminSource).toContain('View referral details')
    expect(adminSource).not.toContain('Code Email Sent:')
  })

  it('filters referral customers for QA handoff scenarios', () => {
    const rows = [
      { status: 'invited', uses: 0, qualified: 0 },
      { status: 'opted_in', uses: 2, qualified: 1, reward_earned: true },
      { status: 'opted_in', uses: 1, qualified: 0, has_self_use_only: true, has_disqualified_usage: true },
      { status: 'opted_out', uses: 0, qualified: 0 },
    ]

    expect(filterReferralCustomers(rows, 'awaiting_response')).toHaveLength(1)
    expect(filterReferralCustomers(rows, 'opted_in')).toHaveLength(2)
    expect(filterReferralCustomers(rows, 'has_code_usage')).toHaveLength(2)
    expect(filterReferralCustomers(rows, 'has_qualified')).toHaveLength(1)
    expect(filterReferralCustomers(rows, 'reward_earned')).toHaveLength(1)
    expect(filterReferralCustomers(rows, 'self_use_only')).toHaveLength(1)
    expect(filterReferralCustomers(rows, 'disqualified_usage')).toHaveLength(1)
  })

  it('filters referral code usage without requiring completed bookings', () => {
    const rows = [
      { code: 'REF-AAAA-BBBB', booking_reference: 'TAG-1', referrer: 'Ref One', used_by: 'Friend One', booking_status: 'confirmed', attribution_status: 'pending', self_use: false },
      { code: 'REF-CCCC-DDDD', booking_reference: 'TAG-2', referrer: 'Ref Two', used_by: 'Friend Two', booking_status: 'completed', attribution_status: 'qualified', self_use: false },
      { code: 'REF-AAAA-BBBB', booking_reference: 'TAG-3', referrer: 'Ref One', used_by: 'Ref One', booking_status: 'completed', attribution_status: 'disqualified', self_use: true },
    ]

    expect(filterReferralUsage(rows, 'open_bookings')).toHaveLength(1)
    expect(filterReferralUsage(rows, 'completed')).toHaveLength(2)
    expect(filterReferralUsage(rows, 'pending')).toHaveLength(1)
    expect(filterReferralUsage(rows, 'qualified')).toHaveLength(1)
    expect(filterReferralUsage(rows, 'disqualified')).toHaveLength(1)
    expect(filterReferralUsage(rows, 'self_use')).toHaveLength(1)
    expect(filterReferralUsage(rows, 'all', 'REF-AAAA')).toHaveLength(2)
    expect(filterReferralUsage(rows, 'all', 'TAG-2')).toHaveLength(1)
  })
})
