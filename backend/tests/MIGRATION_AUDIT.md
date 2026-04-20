# Test Migration Audit

**Generated:** 2026-04-20
**Purpose:** Track migration of root-level tests to `tests/mocked/` bucket

## Summary

| Category | Count |
|----------|-------|
| Root test files | 102 |
| Already in mocked/ | 12 |
| To migrate | 102 |

## Root Test Files (Hit Live Staging DB)

These 102 test files currently execute against live Railway PostgreSQL staging.
They need to be migrated to `tests/mocked/` with proper fixtures.

### By Feature Area

#### Authentication & Users
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_auth.py | mocked/test_auth.py | High |
| test_login_email.py | mocked/test_login_email.py | Medium |
| test_user_management.py | mocked/test_user_management.py | Medium |

#### Booking Core
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_booking_service.py | mocked/test_booking_service.py | High |
| test_booking_deduplication.py | mocked/test_booking_deduplication.py | High |
| test_booking_locations.py | mocked/test_booking_locations.py | Medium |
| test_booking_confirmation_email.py | mocked/test_booking_confirmation_email.py | Medium |
| test_concurrent_booking.py | mocked/test_concurrent_booking.py | High |
| test_same_day_booking.py | mocked/test_same_day_booking.py | Medium |
| test_manual_booking.py | mocked/test_manual_booking.py | Medium |

#### Pricing
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_pricing.py | mocked/test_pricing.py | High |
| test_anchor_pricing.py | mocked/test_anchor_pricing.py | Medium |
| test_anchor_pricing_integration.py | DELETE (merge into mocked) | Low |
| test_flexible_duration_pricing_integration.py | mocked/test_flexible_duration_pricing.py | Medium |

#### Promo Codes
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_promo_code.py | mocked/test_promo_code.py | High |
| test_promo_code_booking_flow.py | mocked/test_promo_code_booking_flow.py | Medium |
| test_promo_code_change.py | mocked/test_promo_code_change.py | Medium |
| test_promo_code_expiry.py | mocked/test_promo_code_expiry.py | Medium |
| test_promo_code_expiry_integration.py | DELETE (merge into mocked) | Low |
| test_promo_modal.py | mocked/test_promo_modal.py | Low |
| test_promo_modal_code.py | mocked/test_promo_modal_code.py | Low |
| test_promo_with_flexible_pricing.py | mocked/test_promo_with_flexible_pricing.py | Medium |
| test_promotion_code_prefix.py | mocked/test_promotion_code_prefix.py | Low |
| test_promotions.py | mocked/test_promotions.py | Medium |
| test_multi_use_promo_codes.py | mocked/test_multi_use_promo_codes.py | Medium |
| test_founder_promo_code.py | mocked/test_founder_promo_code.py | Low |

#### Admin Features
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_admin_bookings.py | mocked/test_admin_bookings.py | High |
| test_admin_bookings_optimization.py | mocked/test_admin_bookings_optimization.py | Medium |
| test_admin_bookings_optimization_integration.py | DELETE (merge into mocked) | Low |
| test_admin_customers.py | mocked/test_admin_customers.py | Medium |
| test_admin_flights.py | mocked/test_admin_flights.py | Medium |
| test_admin_flights_integration.py | DELETE (merge into mocked) | Low |
| test_admin_marketing_promo.py | mocked/test_admin_marketing_promo.py | Low |

#### Flights
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_flight_history.py | mocked/test_flight_history.py | Medium |
| test_manual_flight_entry.py | mocked/test_manual_flight_entry.py | Medium |
| test_edit_flight_details.py | mocked/test_edit_flight_details.py | Medium |
| test_edit_flight_details_integration.py | DELETE (merge into mocked) | Low |
| test_overnight_arrivals.py | mocked/test_overnight_arrivals.py | Medium |
| test_seasonal_routes.py | mocked/test_seasonal_routes.py | Low |

#### Vehicle & Inspection
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_vehicle_inspection.py | mocked/test_vehicle_inspection.py | Medium |
| test_vehicle_model_optional.py | mocked/test_vehicle_model_optional.py | Low |
| test_declined_inspection.py | mocked/test_declined_inspection.py | Medium |
| test_declined_inspection_integration.py | DELETE (merge into mocked) | Low |
| test_inspection_status_batch.py | mocked/test_inspection_status_batch.py | Low |
| test_dvla.py | mocked/test_dvla.py | Medium |

#### Employee & Roster
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_roster.py | mocked/test_roster.py | Medium |
| test_roster_shift_duplicate.py | mocked/test_roster_shift_duplicate.py | Low |
| test_roster_shift_duplicate_integration.py | DELETE (merge into mocked) | Low |
| test_shift_claim_release.py | mocked/test_shift_claim_release.py | Medium |
| test_shift_claim_release_integration.py | DELETE (merge into mocked) | Low |
| test_shift_unassign.py | mocked/test_shift_unassign.py | Medium |
| test_shift_unassign_integration.py | DELETE (merge into mocked) | Low |
| test_employee_holidays.py | mocked/test_employee_holidays.py | Medium |
| test_employee_holidays_integration.py | DELETE (merge into mocked) | Low |
| test_employee_unavailability.py | mocked/test_employee_unavailability.py | Medium |
| test_employee_unavailability_integration.py | DELETE (merge into mocked) | Low |
| test_payroll.py | mocked/test_payroll.py | Medium |
| test_payroll_integration.py | DELETE (merge into mocked) | Low |
| test_weekly_hours.py | mocked/test_weekly_hours.py | Low |
| test_weekly_hours_breakdown.py | mocked/test_weekly_hours_breakdown.py | Low |

