const PricingSection = ({
  pricing,
  fetchPricing,
  pricingMessage,
  loadingPricing,
  setPricing,
  savingPricing,
  savePricing,
}) => {
  const safePricing = pricing || {}

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Pricing Settings</h2>
        <button onClick={fetchPricing} className="admin-refresh" disabled={loadingPricing}>
          {loadingPricing ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {pricingMessage && <div className="admin-success">{pricingMessage}</div>}

      {loadingPricing ? (
        <div className="admin-loading-inline">
          <div className="spinner-small"></div>
          <span>Loading pricing settings...</span>
        </div>
      ) : (
        <div className="pricing-settings-form">
          <div className="admin-pricing-section">
            <h3>Anchor Prices (Early Booking Tier)</h3>
            <p className="pricing-hint">These are the base prices when customers book 14+ days in advance. Days between anchors use daily increments.</p>

            <div className="pricing-inputs pricing-inputs-grid">
              <div className="pricing-input-group">
                <label>1-4 Days</label>
                <div className="price-input-wrapper">
                  <span className="currency-symbol">£</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={safePricing.days_1_4_price}
                    onChange={(e) => {
                      const val = e.target.value.replace(/[^0-9.]/g, '')
                      setPricing({ ...safePricing, days_1_4_price: parseFloat(val) || 0 })
                    }}
                  />
                </div>
              </div>

              <div className="pricing-input-group">
                <label>1 Week (7 Days)</label>
                <div className="price-input-wrapper">
                  <span className="currency-symbol">£</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={safePricing.week1_base_price}
                    onChange={(e) => {
                      const val = e.target.value.replace(/[^0-9.]/g, '')
                      setPricing({ ...safePricing, week1_base_price: parseFloat(val) || 0 })
                    }}
                  />
                </div>
              </div>

              <div className="pricing-input-group">
                <label>2 Weeks (14 Days)</label>
                <div className="price-input-wrapper">
                  <span className="currency-symbol">£</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={safePricing.week2_base_price}
                    onChange={(e) => {
                      const val = e.target.value.replace(/[^0-9.]/g, '')
                      setPricing({ ...safePricing, week2_base_price: parseFloat(val) || 0 })
                    }}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="admin-pricing-section tier-increment-section">
            <h3>Daily Increment</h3>
            <p className="pricing-hint">Added per day for durations between anchors (5-6, 8-13, 15+ days).</p>
            <div className="pricing-inputs">
              <div className="pricing-input-group pricing-input-highlight">
                <label>Daily Increment</label>
                <div className="price-input-wrapper">
                  <span className="currency-symbol">£</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={safePricing.daily_increment}
                    onChange={(e) => {
                      const val = e.target.value.replace(/[^0-9.]/g, '')
                      setPricing({ ...safePricing, daily_increment: parseFloat(val) || 0 })
                    }}
                  />
                </div>
                <span className="pricing-input-hint">per extra day</span>
              </div>
            </div>
          </div>

          <div className="admin-pricing-section tier-increment-section">
            <h3>Tier Increment</h3>
            <p className="pricing-hint">Added for Standard tier (+1x) and Late tier (+2x) bookings based on advance booking.</p>
            <div className="pricing-inputs">
              <div className="pricing-input-group pricing-input-highlight">
                <label>Tier Increment</label>
                <div className="price-input-wrapper">
                  <span className="currency-symbol">£</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={safePricing.tier_increment}
                    onChange={(e) => {
                      const val = e.target.value.replace(/[^0-9.]/g, '')
                      setPricing({ ...safePricing, tier_increment: parseFloat(val) || 0 })
                    }}
                  />
                </div>
                <span className="pricing-input-hint">per tier level</span>
              </div>
            </div>
          </div>

          <div className="admin-pricing-section peak-day-section">
            <h3>Peak Day Increment</h3>
            <p className="pricing-hint">Added when drop-off is Friday/Saturday AND pickup is Sunday/Monday/Tuesday. Set to 0 to disable.</p>
            <div className="pricing-inputs">
              <div className="pricing-input-group pricing-input-highlight">
                <label>Peak Day Increment</label>
                <div className="price-input-wrapper">
                  <span className="currency-symbol">£</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={safePricing.peak_day_increment}
                    onChange={(e) => {
                      const val = e.target.value.replace(/[^0-9.]/g, '')
                      setPricing({ ...safePricing, peak_day_increment: parseFloat(val) || 0 })
                    }}
                  />
                </div>
                <span className="pricing-input-hint">for peak day bookings</span>
              </div>
            </div>
          </div>

          <div className="admin-pricing-section display-mode-section">
            <h3>Homepage Display</h3>
            <p className="pricing-hint">How prices are shown on the homepage pricing section.</p>
            <div className="pricing-display-toggle">
              <label className="toggle-option">
                <input
                  type="radio"
                  name="priceDisplayMode"
                  checked={!safePricing.show_price_range}
                  onChange={() => setPricing({ ...safePricing, show_price_range: false })}
                />
                <span className="toggle-label">
                  <strong>From £{safePricing.days_1_4_price}</strong>
                  <span className="toggle-hint">Shows minimum price only</span>
                </span>
              </label>
              <label className="toggle-option">
                <input
                  type="radio"
                  name="priceDisplayMode"
                  checked={safePricing.show_price_range}
                  onChange={() => setPricing({ ...safePricing, show_price_range: true })}
                />
                <span className="toggle-label">
                  <strong>£{safePricing.days_1_4_price}–£{safePricing.days_1_4_price + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</strong>
                  <span className="toggle-hint">Shows full price range</span>
                </span>
              </label>
            </div>
          </div>

          <div className="pricing-preview">
            <h3>Price Preview</h3>
            <table className="pricing-preview-table">
              <thead>
                <tr>
                  <th rowSpan="2">Duration</th>
                  <th colSpan="3">Regular</th>
                  <th colSpan="3">Peak Day (+£{safePricing.peak_day_increment})</th>
                </tr>
                <tr>
                  <th>Early</th>
                  <th>Standard</th>
                  <th>Late</th>
                  <th>Early</th>
                  <th>Standard</th>
                  <th>Late</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>1-4 Days</td>
                  <td>£{safePricing.days_1_4_price}</td>
                  <td>£{safePricing.days_1_4_price + safePricing.tier_increment}</td>
                  <td>£{safePricing.days_1_4_price + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.days_1_4_price + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.days_1_4_price + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.days_1_4_price + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
                <tr>
                  <td>5 Days</td>
                  <td>£{safePricing.days_1_4_price + safePricing.daily_increment}</td>
                  <td>£{safePricing.days_1_4_price + safePricing.daily_increment + safePricing.tier_increment}</td>
                  <td>£{safePricing.days_1_4_price + safePricing.daily_increment + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.days_1_4_price + safePricing.daily_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.days_1_4_price + safePricing.daily_increment + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.days_1_4_price + safePricing.daily_increment + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
                <tr>
                  <td>6 Days</td>
                  <td>£{safePricing.days_1_4_price + (safePricing.daily_increment * 2)}</td>
                  <td>£{safePricing.days_1_4_price + (safePricing.daily_increment * 2) + safePricing.tier_increment}</td>
                  <td>£{safePricing.days_1_4_price + (safePricing.daily_increment * 2) + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.days_1_4_price + (safePricing.daily_increment * 2) + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.days_1_4_price + (safePricing.daily_increment * 2) + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.days_1_4_price + (safePricing.daily_increment * 2) + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
                <tr>
                  <td>7 Days (1 Week)</td>
                  <td>£{safePricing.week1_base_price}</td>
                  <td>£{safePricing.week1_base_price + safePricing.tier_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.week1_base_price + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
                <tr>
                  <td>8 Days</td>
                  <td>£{safePricing.week1_base_price + safePricing.daily_increment}</td>
                  <td>£{safePricing.week1_base_price + safePricing.daily_increment + safePricing.tier_increment}</td>
                  <td>£{safePricing.week1_base_price + safePricing.daily_increment + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.week1_base_price + safePricing.daily_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + safePricing.daily_increment + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + safePricing.daily_increment + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
                <tr>
                  <td>9 Days</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 2)}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 2) + safePricing.tier_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 2) + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 2) + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 2) + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 2) + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
                <tr>
                  <td>10 Days</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 3)}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 3) + safePricing.tier_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 3) + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 3) + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 3) + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 3) + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
                <tr>
                  <td>11 Days</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 4)}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 4) + safePricing.tier_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 4) + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 4) + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 4) + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 4) + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
                <tr>
                  <td>12 Days</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 5)}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 5) + safePricing.tier_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 5) + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 5) + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 5) + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 5) + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
                <tr>
                  <td>13 Days</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 6)}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 6) + safePricing.tier_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 6) + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 6) + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 6) + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week1_base_price + (safePricing.daily_increment * 6) + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
                <tr>
                  <td>14 Days (2 Weeks)</td>
                  <td>£{safePricing.week2_base_price}</td>
                  <td>£{safePricing.week2_base_price + safePricing.tier_increment}</td>
                  <td>£{safePricing.week2_base_price + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.week2_base_price + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week2_base_price + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week2_base_price + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
                <tr>
                  <td>15 Days</td>
                  <td>£{safePricing.week2_base_price + safePricing.daily_increment}</td>
                  <td>£{safePricing.week2_base_price + safePricing.daily_increment + safePricing.tier_increment}</td>
                  <td>£{safePricing.week2_base_price + safePricing.daily_increment + (safePricing.tier_increment * 2)}</td>
                  <td>£{safePricing.week2_base_price + safePricing.daily_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week2_base_price + safePricing.daily_increment + safePricing.tier_increment + safePricing.peak_day_increment}</td>
                  <td>£{safePricing.week2_base_price + safePricing.daily_increment + (safePricing.tier_increment * 2) + safePricing.peak_day_increment}</td>
                </tr>
              </tbody>
            </table>
            <p className="pricing-preview-note">Peak Day: applies when drop-off is Fri/Sat OR pickup is Sun/Mon/Tue</p>
          </div>

          <div className="pricing-actions">
            <button
              className="pricing-save-btn"
              onClick={savePricing}
              disabled={savingPricing}
            >
              {savingPricing ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default PricingSection
