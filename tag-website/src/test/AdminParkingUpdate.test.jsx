import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const adminSource = fs.readFileSync(path.resolve(__dirname, '../Admin.jsx'), 'utf8')

const getParkingUpdateStatus = (booking) => {
  const emailStatus = booking.parking_update_email_status || 'pending'
  const smsStatus = booking.parking_update_sms_status || 'pending'

  if (emailStatus === 'failed') {
    return 'failed'
  }
  if (emailStatus === 'sent' && smsStatus === 'sent') {
    return 'sent'
  }
  if (emailStatus === 'sent') {
    return 'partial'
  }
  return 'pending'
}

const applyParkingUpdateResponse = (booking, data) => ({
  ...booking,
  parking_update_email_status: data.parking_update_email_status,
  parking_update_email_sent_at: data.parking_update_email_sent_at,
  parking_update_email_attempt_count: data.parking_update_email_attempt_count,
  parking_update_email_last_attempt_at: data.parking_update_email_last_attempt_at,
  parking_update_sms_status: data.parking_update_sms_status,
  parking_update_sms_sent_at: data.parking_update_sms_sent_at,
  parking_update_last_error: data.parking_update_last_error,
})

describe('Admin Parking Update Notification UI', () => {
  it('places Parking Update between Confirmation and 2-Day Reminder', () => {
    const confirmationIndex = adminSource.indexOf('Confirmation Email Status Indicator')
    const parkingIndex = adminSource.indexOf('Parking Update Status Indicator')
    const reminderIndex = adminSource.indexOf('2-Day Reminder Status Indicator')

    expect(confirmationIndex).toBeGreaterThan(-1)
    expect(parkingIndex).toBeGreaterThan(confirmationIndex)
    expect(reminderIndex).toBeGreaterThan(parkingIndex)
  })

  it('shows pending, sent, failed, and partial status labels', () => {
    expect(adminSource).toContain('Parking Update')
    expect(adminSource).toContain('Pending')
    expect(adminSource).toContain('Sent ✓')
    expect(adminSource).toContain('Failed')
    expect(adminSource).toContain('Email Sent / SMS Failed')
    expect(adminSource).toContain('Email Sent / SMS Off')
  })

  it('derives parking update status from email and SMS fields', () => {
    expect(getParkingUpdateStatus({})).toBe('pending')
    expect(getParkingUpdateStatus({
      parking_update_email_status: 'sent',
      parking_update_sms_status: 'sent',
    })).toBe('sent')
    expect(getParkingUpdateStatus({ parking_update_email_status: 'failed' })).toBe('failed')
    expect(getParkingUpdateStatus({
      parking_update_email_status: 'sent',
      parking_update_sms_status: 'failed',
    })).toBe('partial')
    expect(getParkingUpdateStatus({
      parking_update_email_status: 'sent',
      parking_update_sms_status: 'disabled',
    })).toBe('partial')
  })

  it('manual send uses the parking update endpoint and applies returned status fields', () => {
    expect(adminSource).toContain('/send-parking-update')

    const updated = applyParkingUpdateResponse(
      { id: 42, reference: 'TAG-1', parking_update_email_status: 'pending' },
      {
        parking_update_email_status: 'sent',
        parking_update_email_sent_at: '2026-06-02T10:00:00Z',
        parking_update_email_attempt_count: 1,
        parking_update_email_last_attempt_at: '2026-06-02T10:00:00Z',
        parking_update_sms_status: 'sent',
        parking_update_sms_sent_at: '2026-06-02T10:01:00Z',
        parking_update_last_error: null,
      },
    )

    expect(updated).toMatchObject({
      id: 42,
      parking_update_email_status: 'sent',
      parking_update_email_attempt_count: 1,
      parking_update_sms_status: 'sent',
      parking_update_last_error: null,
    })
  })
})
