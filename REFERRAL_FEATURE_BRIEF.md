# Referral Feature Brief

## Goal

Invite customers into a referral program one week after they complete a booking. Customers who opt in receive a unique referral code within one hour. Friends and family can use that code for 10% off their booking. Once enough referred bookings are completed, the referrer receives one free week of parking as a reward.

## Product Rules

1. Eligibility starts when a customer has a booking with `status = completed`.
2. Eligible customers receive a referral invite email 7 days after the booking is completed, with a clear Yes / No choice.
3. If the customer clicks No, they are opted out and receive no further referral emails.
4. If the customer does nothing, they receive one reminder email 4 weeks after the original invite.
5. If the customer clicks Yes, they are opted in and receive their unique referral code within one hour.
6. Referral codes give family and friends 10% off their booking.
7. A customer may use their own referral code for the 10% discount.
8. Self-use does not count toward referral reward progress.
9. After 6 completed referred bookings, the referrer earns a free-week reward.
10. After 7 completed referred bookings, the referrer still has one active free-week reward unless the business later chooses to issue another reward at 12/14, etc.
11. The free-week reward follows existing `free_week` promo behavior: stays up to 7 days are free; stays over 7 days deduct the current 7-day base price from the booking price at the time of booking.

## Recommended Interpretations

- Use 6 completed non-self referred bookings as the reward threshold. The user wrote "6/7"; treat that as "after 6, certainly by 7" unless the business confirms a different exact threshold.
- Invite each customer once, based on customer identity, not once per booking.
- If a customer has multiple completed bookings, trigger from their first completed booking that is at least 7 days old and has not already produced a referral invite.
- Generate one reusable referral discount code per opted-in customer.
- Count reward progress only when the referred booking reaches `completed`, not when it is created or paid.
- Exclude cancelled, refunded, pending, and confirmed-but-not-completed bookings from reward progress.
- Reward codes should be separate from referral discount codes.

## Existing Repo Hooks

- Booking status already includes `completed` in `backend/db_models.py`.
- Booking records already have `completed_at`, email tracking fields, and relationships to customers/payments.
- Promotions already support `percentage`, `free_week`, and `free_100` discount types.
- `PromoCode` already supports multi-use usage tracking via `PromoCodeUsage`.
- `email_scheduler.py` already handles delayed background email workflows.
- `email_service.py` already centralizes SendGrid template delivery.

## Data Model

Add a referral program table rather than overloading marketing subscribers.

### `referral_programs`

- `id`
- `customer_id` unique, indexed, FK to `customers.id`
- `status`: `eligible`, `invited`, `reminded`, `opted_in`, `opted_out`
- `invite_sent_at`
- `reminder_sent_at`
- `responded_at`
- `referral_code_id` nullable FK to `promo_codes.id`
- `reward_code_id` nullable FK to `promo_codes.id`
- `qualified_referral_count` integer default 0
- `reward_earned_at`
- `reward_email_sent_at`
- `created_at`
- `updated_at`

### `referral_attributions`

- `id`
- `referral_program_id` FK
- `referrer_customer_id` FK to `customers.id`
- `referred_customer_id` FK to `customers.id`
- `booking_id` unique FK to `bookings.id`
- `promo_code_id` FK to `promo_codes.id`
- `is_self_use` boolean
- `status`: `pending`, `qualified`, `disqualified`
- `qualified_at`
- `created_at`

## Backend Work

### Eligibility Scan

Create a scheduler function that finds customers with at least one booking that has `status = completed` and `completed_at <= now - 7 days`, and no referral program row. Create a row with `eligible`, then send the invite and mark `invited` on success.

Suggested behavior:
- limit batches to 10-50 customers per run
- skip customers with no valid email
- idempotent via unique `customer_id`
- do not create rows for users already opted out
- do not invite completed bookings until `completed_at` is present and at least 7 days old

### Invite Response API

Create public signed-token endpoints:

- `GET /api/referrals/respond?token=...&decision=yes`
- `GET /api/referrals/respond?token=...&decision=no`

Behavior:
- validate token, expiry, customer/referral row
- `no`: set `opted_out`, `responded_at`, return a simple confirmation page or JSON
- `yes`: set `opted_in`, `responded_at`; code generation can happen immediately or via scheduler within one hour
- repeat clicks should be idempotent

### Code Generation

When opted in and no `referral_code_id` exists:
- create or reuse a `Promotion` named like `Referral Friend 10%`
- create a reusable `PromoCode` with `discount_percent = 10`, `discount_type = percentage`
- use a recognizable prefix such as `REF`
- set `max_uses = 0` for unlimited friend/family use unless the business wants a cap
- assign the generated code to `referral_programs.referral_code_id`
- email the customer their code

### Attribution

When a booking uses a referral code:
- create a `referral_attributions` row linked to the booking
- set `is_self_use = true` when `booking.customer_id == referral_program.customer_id`
- do not increment `qualified_referral_count` until the booking becomes `completed`
- self-use receives discount but remains `disqualified` or never qualifies for reward count