#### Reports & Analytics
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_booking_stats.py | mocked/test_booking_stats.py | Medium |
| test_booking_stats_integration.py | DELETE (merge into mocked) | Low |
| test_financial_report.py | mocked/test_financial_report.py | Medium |
| test_financial_report_integration.py | DELETE (merge into mocked) | Low |
| test_fun_facts.py | mocked/test_fun_facts.py | Low |
| test_fun_facts_integration.py | DELETE (merge into mocked) | Low |
| test_popular_report.py | mocked/test_popular_report.py | Low |
| test_popular_report_integration.py | DELETE (merge into mocked) | Low |
| test_occupancy_report.py | mocked/test_occupancy_report.py | Low |
| test_occupancy_report_integration.py | DELETE (merge into mocked) | Low |
| test_forecast_cache.py | mocked/test_forecast_cache.py | Low |
| test_forecast_cache_integration.py | DELETE (merge into mocked) | Low |

#### Marketing & Leads
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_marketing_subscribe.py | mocked/test_marketing_subscribe.py | Medium |
| test_marketing_sources.py | mocked/test_marketing_sources.py | Low |
| test_abandoned_leads.py | mocked/test_abandoned_leads.py | Medium |
| test_abandoned_carts.py | mocked/test_abandoned_carts.py | Medium |
| test_abandoned_carts_integration.py | DELETE (merge into mocked) | Low |
| test_session_tracking.py | mocked/test_session_tracking.py | Medium |
| test_session_tracking_integration.py | DELETE (merge into mocked) | Low |

#### Email & SMS
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_thank_you_email.py | mocked/test_thank_you_email.py | Medium |
| test_2day_reminder_email.py | mocked/test_2day_reminder_email.py | Medium |
| test_send_founder_email_endpoint.py | mocked/test_send_founder_email_endpoint.py | Low |
| test_subscriber_founder_email.py | mocked/test_subscriber_founder_email.py | Low |
| test_founder_followup_email.py | mocked/test_founder_followup_email.py | Low |
| test_sms_service.py | mocked/test_sms_service.py | Medium |
| test_sms_integration.py | DELETE (merge into mocked) | Low |
| test_sms_threads.py | mocked/test_sms_threads.py | Medium |
| test_sms_threads_integration.py | DELETE (merge into mocked) | Low |

#### Payments
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_stripe.py | mocked/test_stripe.py | High |
| test_cancel_payment.py | mocked/test_cancel_payment.py | High |

#### Infrastructure
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_api.py | mocked/test_api.py | High |
| test_integration.py | DELETE (general integration) | Low |
| test_circuit_breaker.py | mocked/test_circuit_breaker.py | Medium |
| test_db_health_history.py | mocked/test_db_health_history.py | Low |
| test_pool_snapshot.py | mocked/test_pool_snapshot.py | Low |
| test_qa_dashboard.py | mocked/test_qa_dashboard.py | Low |

#### Misc
| File | Proposed Destination | Priority |
|------|---------------------|----------|
| test_address_lookup.py | mocked/test_address_lookup.py | Medium |
| test_blocked_dates.py | mocked/test_blocked_dates.py | Medium |
| test_customer_name_snapshot.py | mocked/test_customer_name_snapshot.py | Low |
| test_name_title_case.py | mocked/test_name_title_case.py | Low |
| test_testimonials.py | mocked/test_testimonials.py | Low |
| test_time_slots.py | mocked/test_time_slots.py | Medium |

---

## Already Mocked (tests/mocked/)

These 12 test files are already properly mocked:

| File | Tests | Status |
|------|-------|--------|
| test_customer_detail.py | 32 | Working |
| test_swap_vehicle.py | 24 | Working |
| test_testimonials_stats.py | ? | Working |
| test_session_expiry.py | ? | Working |
| test_discount_types.py | ? | Working |
| test_discount_types_integration.py | ? | Working |
| test_peak_day_pricing.py | 52 | Working |
| test_tier_pricing.py | ~30 | **7 FAILING** (date issue) |
| test_get_current_user.py | ? | Working |
| test_time_slots.py | ? | Working |
| test_peak_booking_hours.py | ? | Working |
| test_pricing_display_toggle.py | ? | Working |

---

## Migration Strategy

### Phase 1: Fix Critical (High Priority)
1. test_auth.py
2. test_booking_service.py
3. test_stripe.py
4. test_api.py
5. test_pricing.py
6. test_promo_code.py

### Phase 2: Core Features (Medium Priority)
- All booking-related tests
- Employee/roster tests
- Marketing tests

### Phase 3: Reports & Low Priority
- All report tests
- Misc utility tests

### For Each Migration:
1. Copy file to `tests/mocked/`
2. Replace DB fixtures with mocks
3. Run to verify passes
4. Delete original from root
5. Update imports if needed

---

## Notes

- `*_integration.py` files at root level are redundant - they hit live DB just like their non-integration counterparts
- All these should be merged into single mocked test file
- Current mocked conftest.py already handles fixture overrides correctly