### Completion Qualification

When a booking changes to `completed`:
- find any attribution for the booking
- if not self-use, mark `qualified`
- recompute or increment `qualified_referral_count`
- when count reaches threshold and no reward exists, generate one `free_week` reward code and send reward email

### Reward Code

Create a `Promotion` named like `Referral Reward Free Week`.

Reward promo:
- `discount_percent = 100`
- `discount_type = free_week`
- single-use by default
- recipient is the referrer
- expiration optional; if added, use at least 12 months

## Email Work

Admin/Marketing/Email Campaigns note:
- The reusable campaign wrapper used by Admin -> Marketing -> Email Campaigns is `backend/email_templates/marketing_campaign_email.html`.
- It is sent by `send_marketing_campaign_email()` in `backend/email_service.py`.
- The Admin UI for campaign subject/message/recipients lives in `tag-website/src/Admin.jsx` under the Marketing `campaigns` sub-tab.
- Brand casing in customer-facing copy should be `Tag`, not `TAG`. Keep `TAG-*` only for booking references, promo codes, and other literal code values.

Create templates:

- `referral_invite_email.html`: sent one week after completed parking, asks the customer if they want to join, with Yes and No buttons.
- `referral_invite_reminder_email.html`: sent once 4 weeks later if no response.
- `referral_code_email.html`: contains the unique 10% code and short share copy.
- `referral_reward_email.html`: tells the referrer they earned up to 1 week free parking.

Email copy notes:
- Keep opt-in explicit.
- Make No a real one-click opt-out.
- Say self-use is allowed for 10% off but only friend/family completed bookings count toward rewards.
- Avoid promising "completely free" without the over-7-day caveat.

## Frontend/Admin Work

Minimum public frontend:
- Confirmation page for Yes response.
- Confirmation page for No response.
- Error page for expired/invalid token.

Admin visibility:
- Add referral status and referral code to customer detail or booking/customer admin panels.
- Show qualified referral count.
- Show reward code and reward earned/sent timestamps.
- Optional manual resend buttons for invite/code/reward.

Checkout:
- Existing promo validation UI should work for referral discount codes if they are created as normal `PromoCode` rows.
- Ensure promo validation response can identify referral codes if the frontend needs special messaging.

## QA Agent Test Matrix

### Eligibility and Invite

- Customer with no completed bookings is not invited.
- Customer with one completed booking completed less than 7 days ago is not invited.
- Customer with one completed booking completed 7 or more days ago is invited.
- Customer with several completed bookings receives only one referral program row and one invite.
- Cancelled/refunded/pending/confirmed-only customers are not invited.
- Missing/invalid email is skipped without crashing the scheduler.

### Opt In / Opt Out

- Yes response marks `opted_in`.
- No response marks `opted_out`.
- Repeated Yes is idempotent.
- Repeated No is idempotent.
- Yes after No should remain blocked unless business chooses reversible opt-in.
- Invalid/expired/mismatched token fails without changing state.

### Reminder

- No-response invited customer receives one reminder after 4 weeks.
- No reminder before 4 weeks.
- No reminder after opted in.
- No reminder after opted out.
- Reminder send failure does not mark `reminder_sent_at`.

### Referral Code

- Opted-in customer gets a unique referral code within the one-hour window.
- Code is 10% off and validates through existing promo validation.
- Code is reusable by different friend/family customers.
- Code can be used by the owner for the discount.
- Owner self-use does not create qualified reward progress.

### Attribution and Rewards

- Referred booking starts as pending attribution.
- Confirmed booking does not count until completed.
- Completed non-self booking increments count.
- Cancelled/refunded referred booking does not count.
- Completing the same booking twice does not double count.
- Threshold at 6 creates one free-week reward code.
- 7th completed referral does not create duplicate reward code.
- Free-week reward makes stays of 7 days or less free.
- Free-week reward deducts the current 7-day base price from longer stays.

### Integration Boundaries

- Existing marketing promo codes still validate and mark used as before.
- Existing free-week promo behavior remains unchanged.
- Promo modal auto-deactivation is not triggered by normal referral codes unless intended.
- Booking confirmation/payment flows still store `PromoCodeUsage`.
- Scheduler batch processing is idempotent across restarts.

## Build Agent Checklist

1. Add Alembic migration for referral tables and enums.
2. Add SQLAlchemy models and relationships.
3. Add referral service helpers for eligibility, token generation, code generation, attribution, qualification, and reward issuing.
4. Add email templates and send functions.
5. Add scheduler jobs.
6. Add public response endpoints.
7. Hook attribution into promo-code booking creation/confirmation flow.
8. Hook qualification into booking completion flow.
9. Add admin/customer visibility.
10. Run backend mocked tests, targeted referral tests, and relevant promo-code tests.

## PR Plan

### PR 1: Referral Schema and Service Foundation

Scope:
- Add referral status enum/model definitions.
- Add `referral_programs` and `referral_attributions` Alembic migration.
- Add SQLAlchemy relationships.
- Add referral service helpers for lookup, idempotent row creation, and threshold constants.

QA:
- Migration upgrade/downgrade smoke coverage if available.
- Model default tests for statuses, unique customer program, attribution uniqueness by booking.
- Service tests for idempotent referral program creation.

Acceptance:
- App starts with the new models.
- Existing booking, promo, and marketing tests still pass.
- No email or checkout behavior changes yet.

### PR 2: One-Week Invite and Response Flow

Scope:
- Add `referral_invite_email.html` and `referral_invite_reminder_email.html`.
- Add email service functions for invite and reminder.
- Add signed-token generation/validation for Yes/No links.
- Add public response endpoint for opt-in/opt-out.
- Add scheduler job that invites customers 7 days after `completed_at`.
- Add scheduler job that sends one reminder 4 weeks after unanswered invite.

QA:
- Completed less than 7 days ago does not invite.
- Completed 7+ days ago invites exactly once.
- No response gets one reminder after 4 weeks.
- Opt-in and opt-out are idempotent.
- Invalid, expired, or tampered token does not mutate state.

Acceptance:
- Eligible completed customers receive one invite after the 7-day delay.
- Customers can clearly opt in or opt out.
- Opted-out customers receive no referral code/reminder.

### PR 3: Referral Code Generation and Email

Scope:
- Add `referral_code_email.html`.
- Generate unique reusable 10% referral code within one hour of opt-in.
- Create/reuse a `Referral Friend 10%` promotion.
- Link generated `PromoCode` to the customer referral program.
- Ensure existing promo validation accepts referral codes.

QA:
- Opted-in customers get a unique code.
- Code validates as 10% off.
- Code is reusable when configured as unlimited-use.
- Existing promo code validation behavior remains unchanged.
- Code generation is idempotent if the scheduler runs repeatedly.

Acceptance:
- Customer receives their unique referral code within the promised window.
- Friends/family can apply it in the existing checkout promo field.

### PR 4: Checkout Attribution

Scope:
- When a booking uses a referral code, create a `referral_attributions` row.
- Detect self-use by comparing booking customer to referrer customer.
- Keep self-use discount valid but mark it non-qualifying for reward progress.
- Ensure booking deletion/cancellation does not leave misleading qualified progress.

QA:
- Friend/family use creates pending attribution.
- Self-use creates attribution with `is_self_use = true` or otherwise excludes qualification.
- Self-use still receives the 10% discount.
- Same booking cannot create duplicate attribution.
- Cancelled/refunded bookings do not qualify.

Acceptance:
- Referral usage is recorded without changing normal payment/confirmation flow.
- Self-use works for discount but not reward progress.

### PR 5: Completion Qualification and Reward Issuing

Scope:
- Hook into booking completion flow.
- Mark non-self referral attributions as qualified when booking becomes `completed`.
- Increment or recompute `qualified_referral_count`.
- At threshold, create a single-use `free_week` reward code.
- Add `referral_reward_email.html` and send reward email.

QA:
- Confirmed booking does not count until completed.
- Completed referred booking increments count once.
- Duplicate completion does not double count.
- 6th qualified referral creates one reward.
- 7th qualified referral does not create a duplicate reward.
- Reward uses `free_week` behavior for under/over 7-day bookings.

Acceptance:
- Referrer earns one free-week reward after the agreed threshold.
- Reward code behaves like existing free-week promos.

### PR 6: Admin Visibility and Manual Controls

Scope:
- Add referral fields to customer/admin views.
- Show referral status, referral code, qualified count, reward status, and timestamps.
- Optional admin actions: resend invite, resend referral code, resend reward email, opt customer out.

QA:
- Admin views render customers with and without referral rows.
- Manual resend actions are permission-protected.
- Manual actions are idempotent and do not duplicate codes/rewards.

Acceptance:
- Support/admin can answer "is this customer in the referral program?" without direct database access.

### PR 7: End-to-End Regression and Launch Guardrails

Scope:
- Add or update E2E coverage for promo/referral checkout path.
- Add metrics/logging for invite sent, opt-in, opt-out, code sent, referral used, reward earned.
- Add a feature flag or environment variable to pause invite/code/reward schedulers independently.
- Add launch/backfill runbook.

QA:
- E2E happy path: completed customer invited, opts in, friend uses code, booking completes, reward issued.
- Feature flag disables outbound referral emails.
- Existing promo-code, free-week, booking confirmation, and completion tests pass.

Acceptance:
- Feature can be enabled gradually and paused without deploy rollback.
- Launch has a clear operational checklist.

## Open Business Questions

- Is the exact threshold 6, 7, or "6 completed referrals plus the current trip makes 7 total"? Current recommended assumption is 6.
- Should a customer be able to reverse an opt-out later through admin support?
- Should referral codes expire?
- Should reward codes expire?
- Should one referrer earn multiple free-week rewards for every 6 additional completed referrals?
- Should the friend/family discount be valid for all service types, including Park & Ride and Meet & Greet?
