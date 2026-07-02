import React from 'react'
import DatePicker from 'react-datepicker'
import BookingLocationMap from '../../BookingLocationMap'

const ReportsSectionPage = ({
  abandonedCartsData,
  abandonedCartsPeriod,
  activeTab,
  bookingLocations,
  bookingStats,
  capacityForm,
  capacityMessage,
  capacitySettings,
  dateToUkString,
  editingFinancialBooking,
  expandedDailyMonths,
  expandedFinancialMonths,
  expandedRevenueDailyMonths,
  exportFinancialCSV,
  exportingFinancial,
  fetchAbandonedCarts,
  fetchBookingLocations,
  fetchBookingStats,
  fetchBookingsForecast,
  fetchFinancialReport,
  fetchFunFacts,
  fetchOccupancyReport,
  fetchSessionTracking,
  financialData,
  financialFromDate,
  financialPromoFilter,
  financialStatusFilter,
  financialToDate,
  forecastData,
  formatDateInput,
  funFacts,
  loadingAbandonedCarts,
  loadingCapacitySettings,
  loadingFinancial,
  loadingForecast,
  loadingFunFacts,
  loadingLocations,
  loadingOccupancy,
  loadingPopular,
  loadingSecondaryReport,
  loadingSessionTracking,
  loadingStats,
  mapType,
  occupancyChartMaxPercent,
  occupancyChartOffset,
  occupancyData,
  occupancyView,
  originLocations,
  parseUkDate,
  peakHoursView,
  peakSearchView,
  popularData,
  popularTop,
  reportsSubTab,
  revenueChartType,
  revenueWeeklyPageIndex,
  saveCapacitySettings,
  saveFinancialOverride,
  savingCapacitySettings,
  savingFinancialOverride,
  secondaryGroup,
  secondaryReport,
  sessionTrackingData,
  sessionTrackingPeriod,
  setAbandonedCartsPeriod,
  setCapacityForm,
  setEditingFinancialBooking,
  setExpandedDailyMonths,
  setExpandedFinancialMonths,
  setExpandedRevenueDailyMonths,
  setFinancialFromDate,
  setFinancialPromoFilter,
  setFinancialStatusFilter,
  setFinancialToDate,
  setMapType,
  setOccupancyChartOffset,
  setOccupancyView,
  setPeakHoursView,
  setPeakSearchView,
  setPopularTop,
  setRevenueChartType,
  setRevenueWeeklyPageIndex,
  setSecondaryGroup,
  setSessionTrackingPeriod,
  setStatsChartType,
  setWeeklyPageIndex,
  skippedBookings,
  statsChartType,
  totalBookings,
  totalCustomers,
  weeklyPageIndex,
}) => {
  // Day-level expansion inside the financial Monthly Breakdown, keyed
  // "monthKey|paidDateSort". Local state (not lifted to Admin.jsx) as nothing
  // else needs it. Must be declared before the activeTab early return.
  const [expandedFinancialDays, setExpandedFinancialDays] = React.useState({})

  if (activeTab !== 'reports') {
    return null
  }

  return (
              <div className="admin-section">
                <h2>
                  {reportsSubTab === 'growth' && 'Booking Growth'}
                  {reportsSubTab === 'financial' && 'Financial'}
                  {reportsSubTab === 'sessions' && 'Session Tracking'}
                  {reportsSubTab === 'analytics' && 'Abandoned Carts'}
                  {reportsSubTab === 'forecast' && 'Bookings Forecast'}
                  {reportsSubTab === 'occupancy' && 'Occupancy'}
                  {reportsSubTab === 'popular' && 'Popular Routes'}
                  {reportsSubTab === 'map' && 'Location Maps'}
                </h2>
    
                {/* Booking Growth Charts */}
                {reportsSubTab === 'growth' && (
                  <div className="booking-stats-section">
                    {loadingStats ? (
                      <div className="admin-loading-inline">
                        <div className="spinner-small"></div>
                        <span>Loading booking statistics...</span>
                      </div>
                    ) : bookingStats ? (
                      <>
                        {/* Section Header with Refresh */}
                        <div className="reports-section-header">
                          <button
                            className="refresh-page-btn"
                            onClick={() => { fetchBookingStats(); fetchFunFacts(true); }}
                            disabled={loadingStats || loadingFunFacts}
                          >
                            {loadingStats || loadingFunFacts ? 'Refreshing...' : 'Refresh Page'}
                          </button>
                        </div>
    
                        {/* Summary Cards */}
                        <div className="stats-summary-cards">
                          <div className="stats-card">
                            <div className="stats-card-value">{bookingStats.total_successful}</div>
                            <div className="stats-card-label">Total Successful Bookings</div>
                          </div>
                          <div className="stats-card">
                            <div className="stats-card-value">{bookingStats.this_month}</div>
                            <div className="stats-card-label">This Month</div>
                            {bookingStats.last_month > 0 && (
                              <div className={`stats-card-change ${bookingStats.this_month >= bookingStats.last_month ? 'positive' : 'negative'}`}>
                                {bookingStats.this_month >= bookingStats.last_month ? '+' : ''}{bookingStats.this_month - bookingStats.last_month} vs last month
                                {' '}({bookingStats.this_month >= bookingStats.last_month ? '+' : ''}{Math.round(((bookingStats.this_month - bookingStats.last_month) / bookingStats.last_month) * 100)}%)
                              </div>
                            )}
                          </div>
                          <div className="stats-card">
                            <div className="stats-card-value">{bookingStats.this_week}</div>
                            <div className="stats-card-label">This Week</div>
                            {bookingStats.last_week > 0 && (
                              <div className={`stats-card-change ${bookingStats.this_week >= bookingStats.last_week ? 'positive' : 'negative'}`}>
                                {bookingStats.this_week >= bookingStats.last_week ? '+' : ''}{bookingStats.this_week - bookingStats.last_week} vs last week
                                {' '}({bookingStats.this_week >= bookingStats.last_week ? '+' : ''}{Math.round(((bookingStats.this_week - bookingStats.last_week) / bookingStats.last_week) * 100)}%)
                              </div>
                            )}
                          </div>
                          <div className="stats-card revenue-card">
                            <div className="stats-card-value">&pound;{bookingStats.avg_revenue_per_customer?.toFixed(2) || '0.00'}</div>
                            <div className="stats-card-label">Avg Revenue per Customer</div>
                            <div className="stats-card-subtext">
                              &pound;{bookingStats.total_revenue?.toFixed(2) || '0.00'} total from {bookingStats.paid_customer_count || 0} paid bookings
                            </div>
                          </div>
                        </div>
    
                        {/* Trip Insights */}
                        <div className="trip-insights-section">
                          <h3>Trip Insights</h3>
                          <div className="trip-insights-grid">
                            <div className="trip-insight-card">
                              <span className="trip-insight-icon">📊</span>
                              <div className="trip-insight-content">
                                <span className="trip-insight-label">Avg Trip Duration</span>
                                <span className="trip-insight-value">{bookingStats.avg_trip_duration || 0} days</span>
                                {bookingStats.top_durations?.length > 0 && (
                                  <div className="trip-insight-busiest-section">
                                    <span className="trip-insight-busiest-label">Top 10:</span>
                                    {bookingStats.top_durations.map((d, i) => (
                                      <span key={i} className="trip-insight-busiest">
                                        {d.days} day{d.days !== 1 ? 's' : ''} ({d.count} · {d.percent}%)
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                            <div className="trip-insight-card">
                              <span className="trip-insight-icon">🚗</span>
                              <div className="trip-insight-content">
                                <span className="trip-insight-label">Drop-off Times</span>
                                <span className="trip-insight-value">
                                  AM: {bookingStats.dropoff_range?.am || 0} | PM: {bookingStats.dropoff_range?.pm || 0}
                                </span>
                                {bookingStats.dropoff_range?.am_busiest?.length > 0 && (
                                  <div className="trip-insight-busiest-section">
                                    <span className="trip-insight-busiest-label">AM Busiest:</span>
                                    {bookingStats.dropoff_range.am_busiest.map((h, i) => (
                                      <span key={i} className="trip-insight-busiest">
                                        {h.start} - {h.end} ({h.count})
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {bookingStats.dropoff_range?.pm_busiest?.length > 0 && (
                                  <div className="trip-insight-busiest-section">
                                    <span className="trip-insight-busiest-label">PM Busiest:</span>
                                    {bookingStats.dropoff_range.pm_busiest.map((h, i) => (
                                      <span key={i} className="trip-insight-busiest">
                                        {h.start} - {h.end} ({h.count})
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                            <div className="trip-insight-card">
                              <span className="trip-insight-icon">✈️</span>
                              <div className="trip-insight-content">
                                <span className="trip-insight-label">Pick-up Times</span>
                                <span className="trip-insight-value">
                                  AM: {bookingStats.pickup_range?.am || 0} | PM: {bookingStats.pickup_range?.pm || 0}
                                </span>
                                {bookingStats.pickup_range?.am_busiest?.length > 0 && (
                                  <div className="trip-insight-busiest-section">
                                    <span className="trip-insight-busiest-label">AM Busiest:</span>
                                    {bookingStats.pickup_range.am_busiest.map((h, i) => (
                                      <span key={i} className="trip-insight-busiest">
                                        {h.start} - {h.end} ({h.count})
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {bookingStats.pickup_range?.pm_busiest?.length > 0 && (
                                  <div className="trip-insight-busiest-section">
                                    <span className="trip-insight-busiest-label">PM Busiest:</span>
                                    {bookingStats.pickup_range.pm_busiest.map((h, i) => (
                                      <span key={i} className="trip-insight-busiest">
                                        {h.start} - {h.end} ({h.count})
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
    
                        {/* Busiest Booking Days (when customers make bookings) */}
                        {bookingStats.booking_days_of_week && bookingStats.booking_days_of_week.length > 0 && (
                          <div className="booking-days-section">
                            <h3>Busiest Booking Days</h3>
                            <p className="section-subtitle">When customers make their bookings (UK time)</p>
                            <div className="day-of-week-chart">
                              {(() => {
                                const maxCount = Math.max(...bookingStats.booking_days_of_week.map(d => d.count));
                                return bookingStats.booking_days_of_week.map((day, index) => (
                                  <div key={index} className="day-bar-container">
                                    <div className="day-label">{day.day.substring(0, 3)}</div>
                                    <div className="day-bar-wrapper">
                                      <div
                                        className="day-bar"
                                        style={{
                                          height: `${maxCount > 0 ? (day.count / maxCount) * 100 : 0}%`,
                                          backgroundColor: day.count === maxCount ? '#22c55e' : '#3b82f6'
                                        }}
                                      />
                                    </div>
                                    <div className="day-count">{day.count}</div>
                                    <div className="day-percent">{day.percent}%</div>
                                  </div>
                                ));
                              })()}
                            </div>
                          </div>
                        )}
    
                        {/* Peak Booking Hours (UK timezone) */}
                        {bookingStats.booking_hours_of_day && bookingStats.booking_hours_of_day.length > 0 && (
                          <div className="booking-hours-section">
                            <h3>Peak Booking Hours</h3>
                            <p className="section-subtitle">When customers make their bookings (UK time)</p>
    
                            {/* View Switcher */}
                            <div className="peak-hours-view-switcher">
                              <button
                                className={`view-switch-btn ${peakHoursView === 'overall' ? 'active' : ''}`}
                                onClick={() => setPeakHoursView('overall')}
                              >
                                Overall
                              </button>
                              {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map(day => (
                                <button
                                  key={day}
                                  className={`view-switch-btn ${peakHoursView === day ? 'active' : ''}`}
                                  onClick={() => setPeakHoursView(day)}
                                >
                                  {day.substring(0, 3)}
                                </button>
                              ))}
                            </div>
    
                            {/* Time Ranges Summary - only show for overall view */}
                            {peakHoursView === 'overall' && bookingStats.booking_time_ranges && (
                              <div className="time-ranges-grid">
                                {bookingStats.booking_time_ranges.map((range, index) => (
                                  <div key={index} className="time-range-card">
                                    <div className="time-range-label">{range.label.split(' ')[0]}</div>
                                    <div className="time-range-hours">{range.label.match(/\(([^)]+)\)/)?.[1]}</div>
                                    <div className="time-range-count">{range.count}</div>
                                    <div className="time-range-percent">{range.percent}%</div>
                                  </div>
                                ))}
                              </div>
                            )}
    
                            {/* Day-specific total */}
                            {peakHoursView !== 'overall' && bookingStats.booking_hours_by_day?.[peakHoursView] && (
                              <div className="day-specific-summary">
                                <span className="day-total-label">{peakHoursView}s:</span>
                                <span className="day-total-count">{bookingStats.booking_hours_by_day[peakHoursView].total} bookings</span>
                              </div>
                            )}
    
                            {/* Hourly Breakdown Chart */}
                            <div className="hourly-chart">
                              {(() => {
                                const hoursData = peakHoursView === 'overall'
                                  ? bookingStats.booking_hours_of_day
                                  : bookingStats.booking_hours_by_day?.[peakHoursView]?.hours || [];
                                const maxCount = Math.max(...hoursData.map(h => h.count), 1);
    
                                return hoursData.map((hour, index) => (
                                  <div key={index} className="hour-bar-container">
                                    <div className="hour-bar-wrapper">
                                      <div
                                        className="hour-bar"
                                        style={{
                                          height: `${maxCount > 0 ? (hour.count / maxCount) * 100 : 0}%`,
                                          backgroundColor: hour.count === maxCount ? '#22c55e' : '#3b82f6'
                                        }}
                                        title={`${hour.label}: ${hour.count} bookings (${hour.percent}%)`}
                                      />
                                    </div>
                                    <div className="hour-label">{hour.hour}</div>
                                  </div>
                                ));
                              })()}
                            </div>
                            <p className="chart-helper-text">Hours shown in 24-hour format (UK timezone)</p>
                          </div>
                        )}
    
                        {/* Peak Search Hours (UK timezone) */}
                        {bookingStats.search_hours_of_day && bookingStats.search_hours_of_day.length > 0 && bookingStats.total_searches > 0 && (
                          <div className="booking-hours-section search-hours-section">
                            <h3>Peak Search Hours</h3>
                            <p className="section-subtitle">When customers search for quotes (UK time)</p>
    
                            {/* View Switcher */}
                            <div className="peak-hours-view-switcher">
                              <button
                                className={`view-switch-btn ${peakSearchView === 'overall' ? 'active' : ''}`}
                                onClick={() => setPeakSearchView('overall')}
                              >
                                Overall
                              </button>
                              {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map(day => (
                                <button
                                  key={day}
                                  className={`view-switch-btn ${peakSearchView === day ? 'active' : ''}`}
                                  onClick={() => setPeakSearchView(day)}
                                >
                                  {day.substring(0, 3)}
                                </button>
                              ))}
                            </div>
    
                            {/* Time Ranges Summary - only show for overall view */}
                            {peakSearchView === 'overall' && bookingStats.search_time_ranges && (
                              <div className="time-ranges-grid">
                                {bookingStats.search_time_ranges.map((range, index) => (
                                  <div key={index} className="time-range-card search">
                                    <div className="time-range-label">{range.label.split(' ')[0]}</div>
                                    <div className="time-range-hours">{range.label.match(/\(([^)]+)\)/)?.[1]}</div>
                                    <div className="time-range-count">{range.count}</div>
                                    <div className="time-range-percent">{range.percent}%</div>
                                  </div>
                                ))}
                              </div>
                            )}
    
                            {/* Day-specific total */}
                            {peakSearchView !== 'overall' && bookingStats.search_hours_by_day?.[peakSearchView] && (
                              <div className="day-specific-summary">
                                <span className="day-total-label">{peakSearchView}s:</span>
                                <span className="day-total-count">{bookingStats.search_hours_by_day[peakSearchView].total} searches</span>
                              </div>
                            )}
    
                            {/* Hourly Breakdown Chart */}
                            <div className="hourly-chart">
                              {(() => {
                                const hoursData = peakSearchView === 'overall'
                                  ? bookingStats.search_hours_of_day
                                  : bookingStats.search_hours_by_day?.[peakSearchView]?.hours || [];
                                const maxCount = Math.max(...hoursData.map(h => h.count), 1);
    
                                return hoursData.map((hour, index) => (
                                  <div key={index} className="hour-bar-container">
                                    <div className="hour-bar-wrapper">
                                      <div
                                        className="hour-bar search"
                                        style={{
                                          height: `${maxCount > 0 ? (hour.count / maxCount) * 100 : 0}%`,
                                          backgroundColor: hour.count === maxCount ? '#f97316' : '#fb923c'
                                        }}
                                        title={`${hour.label}: ${hour.count} searches (${hour.percent}%)`}
                                      />
                                    </div>
                                    <div className="hour-label">{hour.hour}</div>
                                  </div>
                                ));
                              })()}
                            </div>
                            <p className="chart-helper-text">Hours shown in 24-hour format (UK timezone)</p>
                            {bookingStats.search_data_start_date && (
                              <p className="chart-footnote">* Session tracking went live {bookingStats.search_data_start_date}</p>
                            )}
                          </div>
                        )}
    
                        {/* Google Ads Bid Recommendations */}
                        {bookingStats?.bid_recommendations && bookingStats.bid_recommendations.length > 0 && (
                          <div className="bid-recommendations-section">
                            <h3>Google Ads Bid Recommendations</h3>
                            <p className="section-subtitle">
                              Daily recommendations based on search volume and conversion rates since {bookingStats.search_data_start_date}.
                              <br />
                              <strong>{bookingStats.total_searches}</strong> searches → <strong>{bookingStats.bid_total_bookings}</strong> bookings = <strong>{bookingStats.overall_conversion_rate}%</strong> conversion
                            </p>
                            <div className="bid-recommendations-grid">
                              {bookingStats.bid_recommendations.map((rec) => (
                                <div
                                  key={rec.day}
                                  className={`bid-recommendation-card ${rec.recommendation} priority-${rec.priority}`}
                                >
                                  <div className="bid-rec-header">
                                    <span className="bid-rec-day">{rec.day}</span>
                                    <span className={`bid-rec-badge ${rec.recommendation}`}>
                                      {rec.recommendation === 'increase' && '↑ Increase'}
                                      {rec.recommendation === 'maintain' && '→ Maintain'}
                                      {rec.recommendation === 'reduce' && '↓ Reduce'}
                                    </span>
                                  </div>
                                  <div className="bid-rec-stats">
                                    <div className="bid-rec-stat">
                                      <span className="stat-value">{rec.searches}</span>
                                      <span className="stat-label">Searches</span>
                                    </div>
                                    <div className="bid-rec-stat">
                                      <span className="stat-value">{rec.bookings}</span>
                                      <span className="stat-label">Bookings</span>
                                    </div>
                                    <div className="bid-rec-stat">
                                      <span className="stat-value">{rec.conversion_rate}%</span>
                                      <span className="stat-label">Conversion</span>
                                    </div>
                                  </div>
                                  <p className="bid-rec-reason">{rec.reason}</p>
                                  {rec.peak_search_hours.length > 0 && (
                                    <div className="bid-rec-peak-hours">
                                      <span className="peak-hours-label">Peak search hours:</span>
                                      <span className="peak-hours-value">{rec.peak_search_hours.join(', ')}</span>
                                    </div>
                                  )}
                                  {rec.high_converting_hours.length > 0 && (
                                    <div className="bid-rec-converting-hours">
                                      <span className="converting-hours-label">Best converting:</span>
                                      <span className="converting-hours-value">
                                        {rec.high_converting_hours.map(h => `${h.label} (${h.conversion_rate}%)`).join(', ')}
                                      </span>
                                    </div>
                                  )}
                                </div>
                              ))}
                              {/* Overall Summary Card */}
                              <div className="bid-recommendation-card overall">
                                <div className="bid-rec-header">
                                  <span className="bid-rec-day">Overall</span>
                                  <span className="bid-rec-badge overall">Summary</span>
                                </div>
                                <div className="bid-rec-stats">
                                  <div className="bid-rec-stat">
                                    <span className="stat-value">{bookingStats.total_searches}</span>
                                    <span className="stat-label">Searches</span>
                                  </div>
                                  <div className="bid-rec-stat">
                                    <span className="stat-value">{bookingStats.bid_total_bookings}</span>
                                    <span className="stat-label">Bookings</span>
                                  </div>
                                  <div className="bid-rec-stat">
                                    <span className="stat-value">{bookingStats.overall_conversion_rate}%</span>
                                    <span className="stat-label">Conversion</span>
                                  </div>
                                </div>
                                <p className="bid-rec-reason">
                                  {bookingStats.overall_conversion_rate >= 50
                                    ? 'Strong conversion rate - campaigns performing well'
                                    : bookingStats.overall_conversion_rate >= 30
                                    ? 'Good conversion rate - room for optimization'
                                    : 'Focus on high-converting days for better ROI'}
                                </p>
                              </div>
                            </div>
                          </div>
                        )}
    
                        {/* Monthly Booking Pattern (payday hypothesis) */}
                        {bookingStats?.monthly_booking_pattern && bookingStats.monthly_booking_pattern.months.length > 0 && (
                          <div className="monthly-pattern-section">
                            <h3>Monthly Booking Pattern</h3>
                            <p className="section-subtitle">
                              Bookings (confirmed + completed, all sources) grouped by week-of-month.
                              Testing whether bookings cluster around UK monthly payday.
                              <br />
                              <strong>Year:</strong> {bookingStats.monthly_booking_pattern.year}
                            </p>
                            <div className="monthly-pattern-grid">
                              {bookingStats.monthly_booking_pattern.months.map((month) => {
                                const max = Math.max(...month.buckets.map(b => b.count), 1)
                                return (
                                  <div key={month.month} className="monthly-pattern-card">
                                    <div className="monthly-pattern-header">
                                      <span className="monthly-pattern-label">{month.label}</span>
                                      <span className="monthly-pattern-total">{month.total} bookings</span>
                                    </div>
                                    <div className="monthly-pattern-bars">
                                      {month.buckets.map((b) => (
                                        <div
                                          key={b.key}
                                          className={`monthly-pattern-bar-row ${b.key === month.busiest_bucket ? 'busiest' : ''}`}
                                        >
                                          <span className="bucket-label">{b.label}</span>
                                          <div className="bucket-bar-track">
                                            <div
                                              className="bucket-bar-fill"
                                              style={{ width: `${(b.count / max) * 100}%` }}
                                            />
                                          </div>
                                          <span className="bucket-count">{b.count}</span>
                                        </div>
                                      ))}
                                    </div>
                                    {month.busiest_bucket && (
                                      <p className="monthly-pattern-insight">
                                        Busiest: <strong>{month.buckets.find(b => b.key === month.busiest_bucket)?.label}</strong>
                                      </p>
                                    )}
                                  </div>
                                )
                              })}
                              {/* Overall card */}
                              {(() => {
                                const overall = bookingStats.monthly_booking_pattern.overall
                                const max = Math.max(...overall.buckets.map(b => b.count), 1)
                                return (
                                  <div className="monthly-pattern-card overall">
                                    <div className="monthly-pattern-header">
                                      <span className="monthly-pattern-label">Overall</span>
                                      <span className="monthly-pattern-total">{overall.total} bookings</span>
                                    </div>
                                    <div className="monthly-pattern-bars">
                                      {overall.buckets.map((b) => (
                                        <div
                                          key={b.key}
                                          className={`monthly-pattern-bar-row ${b.key === overall.busiest_bucket ? 'busiest' : ''}`}
                                        >
                                          <span className="bucket-label">{b.label}</span>
                                          <div className="bucket-bar-track">
                                            <div
                                              className="bucket-bar-fill"
                                              style={{ width: `${(b.count / max) * 100}%` }}
                                            />
                                          </div>
                                          <span className="bucket-count">{b.count}</span>
                                        </div>
                                      ))}
                                    </div>
                                    {overall.busiest_bucket && (
                                      <p className="monthly-pattern-insight">
                                        Busiest overall: <strong>{overall.buckets.find(b => b.key === overall.busiest_bucket)?.label}</strong>
                                      </p>
                                    )}
                                  </div>
                                )
                              })()}
                            </div>
                          </div>
                        )}
    
                        {/* Fun Facts */}
                        {funFacts && (
                          <div className="fun-facts-section">
                            <h3>Fun Facts</h3>
                            <div className="fun-facts-grid">
                              {funFacts.busiestDay && (
                                <div className="fun-fact-card">
                                  <span className="fun-fact-icon">📅</span>
                                  <div className="fun-fact-content">
                                    <span className="fun-fact-label">Busiest {funFacts.busiestDay.dates?.length > 1 ? 'Days' : 'Day'}</span>
                                    <span className="fun-fact-value">{funFacts.busiestDay.count} bookings</span>
                                    {funFacts.busiestDay.dates?.map((date, index) => (
                                      <span key={index} className="fun-fact-detail">{date}</span>
                                    ))}
                                  </div>
                                </div>
                              )}
                              {funFacts.busiestWeek && (
                                <div className="fun-fact-card">
                                  <span className="fun-fact-icon">📈</span>
                                  <div className="fun-fact-content">
                                    <span className="fun-fact-label">Busiest Week</span>
                                    <span className="fun-fact-value">{funFacts.busiestWeek.bookings} bookings</span>
                                    <span className="fun-fact-detail">{funFacts.busiestWeek.startDate} - {funFacts.busiestWeek.endDate}</span>
                                  </div>
                                </div>
                              )}
                              {funFacts.busiestMonth && (
                                <div className="fun-fact-card">
                                  <span className="fun-fact-icon">🗓️</span>
                                  <div className="fun-fact-content">
                                    <span className="fun-fact-label">Busiest Month</span>
                                    <span className="fun-fact-value">{funFacts.busiestMonth.bookings} bookings</span>
                                    <span className="fun-fact-detail">{funFacts.busiestMonth.month}</span>
                                  </div>
                                </div>
                              )}
                              {funFacts.busiestStreak && (
                                <div className="fun-fact-card">
                                  <span className="fun-fact-icon">🔥</span>
                                  <div className="fun-fact-content">
                                    <span className="fun-fact-label">Busiest Streak</span>
                                    <span className="fun-fact-value">{funFacts.busiestStreak.days} consecutive days</span>
                                    <span className="fun-fact-detail">{funFacts.busiestStreak.startDate} - {funFacts.busiestStreak.endDate} ({funFacts.busiestStreak.bookings} bookings)</span>
                                  </div>
                                </div>
                              )}
                              {funFacts.longestTrip && (
                                <div className="fun-fact-card">
                                  <span className="fun-fact-icon">✈️</span>
                                  <div className="fun-fact-content">
                                    <span className="fun-fact-label">Longest Trip</span>
                                    <span className="fun-fact-value">{funFacts.longestTrip.days} days</span>
                                    <span className="fun-fact-detail">{funFacts.longestTrip.customerName || funFacts.longestTrip.dates}</span>
                                  </div>
                                </div>
                              )}
                              {funFacts.highestTransaction && (
                                <div className="fun-fact-card">
                                  <span className="fun-fact-icon">💰</span>
                                  <div className="fun-fact-content">
                                    <span className="fun-fact-label">Highest Transaction</span>
                                    <span className="fun-fact-value">{funFacts.highestTransaction.amount}</span>
                                    <span className="fun-fact-detail">{funFacts.highestTransaction.customerName || `${funFacts.highestTransaction.days} day trip`}</span>
                                  </div>
                                </div>
                              )}
                              {funFacts.latestTimeOfNight && (
                                <div className="fun-fact-card">
                                  <span className="fun-fact-icon">🌙</span>
                                  <div className="fun-fact-content">
                                    <span className="fun-fact-label">Latest Night Owl</span>
                                    <span className="fun-fact-value">{funFacts.latestTimeOfNight.time}</span>
                                    <span className="fun-fact-detail">{funFacts.latestTimeOfNight.customerName || funFacts.latestTimeOfNight.date}</span>
                                  </div>
                                </div>
                              )}
                              {funFacts.earliestTimeOfDay && (
                                <div className="fun-fact-card">
                                  <span className="fun-fact-icon">🌅</span>
                                  <div className="fun-fact-content">
                                    <span className="fun-fact-label">Earliest Riser</span>
                                    <span className="fun-fact-value">{funFacts.earliestTimeOfDay.time}</span>
                                    <span className="fun-fact-detail">{funFacts.earliestTimeOfDay.customerName || funFacts.earliestTimeOfDay.date}</span>
                                  </div>
                                </div>
                              )}
                              {funFacts.lastMinuteBooking && (
                                <div className="fun-fact-card">
                                  <span className="fun-fact-icon">⚡</span>
                                  <div className="fun-fact-content">
                                    <span className="fun-fact-label">Last Minute Booking</span>
                                    <span className="fun-fact-value">
                                      {funFacts.lastMinuteBooking.gapDays === 0
                                        ? (funFacts.lastMinuteBooking.gapTime || 'Same day')
                                        : `${funFacts.lastMinuteBooking.gapDays} day${funFacts.lastMinuteBooking.gapDays !== 1 ? 's' : ''} before`}
                                    </span>
                                    <span className="fun-fact-detail">{funFacts.lastMinuteBooking.customerName || (funFacts.lastMinuteBooking.gapDays === 0 ? 'before drop-off' : `Drop-off: ${funFacts.lastMinuteBooking.dropoffDate}`)}</span>
                                  </div>
                                </div>
                              )}
                              {funFacts.advanceBooking && (
                                <div className="fun-fact-card">
                                  <span className="fun-fact-icon">📆</span>
                                  <div className="fun-fact-content">
                                    <span className="fun-fact-label">Most Advance Booking</span>
                                    <span className="fun-fact-value">
                                      {funFacts.advanceBooking.gapDetailed
                                        ? `${funFacts.advanceBooking.gapDetailed.months}m ${funFacts.advanceBooking.gapDetailed.days}d ${String(funFacts.advanceBooking.gapDetailed.hours).padStart(2, '0')}:${String(funFacts.advanceBooking.gapDetailed.minutes).padStart(2, '0')}:${String(funFacts.advanceBooking.gapDetailed.seconds).padStart(2, '0')}`
                                        : `${funFacts.advanceBooking.gapDays} days ahead`}
                                    </span>
                                    <span className="fun-fact-detail">{funFacts.advanceBooking.customerName || 'before drop-off'}</span>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
    
                        {/* Milestones */}
                        {funFacts?.milestones?.length > 0 && (
                          <div className="milestones-section">
                            <h3>Booking Milestones</h3>
                            <div className="milestones-grid">
                              {funFacts.milestones.map((milestone) => (
                                <div key={milestone.number} className={`milestone-card milestone-${milestone.number === 1 ? 'first' : milestone.number >= 100 ? 'century' : 'standard'}`}>
                                  <div className="milestone-badge">
                                    <span className="milestone-number">{milestone.label}</span>
                                    <span className="milestone-label">booking</span>
                                  </div>
                                  <div className="milestone-details">
                                    {milestone.customerName && (
                                      <span className="milestone-customer">{milestone.customerName}</span>
                                    )}
                                    <span className="milestone-datetime">{milestone.date} at {milestone.time}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
    
                        {/* Booking Targets */}
                        {bookingStats && (
                          <div className="booking-targets-section">
                            <h3>Booking Targets</h3>
                            <div className="booking-targets-grid">
                              <div className="booking-target-card">
                                <span className="booking-target-icon">📅</span>
                                <div className="booking-target-content">
                                  <span className="booking-target-label">Daily Target</span>
                                  <span className="booking-target-value">{bookingStats.confirmed_today || 0} bookings today</span>
                                  <div className="booking-target-milestones">
                                    {[1, 2, 3, 4, 5, 10, 15, 20, 25, 30].map(target => (
                                      <span key={target} className={`milestone ${(bookingStats.confirmed_today || 0) >= target ? 'achieved' : ''}`}>
                                        {target}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              </div>
                              <div className="booking-target-card">
                                <span className="booking-target-icon">📆</span>
                                <div className="booking-target-content">
                                  <span className="booking-target-label">Weekly Target</span>
                                  <span className="booking-target-value">{bookingStats.confirmed_this_week || 0} bookings this week</span>
                                  <div className="booking-target-milestones">
                                    {[1, 5, 10, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100].map(target => (
                                      <span key={target} className={`milestone ${(bookingStats.confirmed_this_week || 0) >= target ? 'achieved' : ''}`}>
                                        {target}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              </div>
                              <div className="booking-target-card">
                                <span className="booking-target-icon">🗓️</span>
                                <div className="booking-target-content">
                                  <span className="booking-target-label">Monthly Target</span>
                                  <span className="booking-target-value">{bookingStats.confirmed_this_month || 0} bookings this month</span>
                                  <div className="booking-target-milestones">
                                    {[1, 10, 25, 50, 75, 100, 125, 150, 175, 200, 250, 300, 350].map(target => (
                                      <span key={target} className={`milestone ${(bookingStats.confirmed_this_month || 0) >= target ? 'achieved' : ''}`}>
                                        {target}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              </div>
                              <div className="booking-target-card">
                                <span className="booking-target-icon">🏆</span>
                                <div className="booking-target-content">
                                  <span className="booking-target-label">Total Milestones</span>
                                  <span className="booking-target-value">{bookingStats.total_successful || 0} total bookings</span>
                                  <div className="booking-target-milestones milestones-wrap">
                                    {[1, 10, 25, 50, 75, 100, 150, 250, 500, 750, 1000].map(target => (
                                      <span key={target} className={`milestone ${(bookingStats.total_successful || 0) >= target ? 'achieved' : ''}`}>
                                        {target}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        )}
    
                        {/* Status Breakdown */}
                        {bookingStats.status_totals && (
                          <div className="status-breakdown">
                            <h3>Status Breakdown</h3>
                            <div className="status-breakdown-grid">
                              <div className="status-item status-confirmed">
                                <span className="status-dot"></span>
                                <span className="status-label">Confirmed</span>
                                <span className="status-count">{bookingStats.status_totals.confirmed || 0}</span>
                              </div>
                              <div className="status-item status-completed">
                                <span className="status-dot"></span>
                                <span className="status-label">Completed</span>
                                <span className="status-count">{bookingStats.status_totals.completed || 0}</span>
                              </div>
                              <div className="status-item status-pending">
                                <span className="status-dot"></span>
                                <span className="status-label">Pending</span>
                                <span className="status-count">{bookingStats.status_totals.pending || 0}</span>
                              </div>
                              <div className="status-item status-cancelled">
                                <span className="status-dot"></span>
                                <span className="status-label">Cancelled</span>
                                <span className="status-count">{bookingStats.status_totals.cancelled || 0}</span>
                              </div>
                            </div>
                          </div>
                        )}
    
                        {/* Chart Type Selector */}
                        <div className="chart-controls">
                          <label>View:</label>
                          <select value={statsChartType} onChange={e => setStatsChartType(e.target.value)}>
                            <option value="monthly">Monthly</option>
                            <option value="weekly">Weekly</option>
                            <option value="daily">Daily</option>
                            <option value="cumulative">Cumulative Growth</option>
                          </select>
                          <button
                            className="refresh-stats-btn"
                            onClick={() => fetchBookingStats()}
                            disabled={loadingStats}
                          >
                            {loadingStats ? 'Refreshing...' : 'Refresh Data'}
                          </button>
                        </div>
    
                        {/* Stacked Bar Chart */}
                        <div className="booking-chart">
                          <h3>
                            {statsChartType === 'monthly' && 'Bookings by Month'}
                            {statsChartType === 'weekly' && 'Bookings by Week'}
                            {statsChartType === 'daily' && 'Bookings by Day'}
                            {statsChartType === 'cumulative' && 'Cumulative Growth'}
                          </h3>
                          <div className="chart-container">
                            {statsChartType === 'cumulative' ? (
                              <div className="line-chart">
                                {bookingStats.cumulative.length > 0 && (
                                  <>
                                    <div className="chart-y-axis">
                                      <span>{Math.max(...bookingStats.cumulative.map(d => d.total))}</span>
                                      <span>{Math.round(Math.max(...bookingStats.cumulative.map(d => d.total)) / 2)}</span>
                                      <span>0</span>
                                    </div>
                                    <div className="chart-area">
                                      <svg viewBox={`0 0 ${Math.min(bookingStats.cumulative.length * 30, 1200)} 200`} preserveAspectRatio="none">
                                        <defs>
                                          <linearGradient id="lineGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                            <stop offset="0%" stopColor="#22c55e" stopOpacity="0.3"/>
                                            <stop offset="100%" stopColor="#22c55e" stopOpacity="0.05"/>
                                          </linearGradient>
                                        </defs>
                                        {(() => {
                                          const maxVal = Math.max(...bookingStats.cumulative.map(d => d.total))
                                          const width = Math.min(bookingStats.cumulative.length * 30, 1200)
                                          const points = bookingStats.cumulative.map((d, i) => {
                                            const x = (i / (bookingStats.cumulative.length - 1)) * width
                                            const y = 200 - (d.total / maxVal) * 180
                                            return `${x},${y}`
                                          }).join(' ')
                                          const areaPoints = `0,200 ${points} ${width},200`
                                          return (
                                            <>
                                              <polygon points={areaPoints} fill="url(#lineGradient)" />
                                              <polyline points={points} fill="none" stroke="#22c55e" strokeWidth="2" />
                                            </>
                                          )
                                        })()}
                                      </svg>
                                    </div>
                                  </>
                                )}
                              </div>
                            ) : statsChartType === 'weekly' ? (
                              /* Weekly view with navigation */
                              <div className="weekly-chart-container">
                                {(() => {
                                  const data = bookingStats.weekly
                                  const weeksPerPage = 8
                                  const totalPages = Math.ceil(data.length / weeksPerPage)
                                  const startIdx = Math.max(0, data.length - weeksPerPage - (weeklyPageIndex * weeksPerPage))
                                  const endIdx = Math.min(data.length, startIdx + weeksPerPage)
                                  const displayData = data.slice(startIdx, endIdx)
                                  const maxTotal = Math.max(...data.map(d => d.total), 1)
    
                                  return (
                                    <>
                                      <div className="chart-navigation">
                                        <button
                                          className="nav-btn"
                                          onClick={() => setWeeklyPageIndex(prev => Math.min(prev + 1, totalPages - 1))}
                                          disabled={weeklyPageIndex >= totalPages - 1}
                                        >
                                          &larr; Older
                                        </button>
                                        <span className="nav-info">
                                          Showing weeks {startIdx + 1}-{endIdx} of {data.length}
                                        </span>
                                        <button
                                          className="nav-btn"
                                          onClick={() => setWeeklyPageIndex(prev => Math.max(prev - 1, 0))}
                                          disabled={weeklyPageIndex <= 0}
                                        >
                                          Newer &rarr;
                                        </button>
                                      </div>
                                      <div className="stacked-bar-chart">
                                        {displayData.map((item, idx) => (
                                          <div key={idx} className="bar-column">
                                            <div className="bar-stack" style={{ height: '150px' }}>
                                              {['cancelled', 'pending', 'completed', 'confirmed'].map(status => {
                                                const value = item[status] || 0
                                                const height = (value / maxTotal) * 100
                                                return value > 0 ? (
                                                  <div
                                                    key={status}
                                                    className={`bar-segment bar-${status}`}
                                                    style={{ height: `${height}%` }}
                                                    title={`${status}: ${value}`}
                                                  />
                                                ) : null
                                              })}
                                            </div>
                                            <div className="bar-label">
                                              {(() => {
                                                const match = (item.week || '').match(/(\d{4})-W(\d{2})/)
                                                if (!match) return item.week
                                                const [, year, week] = match
                                                const startDate = new Date(year, 0, 1 + (parseInt(week, 10) - 1) * 7)
                                                const dayOfWeek = startDate.getDay()
                                                const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
                                                startDate.setDate(startDate.getDate() + diff)
                                                const endDate = new Date(startDate)
                                                endDate.setDate(startDate.getDate() + 6)
                                                return `${startDate.getDate()}/${startDate.getMonth() + 1}-${endDate.getDate()}/${endDate.getMonth() + 1}`
                                              })()}
                                            </div>
                                            <div className="bar-total">{item.total}</div>
                                          </div>
                                        ))}
                                      </div>
                                    </>
                                  )
                                })()}
                              </div>
                            ) : statsChartType === 'daily' ? (
                              /* Daily view with monthly containers */
                              <div className="daily-chart-container">
                                {(() => {
                                  const data = bookingStats.daily
                                  // Group daily data by month
                                  const monthlyGroups = {}
                                  data.forEach(item => {
                                    const monthKey = item.date?.slice(0, 7) // "2026-01"
                                    if (monthKey) {
                                      if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
                                      monthlyGroups[monthKey].push(item)
                                    }
                                  })
                                  const sortedMonths = Object.keys(monthlyGroups).sort().reverse()
                                  const maxTotal = Math.max(...data.map(d => d.total), 1)
                                  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    
                                  return sortedMonths.map(monthKey => {
                                    const [year, month] = monthKey.split('-')
                                    const monthName = `${monthNames[parseInt(month, 10) - 1]} ${year}`
                                    const monthData = monthlyGroups[monthKey]
                                    const monthTotal = monthData.reduce((sum, d) => sum + d.total, 0)
                                    const isExpanded = expandedDailyMonths[monthKey]
    
                                    return (
                                      <div key={monthKey} className="daily-month-container">
                                        <div
                                          className="daily-month-header"
                                          onClick={() => setExpandedDailyMonths(prev => ({
                                            ...prev,
                                            [monthKey]: !prev[monthKey]
                                          }))}
                                        >
                                          <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                                          <span className="month-name">{monthName}</span>
                                          <span className="month-total">{monthTotal} bookings</span>
                                        </div>
                                        {isExpanded && (
                                          <div className="stacked-bar-chart daily-bars">
                                            {monthData.map((item, idx) => (
                                              <div key={idx} className="bar-column">
                                                <div className="bar-stack" style={{ height: '120px' }}>
                                                  {['cancelled', 'pending', 'completed', 'confirmed'].map(status => {
                                                    const value = item[status] || 0
                                                    const height = (value / maxTotal) * 100
                                                    return value > 0 ? (
                                                      <div
                                                        key={status}
                                                        className={`bar-segment bar-${status}`}
                                                        style={{ height: `${height}%` }}
                                                        title={`${status}: ${value}`}
                                                      />
                                                    ) : null
                                                  })}
                                                </div>
                                                <div className="bar-label">
                                                  {(() => {
                                                    const [, , day] = (item.date || '').split('-')
                                                    return day || item.date
                                                  })()}
                                                </div>
                                                <div className="bar-total">{item.total}</div>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    )
                                  })
                                })()}
                              </div>
                            ) : (
                              /* Monthly view (default) */
                              <div className="stacked-bar-chart">
                                {(() => {
                                  const data = bookingStats.monthly
                                  const maxTotal = Math.max(...data.map(d => d.total), 1)
                                  const displayData = data.slice(-12) // Show last 12 months
                                  return displayData.map((item, idx) => (
                                    <div key={idx} className="bar-column">
                                      <div className="bar-stack" style={{ height: '150px' }}>
                                        {['cancelled', 'pending', 'completed', 'confirmed'].map(status => {
                                          const value = item[status] || 0
                                          const height = (value / maxTotal) * 100
                                          return value > 0 ? (
                                            <div
                                              key={status}
                                              className={`bar-segment bar-${status}`}
                                              style={{ height: `${height}%` }}
                                              title={`${status}: ${value}`}
                                            />
                                          ) : null
                                        })}
                                      </div>
                                      <div className="bar-label">
                                        {(() => {
                                          const [year, month] = (item.month || '').split('-')
                                          const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                                          return month ? `${monthNames[parseInt(month, 10) - 1]} ${year?.slice(2)}` : item.month
                                        })()}
                                      </div>
                                      <div className="bar-total">{item.total}</div>
                                    </div>
                                  ))
                                })()}
                              </div>
                            )}
                          </div>
    
                          {/* Chart Legend */}
                          {statsChartType !== 'cumulative' && (
                            <div className="chart-legend">
                              <div className="legend-item"><span className="legend-color legend-confirmed"></span> Confirmed</div>
                              <div className="legend-item"><span className="legend-color legend-completed"></span> Completed</div>
                              <div className="legend-item"><span className="legend-color legend-pending"></span> Pending</div>
                              <div className="legend-item"><span className="legend-color legend-cancelled"></span> Cancelled</div>
                            </div>
                          )}
                        </div>
    
                        {/* Data Table */}
                        <div className="stats-table-section">
                          <h3>
                            {statsChartType === 'monthly' && 'Monthly Breakdown'}
                            {statsChartType === 'weekly' && 'Weekly Breakdown'}
                            {statsChartType === 'daily' && 'Daily Breakdown'}
                            {statsChartType === 'cumulative' && 'Cumulative Totals'}
                          </h3>
    
                          {statsChartType === 'daily' ? (
                            /* Daily breakdown with collapsible monthly containers */
                            <div className="daily-table-containers">
                              {(() => {
                                const data = bookingStats.daily
                                const monthlyGroups = {}
                                data.forEach(item => {
                                  const monthKey = item.date?.slice(0, 7)
                                  if (monthKey) {
                                    if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
                                    monthlyGroups[monthKey].push(item)
                                  }
                                })
                                const sortedMonths = Object.keys(monthlyGroups).sort().reverse()
                                const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    
                                return sortedMonths.map(monthKey => {
                                  const [year, month] = monthKey.split('-')
                                  const monthName = `${monthNames[parseInt(month, 10) - 1]} ${year}`
                                  const monthData = monthlyGroups[monthKey]
                                  const monthTotal = monthData.reduce((sum, d) => sum + d.total, 0)
                                  const isExpanded = expandedDailyMonths[monthKey]
    
                                  return (
                                    <div key={monthKey} className="daily-table-month">
                                      <div
                                        className="daily-table-month-header"
                                        onClick={() => setExpandedDailyMonths(prev => ({
                                          ...prev,
                                          [monthKey]: !prev[monthKey]
                                        }))}
                                      >
                                        <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                                        <span className="month-name">{monthName}</span>
                                        <span className="month-total">{monthTotal} bookings</span>
                                      </div>
                                      {isExpanded && (
                                        <div className="stats-table-wrapper">
                                          <table className="stats-table">
                                            <thead>
                                              <tr>
                                                <th>Date</th>
                                                <th className="status-col confirmed">Confirmed</th>
                                                <th className="status-col completed">Completed</th>
                                                <th className="status-col pending">Pending</th>
                                                <th className="status-col cancelled">Cancelled</th>
                                                <th>Total</th>
                                              </tr>
                                            </thead>
                                            <tbody>
                                              {monthData.slice().reverse().map((item, idx) => (
                                                <tr key={idx}>
                                                  <td>{(() => {
                                                    const [, , day] = (item.date || '').split('-')
                                                    return day ? `${day}/${month}` : item.date
                                                  })()}</td>
                                                  <td className="status-col confirmed">{item.confirmed || 0}</td>
                                                  <td className="status-col completed">{item.completed || 0}</td>
                                                  <td className="status-col pending">{item.pending || 0}</td>
                                                  <td className="status-col cancelled">{item.cancelled || 0}</td>
                                                  <td><strong>{item.total}</strong></td>
                                                </tr>
                                              ))}
                                            </tbody>
                                          </table>
                                        </div>
                                      )}
                                    </div>
                                  )
                                })
                              })()}
                            </div>
                          ) : (
                            /* Regular table for monthly, weekly, cumulative */
                            <div className="stats-table-wrapper">
                              <table className="stats-table">
                                <thead>
                                  <tr>
                                    <th>{statsChartType === 'monthly' ? 'Month' : statsChartType === 'weekly' ? 'Week' : 'Date'}</th>
                                    {statsChartType !== 'cumulative' && (
                                      <>
                                        <th className="status-col confirmed">Confirmed</th>
                                        <th className="status-col completed">Completed</th>
                                        <th className="status-col pending">Pending</th>
                                        <th className="status-col cancelled">Cancelled</th>
                                      </>
                                    )}
                                    <th>Total</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {(() => {
                                    const data = statsChartType === 'cumulative' ? bookingStats.cumulative :
                                                 statsChartType === 'monthly' ? bookingStats.monthly :
                                                 bookingStats.weekly
                                    return data.slice(-20).reverse().map((item, idx) => (
                                      <tr key={idx}>
                                        <td>{(() => {
                                          if (statsChartType === 'cumulative' && item.date) {
                                            const [year, month, day] = item.date.split('-')
                                            return `${day}/${month}/${year}`
                                          }
                                          if (item.month) {
                                            const [year, month] = item.month.split('-')
                                            return `${month}/${year}`
                                          }
                                          if (item.week) {
                                            const match = item.week.match(/(\d{4})-W(\d{2})/)
                                            if (!match) return item.week
                                            const [, year, week] = match
                                            const startDate = new Date(year, 0, 1 + (parseInt(week, 10) - 1) * 7)
                                            const dayOfWeek = startDate.getDay()
                                            const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
                                            startDate.setDate(startDate.getDate() + diff)
                                            const endDate = new Date(startDate)
                                            endDate.setDate(startDate.getDate() + 6)
                                            return `${startDate.getDate()}/${startDate.getMonth() + 1} to ${endDate.getDate()}/${endDate.getMonth() + 1}`
                                          }
                                          return ''
                                        })()}</td>
                                        {statsChartType !== 'cumulative' && (
                                          <>
                                            <td className="status-col confirmed">{item.confirmed || 0}</td>
                                            <td className="status-col completed">{item.completed || 0}</td>
                                            <td className="status-col pending">{item.pending || 0}</td>
                                            <td className="status-col cancelled">{item.cancelled || 0}</td>
                                          </>
                                        )}
                                        <td><strong>{item.total}</strong></td>
                                      </tr>
                                    ))
                                  })()}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      </>
                    ) : (
                      <p>No booking data available.</p>
                    )}
                  </div>
                )}
    
                {/* Occupancy Report */}
                {reportsSubTab === 'occupancy' && (
                  <div className="occupancy-report-section">
                    <h3>Parking Occupancy</h3>
                    <p className="reports-description">
                      View online-cap utilization from confirmed and completed bookings. Total capacity and manual reserve are managed below.
                    </p>
    
                    {/* View Type Selector */}
                    <div className="chart-controls">
                      <label>View:</label>
                      <select value={occupancyView} onChange={e => setOccupancyView(e.target.value)}>
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                        <option value="monthly">Monthly</option>
                      </select>
                      <button
                        className="refresh-stats-btn"
                        onClick={() => fetchOccupancyReport(occupancyView, true)}
                        disabled={loadingOccupancy}
                      >
                        {loadingOccupancy ? 'Refreshing...' : 'Refresh Data'}
                      </button>
                    </div>
    
                    <div className="capacity-settings-panel">
                      <div className="capacity-settings-header">
                        <div>
                          <h4>Capacity Schedule</h4>
                          <p>Total spaces minus online spaces becomes the manual reserve. Each row applies to that UK operational day.</p>
                        </div>
                        {loadingCapacitySettings && <span className="capacity-settings-status">Loading...</span>}
                      </div>
    
                      <form className="capacity-settings-form" onSubmit={saveCapacitySettings}>
                        <label>
                          <span>Effective From (UK)</span>
                          <input
                            type="text"
                            inputMode="numeric"
                            placeholder="11/06/2026 14:30"
                            value={capacityForm.effective_from}
                            onChange={e => setCapacityForm({ ...capacityForm, effective_from: e.target.value })}
                          />
                        </label>
                        <label>
                          <span>Total Spaces</span>
                          <input
                            type="number"
                            min="1"
                            value={capacityForm.total_spaces}
                            onChange={e => setCapacityForm({ ...capacityForm, total_spaces: e.target.value })}
                          />
                        </label>
                        <label>
                          <span>Online Spaces</span>
                          <input
                            type="number"
                            min="1"
                            value={capacityForm.online_spaces}
                            onChange={e => setCapacityForm({ ...capacityForm, online_spaces: e.target.value })}
                          />
                        </label>
                        <div className="capacity-reserve-preview">
                          <span>Manual Reserve</span>
                          <strong>
                            {Math.max(
                              0,
                              (parseInt(capacityForm.total_spaces, 10) || 0) -
                              (parseInt(capacityForm.online_spaces, 10) || 0)
                            )}
                          </strong>
                        </div>
                        <button
                          type="submit"
                          className="save-capacity-btn"
                          disabled={savingCapacitySettings}
                        >
                          {savingCapacitySettings ? 'Saving...' : 'Save Capacity'}
                        </button>
                      </form>
    
                      {capacityMessage && (
                        <div className={`capacity-settings-message ${capacityMessage.includes('saved') ? 'success' : 'error'}`}>
                          {capacityMessage}
                        </div>
                      )}
    
                      {capacitySettings?.settings?.length > 0 && (
                        <div className="capacity-schedule-list">
                          {capacitySettings.settings.map(setting => (
                            <div key={setting.effective_from} className="capacity-schedule-row">
                              <span>{setting.effective_from_display || setting.effective_from}</span>
                              <strong>{setting.total_spaces} total</strong>
                              <strong>{setting.online_spaces} online</strong>
                              <strong>{setting.manual_spaces} manual</strong>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
    
                    {loadingOccupancy ? (
                      <div className="admin-loading-inline">
                        <div className="spinner-small"></div>
                        <span>Loading occupancy data...</span>
                      </div>
                    ) : occupancyData ? (
                      <>
                        {/* Summary Stats */}
                        <div className="occupancy-summary">
                          <div className="occupancy-stat">
                            <span className="occupancy-stat-value">{occupancyData.max_capacity}</span>
                            <span className="occupancy-stat-label">Online Spaces</span>
                          </div>
                          {occupancyData.data && occupancyData.data.length > 0 && (() => {
                            const todayEntry = occupancyData.data.find(d => d.is_today);
                            const currentEntry = occupancyData.data.find(d => d.is_current_week || d.is_current_month);
                            const displayEntry = todayEntry || currentEntry;
                            if (displayEntry) {
                              return (
                                <>
                                  <div className="occupancy-stat">
                                    <span className="occupancy-stat-value">{displayEntry.occupied || displayEntry.avg_occupied}</span>
                                    <span className="occupancy-stat-label">{todayEntry ? 'Occupied Today' : 'Current Avg Occupied'}</span>
                                  </div>
                                  <div className="occupancy-stat">
                                    <span className="occupancy-stat-value">{displayEntry.available || displayEntry.avg_available}</span>
                                    <span className="occupancy-stat-label">{todayEntry ? 'Available Today' : 'Current Avg Available'}</span>
                                  </div>
                                  <div className="occupancy-stat">
                                    <span className="occupancy-stat-value">{displayEntry.occupancy_percent || displayEntry.avg_occupancy_percent}%</span>
                                    <span className="occupancy-stat-label">{todayEntry ? 'Utilization Today' : 'Current Utilization'}</span>
                                  </div>
                                </>
                              );
                            }
                            return null;
                          })()}
                        </div>
    
                        {/* Occupancy Chart - Visual Bar Chart */}
                        <div className="occupancy-chart-container">
                          <div className="occupancy-chart-header">
                            <h4>
                              {occupancyView === 'daily' && 'Daily Occupancy'}
                              {occupancyView === 'weekly' && 'Weekly Average Occupancy'}
                              {occupancyView === 'monthly' && 'Monthly Average Occupancy'}
                            </h4>
                            <div className="occupancy-chart-controls">
                              <div className="occupancy-nav-buttons">
                                <button
                                  className="occupancy-nav-btn"
                                  onClick={() => setOccupancyChartOffset(prev => prev - 14)}
                                  title="Previous 2 weeks"
                                >
                                  ← Past
                                </button>
                                <button
                                  className="occupancy-nav-btn today-btn"
                                  onClick={() => setOccupancyChartOffset(0)}
                                  disabled={occupancyChartOffset === 0}
                                  title="Center on today"
                                >
                                  Today
                                </button>
                                <button
                                  className="occupancy-nav-btn"
                                  onClick={() => setOccupancyChartOffset(prev => prev + 14)}
                                  title="Next 2 weeks"
                                >
                                  Future →
                                </button>
                              </div>
                                <span className="occupancy-capacity-badge">
                                  Online cap: {occupancyData.max_capacity} spaces
                                </span>
                            </div>
                          </div>
                            <div className="occupancy-chart-wrapper">
                              <div className="occupancy-y-axis">
                                <span className="y-axis-label" style={{ bottom: '100%' }}>{occupancyChartMaxPercent}%</span>
                                <span className="y-axis-label" style={{ bottom: `${(100 / occupancyChartMaxPercent) * 87.5 + 12.5}%` }}>100%</span>
                                <span className="y-axis-label" style={{ bottom: `${(75 / occupancyChartMaxPercent) * 87.5 + 12.5}%` }}>75%</span>
                                <span className="y-axis-label" style={{ bottom: `${(50 / occupancyChartMaxPercent) * 87.5 + 12.5}%` }}>50%</span>
                                <span className="y-axis-label" style={{ bottom: `${(25 / occupancyChartMaxPercent) * 87.5 + 12.5}%` }}>25%</span>
                                <span className="y-axis-label" style={{ bottom: '12.5%' }}>0%</span>
                              </div>
                              <div className="occupancy-chart-area">
                                <div className="occupancy-gridlines">
                                  <div className="gridline" style={{ bottom: '100%' }}></div>
                                  <div className="gridline gridline-cap" style={{ bottom: `${(100 / occupancyChartMaxPercent) * 100}%` }}></div>
                                  <div className="gridline" style={{ bottom: `${(75 / occupancyChartMaxPercent) * 100}%` }}></div>
                                  <div className="gridline" style={{ bottom: `${(50 / occupancyChartMaxPercent) * 100}%` }}></div>
                                  <div className="gridline" style={{ bottom: `${(25 / occupancyChartMaxPercent) * 100}%` }}></div>
                                <div className="gridline" style={{ bottom: '0%' }}></div>
                              </div>
                              <div className="occupancy-chart">
                                {occupancyData.data && (() => {
                                  // Filter out dates before January 2026
                                  const filteredData = occupancyData.data.filter(item => {
                                    if (item.display_date) {
                                      const parts = item.display_date.split('/');
                                      if (parts.length >= 3) {
                                        const year = parseInt('20' + parts[2], 10);
                                        const month = parseInt(parts[1], 10);
                                        return year > 2026 || (year === 2026 && month >= 1);
                                      }
                                    }
                                    return true;
                                  });
    
                                  // Find today's index
                                  const todayIndex = filteredData.findIndex(item => item.is_today);
                                  const daysToShow = 21; // Show 3 weeks at a time
    
                                  // Calculate start index: center on today + offset
                                  let startIndex;
                                  if (todayIndex >= 0) {
                                    // Center today in the view, then apply offset
                                    startIndex = todayIndex - Math.floor(daysToShow / 2) + occupancyChartOffset;
                                  } else {
                                    // No today found, start from end
                                    startIndex = filteredData.length - daysToShow + occupancyChartOffset;
                                  }
    
                                  // Clamp to valid range
                                  startIndex = Math.max(0, Math.min(startIndex, filteredData.length - daysToShow));
    
                                  return filteredData.slice(startIndex, startIndex + daysToShow).map((item, index) => {
                                  const percent = item.occupancy_percent || item.avg_occupancy_percent || 0;
                                  const occupied = item.occupied || item.avg_occupied || 0;
                                    const online = item.online_capacity || item.avg_online_capacity || occupancyData.online_capacity || occupancyData.max_capacity;
                                    const available = (item.available ?? item.avg_available ?? (online - occupied));
                                  const isHighlight = item.is_today || item.is_current_week || item.is_current_month;
                                  const isPast = item.is_past;
                                  let barClass = 'occupancy-bar';
                                  if (percent >= 90) barClass += ' high';
                                  else if (percent >= 70) barClass += ' medium';
                                  else barClass += ' low';
                                  if (isHighlight) barClass += ' current';
                                  if (isPast) barClass += ' past';
    
                                  // Get day name for daily view
                                  const getDayName = (dateStr) => {
                                    if (!dateStr) return '';
                                    const parts = dateStr.split('/');
                                    if (parts.length >= 3) {
                                      const date = new Date(`20${parts[2]}`, parts[1] - 1, parts[0]);
                                      return date.toLocaleDateString('en-US', { weekday: 'short' });
                                    }
                                    return '';
                                  };
    
                                  return (
                                    <div key={index} className="occupancy-bar-wrapper">
                                      <div className="occupancy-tooltip">
                                        <div className="tooltip-date">
                                          {item.display_date || item.display_week || item.display_month}
                                        </div>
                                        <div className="tooltip-stats">
                                          <span className="tooltip-occupied">{occupied} cars parked</span>
                                          <span className="tooltip-available">{available} spaces free</span>
                                          <span className="tooltip-percent">{Math.round(percent)}% full</span>
                                        </div>
                                      </div>
                                        <div className={barClass} style={{ height: `${Math.max((percent / occupancyChartMaxPercent) * 100, 3)}%` }}>
                                        <div className="occupancy-bar-content">
                                          <span className="occupancy-bar-percent">{Math.round(percent)}%</span>
                                          <span className="occupancy-bar-cars">{occupied}</span>
                                        </div>
                                      </div>
                                      <div className="occupancy-bar-labels">
                                        {occupancyView === 'daily' && (
                                          <>
                                            <span className="bar-label-day">{getDayName(item.display_date)}</span>
                                            <span className="bar-label-date">{item.display_date?.slice(0, 5)}</span>
                                          </>
                                        )}
                                        {occupancyView === 'weekly' && (
                                          <span className="bar-label-date">{item.display_week?.split(' - ')[0]}</span>
                                        )}
                                        {occupancyView === 'monthly' && (
                                          <span className="bar-label-date">{item.display_month?.slice(0, 3)}</span>
                                        )}
                                      </div>
                                    </div>
                                  );
                                });
                                })()}
                              </div>
                            </div>
                          </div>
                          <div className="occupancy-legend">
                            <span className="legend-item"><span className="legend-color low"></span> Low (&lt;70%)</span>
                            <span className="legend-item"><span className="legend-color medium"></span> Medium (70-89%)</span>
                            <span className="legend-item"><span className="legend-color high"></span> High (90%+)</span>
                            <span className="legend-item"><span className="legend-color current"></span> Today</span>
                          </div>
                        </div>
    
                        {/* Occupancy Table */}
                        <div className="occupancy-table-container">
                          <h4>Detailed Breakdown</h4>
    
                          {/* Daily view: Group by month with collapsible sections */}
                          {occupancyView === 'daily' && occupancyData.data && (() => {
                            // Filter out dates before January 2026
                            const filteredData = occupancyData.data.filter(item => {
                              if (item.display_date) {
                                const parts = item.display_date.split('/');
                                if (parts.length >= 3) {
                                  const year = parseInt('20' + parts[2], 10);
                                  const month = parseInt(parts[1], 10);
                                  return year > 2026 || (year === 2026 && month >= 1);
                                }
                              }
                              return true;
                            });
    
                            // Group data by month
                            const groupedByMonth = {};
                            filteredData.forEach(item => {
                              const monthKey = item.display_date?.slice(3) || 'Unknown'; // Get MM/YYYY part
                              if (!groupedByMonth[monthKey]) {
                                groupedByMonth[monthKey] = [];
                              }
                              groupedByMonth[monthKey].push(item);
                            });
    
                            return Object.entries(groupedByMonth).map(([monthKey, items]) => {
                              const hasCurrentDay = items.some(item => item.is_today);
                              const monthLabel = (() => {
                                const parts = monthKey.split('/');
                                if (parts.length === 2) {
                                  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
                                  const monthIndex = parseInt(parts[0], 10) - 1;
                                  return `${monthNames[monthIndex]} ${parts[1]}`;
                                }
                                return monthKey;
                              })();
                              const avgOccupancy = items.reduce((sum, item) => sum + (item.occupancy_percent || 0), 0) / items.length;
    
                              return (
                                <details key={monthKey} className="occupancy-month-group" open={hasCurrentDay}>
                                  <summary className="occupancy-month-header">
                                    <span className="month-title">{monthLabel}</span>
                                    <span className="month-stats">
                                      <span className="month-days">{items.length} days</span>
                                      <span className={`month-avg ${avgOccupancy >= 90 ? 'high' : avgOccupancy >= 70 ? 'medium' : 'low'}`}>
                                        Avg: {avgOccupancy.toFixed(1)}%
                                      </span>
                                    </span>
                                  </summary>
                                  <div className="occupancy-table-wrapper">
                                    <table className="occupancy-table">
                                      <thead>
                                        <tr>
                                          <th>Date</th>
                                          <th>Occupied</th>
                                          <th>Available</th>
                                          <th>Utilization</th>
                                          <th>Status</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {items.map((item, index) => {
                                          const occupied = item.occupied ?? item.avg_occupied;
                                          const available = item.available ?? item.avg_available;
                                          const percent = item.occupancy_percent ?? item.avg_occupancy_percent;
                                          const isHighlight = item.is_today;
                                          const isPast = item.is_past;
    
                                          return (
                                            <tr key={index} className={`${isHighlight ? 'highlight-row' : ''} ${isPast ? 'past-row' : ''}`}>
                                              <td className="date-cell">{item.display_date}</td>
                                              <td className="number-cell">{typeof occupied === 'number' ? occupied.toFixed(0) : '-'}</td>
                                              <td className="number-cell">{typeof available === 'number' ? available.toFixed(0) : '-'}</td>
                                              <td className="util-cell">
                                                <span className={`occupancy-percent ${percent >= 90 ? 'high' : percent >= 70 ? 'medium' : 'low'}`}>
                                                  {typeof percent === 'number' ? `${percent.toFixed(1)}%` : '-'}
                                                </span>
                                              </td>
                                              <td className="status-cell">
                                                {isHighlight && <span className="status-badge current">Today</span>}
                                                {isPast && !isHighlight && <span className="status-badge past">Past</span>}
                                                {!isPast && !isHighlight && <span className="status-badge future">Future</span>}
                                              </td>
                                            </tr>
                                          );
                                        })}
                                      </tbody>
                                    </table>
                                  </div>
                                </details>
                              );
                            });
                          })()}
    
                          {/* Weekly/Monthly view: Standard table */}
                          {occupancyView !== 'daily' && (
                            <div className="occupancy-table-wrapper">
                              <table className="occupancy-table">
                                <thead>
                                  <tr>
                                    <th>{occupancyView === 'weekly' ? 'Week' : 'Month'}</th>
                                    <th>Avg Occupied</th>
                                    <th>Avg Available</th>
                                    <th>Utilization</th>
                                    <th>Status</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {occupancyData.data && occupancyData.data.map((item, index) => {
                                    const occupied = item.avg_occupied;
                                    const available = item.avg_available;
                                    const percent = item.avg_occupancy_percent;
                                    const isHighlight = item.is_current_week || item.is_current_month;
                                    const isPast = item.is_past;
    
                                    return (
                                      <tr key={index} className={`${isHighlight ? 'highlight-row' : ''} ${isPast ? 'past-row' : ''}`}>
                                        <td className="date-cell">{item.display_week || item.display_month}</td>
                                        <td className="number-cell">{typeof occupied === 'number' ? occupied.toFixed(1) : '-'}</td>
                                        <td className="number-cell">{typeof available === 'number' ? available.toFixed(1) : '-'}</td>
                                        <td className="util-cell">
                                          <span className={`occupancy-percent ${percent >= 90 ? 'high' : percent >= 70 ? 'medium' : 'low'}`}>
                                            {typeof percent === 'number' ? `${percent.toFixed(1)}%` : '-'}
                                          </span>
                                        </td>
                                        <td className="status-cell">
                                          {isHighlight && <span className="status-badge current">Current</span>}
                                          {isPast && !isHighlight && <span className="status-badge past">Past</span>}
                                          {!isPast && !isHighlight && <span className="status-badge future">Future</span>}
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          )}
    
                          {/* Secondary Car Park (P2) — future eligible events */}
                          <div className="capacity-settings-panel secondary-carpark-panel">
                            <div className="capacity-settings-header">
                              <div>
                                <h4>Secondary Car Park (P2)</h4>
                                <p>
                                  Future drop-offs and pickups (from today) for bookings within{' '}
                                  {secondaryReport ? `${secondaryReport.window_start}–${secondaryReport.window_end}` : 'the operating window'}
                                  {secondaryReport ? ` — ${secondaryReport.count} eligible bookings, capacity ${secondaryReport.capacity}` : ''}
                                </p>
                              </div>
                              <div className="chart-controls" style={{ margin: 0 }}>
                                <select value={secondaryGroup} onChange={e => setSecondaryGroup(e.target.value)}>
                                  <option value="daily">Daily</option>
                                  <option value="weekly">Weekly</option>
                                  <option value="monthly">Monthly</option>
                                </select>
                              </div>
                            </div>
                            {loadingSecondaryReport ? (
                              <div className="admin-loading-inline"><div className="spinner-small"></div><span>Loading...</span></div>
                            ) : !secondaryReport || (secondaryReport.events || []).length === 0 ? (
                              <p style={{ opacity: 0.7 }}>No eligible future bookings.</p>
                            ) : (() => {
                              const groupKey = (ev) => {
                                const d = new Date(ev.date + 'T00:00:00')
                                if (secondaryGroup === 'monthly') {
                                  return d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
                                }
                                if (secondaryGroup === 'weekly') {
                                  const monday = new Date(d)
                                  monday.setDate(d.getDate() - ((d.getDay() + 6) % 7))
                                  const sunday = new Date(monday)
                                  sunday.setDate(monday.getDate() + 6)
                                  const fmt = (x) => x.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' })
                                  return `Week ${fmt(monday)} – ${fmt(sunday)}`
                                }
                                return d.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' })
                              }
                              const groups = {}
                              secondaryReport.events.forEach(ev => {
                                const key = groupKey(ev)
                                if (!groups[key]) groups[key] = []
                                groups[key].push(ev)
                              })
                              return Object.entries(groups).map(([label, rows]) => (
                                <details key={label} className="occupancy-month-group">
                                  <summary className="occupancy-month-header">
                                    <span className="month-title">{label}</span>
                                    <span className="month-stats">
                                      <span className="month-days">{rows.length} event{rows.length !== 1 ? 's' : ''}</span>
                                    </span>
                                  </summary>
                                  <div className="occupancy-table-wrapper">
                                    <table className="occupancy-table p2-events-table">
                                      <colgroup>
                                        <col style={{ width: '17%' }} />
                                        <col style={{ width: '24%' }} />
                                        <col style={{ width: '21%' }} />
                                        <col style={{ width: '15%' }} />
                                        <col style={{ width: '23%' }} />
                                      </colgroup>
                                      <thead>
                                        <tr>
                                          <th>Ref</th>
                                          <th>Name</th>
                                          <th>Car</th>
                                          <th>Reg</th>
                                          <th>Event</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {rows.map((ev, i) => (
                                          <tr key={`${ev.reference}-${ev.event}-${i}`}>
                                            <td className="date-cell" data-label="Ref">{ev.reference}</td>
                                            <td data-label="Name">{ev.customer_name || '-'}</td>
                                            <td data-label="Car">{ev.car || '-'}</td>
                                            <td className="p2-reg-cell" data-label="Reg">{ev.registration || '-'}</td>
                                            <td data-label="Event">
                                              {ev.event === 'dropoff' ? 'Drop-off' : 'Pickup'}
                                              {secondaryGroup === 'daily' ? '' : ` ${ev.display_date}`}
                                              {ev.time ? ` @ ${ev.time}` : ''}
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                </details>
                              ))
                            })()}
                          </div>
                        </div>
                      </>
                    ) : (
                      <p>No occupancy data available.</p>
                    )}
                  </div>
                )}
    
                {/* Popular Airlines & Destinations */}
                {reportsSubTab === 'popular' && (
                  <div className="popular-report-section">
                    <h3>Popular Airlines & Destinations</h3>
                    <p className="reports-description">
                      View the most popular airlines and destinations based on confirmed and completed bookings.
                    </p>
    
                    {/* Controls */}
                    <div className="chart-controls">
                      <label>Show:</label>
                      <select value={popularTop} onChange={e => setPopularTop(Number(e.target.value))}>
                        <option value={5}>Top 5</option>
                        <option value={10}>Top 10</option>
                        <option value={20}>Top 20</option>
                      </select>
                    </div>
    
                    {loadingPopular ? (
                      <div className="admin-loading-inline">
                        <div className="spinner-small"></div>
                        <span>Loading popular routes...</span>
                      </div>
                    ) : popularData ? (
                      <>
                      <div className="popular-charts-grid">
                        {/* Popular Airlines */}
                        <div className="popular-chart-container">
                          <h4>Top Airlines</h4>
                          <p className="chart-subtitle">Based on {popularData.meta.totalBookings} bookings</p>
                          <div className="popular-bar-chart">
                            {popularData.popularAirlines.length > 0 ? (
                              popularData.popularAirlines.map((airline, idx) => {
                                const maxCount = popularData.popularAirlines[0]?.count || 1
                                const barWidth = (airline.count / maxCount) * 100
                                return (
                                  <div key={idx} className="popular-bar-row">
                                    <div className="popular-bar-label">
                                      <span className="popular-rank">{idx + 1}</span>
                                      <span className="popular-name">{airline.airlineName}</span>
                                    </div>
                                    <div className="popular-bar-container">
                                      <div
                                        className="popular-bar popular-bar-airline"
                                        style={{ width: `${barWidth}%` }}
                                      />
                                      <span className="popular-bar-value">{airline.count} ({airline.percent}%)</span>
                                    </div>
                                  </div>
                                )
                              })
                            ) : (
                              <p className="no-data">No airline data available</p>
                            )}
                          </div>
                        </div>
    
                        {/* Popular Destinations */}
                        <div className="popular-chart-container">
                          <h4>Top Destinations</h4>
                          <p className="chart-subtitle">Based on {popularData.meta.totalBookings} bookings</p>
                          <div className="popular-bar-chart">
                            {popularData.popularDestinations.length > 0 ? (
                              popularData.popularDestinations.map((dest, idx) => {
                                const maxCount = popularData.popularDestinations[0]?.count || 1
                                const barWidth = (dest.count / maxCount) * 100
                                return (
                                  <div key={idx} className="popular-bar-row">
                                    <div className="popular-bar-label">
                                      <span className="popular-rank">{idx + 1}</span>
                                      <span className="popular-name">{dest.destination}</span>
                                    </div>
                                    <div className="popular-bar-container">
                                      <div
                                        className="popular-bar popular-bar-destination"
                                        style={{ width: `${barWidth}%` }}
                                      />
                                      <span className="popular-bar-value">{dest.count} ({dest.percent}%)</span>
                                    </div>
                                  </div>
                                )
                              })
                            ) : (
                              <p className="no-data">No destination data available</p>
                            )}
                          </div>
                        </div>
                      </div>
    
                      {/* Popular Routes - Full Width */}
                      <div className="popular-chart-container popular-chart-full-width">
                        <h4>Top Routes (Airline + Destination)</h4>
                        <p className="chart-subtitle">Based on {popularData.meta.totalBookings} bookings</p>
                        <div className="popular-bar-chart">
                          {popularData.popularRoutes && popularData.popularRoutes.length > 0 ? (
                            popularData.popularRoutes.map((route, idx) => {
                              const maxCount = popularData.popularRoutes[0]?.count || 1
                              const barWidth = (route.count / maxCount) * 100
                              return (
                                <div key={idx} className="popular-bar-row">
                                  <div className="popular-bar-label popular-bar-label-wide">
                                    <span className="popular-rank">{idx + 1}</span>
                                    <span className="popular-name">{route.route}</span>
                                  </div>
                                  <div className="popular-bar-container">
                                    <div
                                      className="popular-bar popular-bar-route"
                                      style={{ width: `${barWidth}%` }}
                                    />
                                    <span className="popular-bar-value">{route.count} ({route.percent}%)</span>
                                  </div>
                                </div>
                              )
                            })
                          ) : (
                            <p className="no-data">No route data available</p>
                          )}
                        </div>
                      </div>
                      </>
                    ) : (
                      <p>No data available. Try refreshing the page.</p>
                    )}
                  </div>
                )}
    
                {/* Location Maps */}
                {reportsSubTab === 'map' && (
                  <>
                    <div className="reports-section-header">
                      <button
                        className="refresh-page-btn"
                        onClick={() => fetchBookingLocations(mapType, true)}
                        disabled={loadingLocations}
                      >
                        {loadingLocations ? 'Refreshing...' : 'Refresh Page'}
                      </button>
                    </div>
    
                    <div className="map-type-tabs">
                      <button
                        className={`map-type-tab ${mapType === 'bookings' ? 'active' : ''}`}
                        onClick={() => setMapType('bookings')}
                      >
                        Bookings Map
                      </button>
                      <button
                        className={`map-type-tab ${mapType === 'origins' ? 'active' : ''}`}
                        onClick={() => setMapType('origins')}
                      >
                        Journey Origins
                      </button>
                    </div>
    
                    {mapType === 'bookings' && (
                      <>
                        <h3>Confirmed Booking Locations</h3>
                        <p className="reports-description">Map showing confirmed bookings based on billing postcodes.</p>
                      </>
                    )}
    
                    {mapType === 'origins' && (
                      <>
                        <h3>Journey Origins (All Leads)</h3>
                        <p className="reports-description">Map showing all customers who started the booking process (Page 1 data).</p>
                      </>
                    )}
    
                    {loadingLocations ? (
                      <div className="admin-loading-inline">
                        <div className="spinner-small"></div>
                        <span>Loading {mapType === 'origins' ? 'customer' : 'booking'} locations...</span>
                      </div>
                    ) : (
                      <>
                        <BookingLocationMap
                          locations={mapType === 'origins' ? originLocations : bookingLocations}
                          mapType={mapType}
                        />
                        {skippedBookings.length > 0 && (
                          <div className="skipped-bookings">
                            <p className="skipped-summary">
                              {mapType === 'origins'
                                ? `${originLocations.length} of ${totalCustomers} customers mapped.`
                                : `${bookingLocations.length} of ${totalBookings} bookings mapped.`
                              }
                              {' '}{skippedBookings.length} skipped:
                            </p>
                            <ul className="skipped-list">
                              {skippedBookings.map((s, i) => (
                                <li key={i}>{s.reference || `Customer ${s.customer_id}`}: {s.reason}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </>
                    )}
                  </>
                )}
    
                {/* Financial Report */}
                {reportsSubTab === 'financial' && (
                  <>
                    <div className="reports-section-header">
                      <button
                        className="refresh-page-btn"
                        onClick={() => fetchFinancialReport(true)}
                        disabled={loadingFinancial}
                      >
                        {loadingFinancial ? 'Refreshing...' : 'Refresh Page'}
                      </button>
                    </div>
    
                    {/* Filters */}
                    <div className="financial-filters">
                      <div className="filter-group">
                        <label>From Date</label>
                        <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                          <input
                            type="text"
                            placeholder="DD/MM/YYYY"
                            value={financialFromDate}
                            onChange={(e) => setFinancialFromDate(formatDateInput(e.target.value))}
                            maxLength={10}
                          />
                          <DatePicker
                            selected={parseUkDate(financialFromDate)}
                            onChange={(date) => setFinancialFromDate(dateToUkString(date))}
                            dateFormat="dd/MM/yyyy"
                            customInput={<button type="button" className="date-picker-btn">📅</button>}
                          />
                        </div>
                      </div>
                      <div className="filter-group">
                        <label>To Date</label>
                        <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                          <input
                            type="text"
                            placeholder="DD/MM/YYYY"
                            value={financialToDate}
                            onChange={(e) => setFinancialToDate(formatDateInput(e.target.value))}
                            maxLength={10}
                          />
                          <DatePicker
                            selected={parseUkDate(financialToDate)}
                            onChange={(date) => setFinancialToDate(dateToUkString(date))}
                            dateFormat="dd/MM/yyyy"
                            customInput={<button type="button" className="date-picker-btn">📅</button>}
                          />
                        </div>
                      </div>
                      <div className="filter-group">
                        <label>Status</label>
                        <select
                          value={financialStatusFilter}
                          onChange={(e) => setFinancialStatusFilter(e.target.value)}
                        >
                          <option value="all">All</option>
                          <option value="confirmed">Confirmed</option>
                          <option value="completed">Completed</option>
                          <option value="refunded">Refunded</option>
                        </select>
                      </div>
                      <div className="filter-group">
                        <label>Promo Code</label>
                        <select
                          value={financialPromoFilter}
                          onChange={(e) => setFinancialPromoFilter(e.target.value)}
                        >
                          <option value="all">All</option>
                          <option value="yes">With Promo</option>
                          <option value="no">Without Promo</option>
                        </select>
                      </div>
                      <button
                        className="filter-apply-btn"
                        onClick={fetchFinancialReport}
                        disabled={loadingFinancial}
                      >
                        Apply Filters
                      </button>
                      <button
                        className="export-csv-btn"
                        onClick={exportFinancialCSV}
                        disabled={exportingFinancial}
                      >
                        {exportingFinancial ? 'Exporting...' : 'Export CSV'}
                      </button>
                    </div>
    
                    {loadingFinancial ? (
                      <div className="admin-loading-inline">
                        <div className="spinner-small"></div>
                        <span>Loading financial report...</span>
                      </div>
                    ) : financialData ? (
                      <>
                        {/* Revenue Fun Facts */}
                        <div className="financial-fun-facts">
                          <h3>Revenue Highlights</h3>
                          <div className="stats-summary-cards">
                            {financialData.funFacts?.revenueToday && (
                              <div className="stats-card fun-fact-card fun-fact-vertical">
                                <div className="stats-card-label">Revenue Today</div>
                                <div className="stats-card-value">{financialData.funFacts.revenueToday.amount}</div>
                                {financialData.funFacts.revenueToday.vsYesterday && (
                                  <div className="fun-fact-change" style={{ color: financialData.funFacts.revenueToday.vsYesterday.startsWith('+') ? '#22c55e' : '#ef4444' }}>
                                    {financialData.funFacts.revenueToday.vsYesterday} vs yesterday
                                  </div>
                                )}
                              </div>
                            )}
                            {financialData.funFacts?.revenueThisWeek && (
                              <div className="stats-card fun-fact-card fun-fact-vertical">
                                <div className="stats-card-label">Revenue This Week</div>
                                <div className="stats-card-value">{financialData.funFacts.revenueThisWeek.amount}</div>
                                {financialData.funFacts.revenueThisWeek.vsLastWeek && (
                                  <div className="fun-fact-change" style={{ color: financialData.funFacts.revenueThisWeek.vsLastWeek.startsWith('+') ? '#22c55e' : '#ef4444' }}>
                                    {financialData.funFacts.revenueThisWeek.vsLastWeek} vs last week
                                  </div>
                                )}
                              </div>
                            )}
                            {financialData.funFacts?.revenueThisMonth && (
                              <div className="stats-card fun-fact-card fun-fact-vertical">
                                <div className="stats-card-label">Revenue This Month</div>
                                <div className="stats-card-value">{financialData.funFacts.revenueThisMonth.amount}</div>
                                {financialData.funFacts.revenueThisMonth.vsLastMonth && (
                                  <div className="fun-fact-change" style={{ color: financialData.funFacts.revenueThisMonth.vsLastMonth.startsWith('+') ? '#22c55e' : '#ef4444' }}>
                                    {financialData.funFacts.revenueThisMonth.vsLastMonth} vs last month
                                  </div>
                                )}
                              </div>
                            )}
                            {financialData.funFacts?.topRevenueDay && (
                              <div className="stats-card fun-fact-card fun-fact-vertical">
                                <div className="stats-card-label">Top Revenue Day</div>
                                <div className="stats-card-value">{financialData.funFacts.topRevenueDay.amount}</div>
                                <div className="fun-fact-detail">{financialData.funFacts.topRevenueDay.date}</div>
                              </div>
                            )}
                            {financialData.funFacts?.topRevenueWeek && (
                              <div className="stats-card fun-fact-card fun-fact-vertical">
                                <div className="stats-card-label">Top Revenue Week</div>
                                <div className="stats-card-value">{financialData.funFacts.topRevenueWeek.amount}</div>
                                <div className="fun-fact-detail">{financialData.funFacts.topRevenueWeek.week}</div>
                              </div>
                            )}
                            {financialData.funFacts?.topRevenueMonth && (
                              <div className="stats-card fun-fact-card fun-fact-vertical">
                                <div className="stats-card-label">Top Revenue Month</div>
                                <div className="stats-card-value">{financialData.funFacts.topRevenueMonth.amount}</div>
                                <div className="fun-fact-detail">{financialData.funFacts.topRevenueMonth.month}</div>
                              </div>
                            )}
                          </div>
                        </div>
    
                        {/* Revenue Milestones */}
                        {financialData.funFacts?.revenueMilestones?.length > 0 && (
                          <div className="revenue-milestones-section">
                            <h3>Revenue Milestones</h3>
                            <div className="revenue-milestones-grid">
                              {financialData.funFacts.revenueMilestones.map((milestone) => (
                                <div
                                  key={milestone.amount}
                                  className={`revenue-milestone-card ${milestone.achieved ? 'achieved' : 'pending'} ${milestone.amount >= 50000 ? 'major' : milestone.amount >= 10000 ? 'significant' : ''}`}
                                >
                                  <div className="milestone-amount">{milestone.label}</div>
                                  {milestone.achieved ? (
                                    <div className="milestone-date">{milestone.date}</div>
                                  ) : (
                                    <div className="milestone-pending">Coming soon...</div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
    
                        {/* Summary Totals */}
                        <div className="financial-summary">
                          <h3>Summary</h3>
                          <div className="stats-summary-cards">
                            <div className="stats-card">
                              <div className="stats-card-value">{financialData.summary?.totalBookings || 0}</div>
                              <div className="stats-card-label">Total Bookings</div>
                            </div>
                            <div className="stats-card">
                              <div className="stats-card-value">{financialData.summary?.totalGross || '£0.00'}</div>
                              <div className="stats-card-label">Original Price (Gross)</div>
                            </div>
                            <div className="stats-card">
                              <div className="stats-card-value" style={{ color: '#f59e0b' }}>{financialData.summary?.totalDiscount || '£0.00'}</div>
                              <div className="stats-card-label">Total Discounts</div>
                            </div>
                            <div className="stats-card">
                              <div className="stats-card-value">{financialData.summary?.totalNet || '£0.00'}</div>
                              <div className="stats-card-label">Amount Paid (Net)</div>
                            </div>
                            <div className="stats-card">
                              <div className="stats-card-value" style={{ color: '#ef4444' }}>{financialData.summary?.totalRefunds || '£0.00'}</div>
                              <div className="stats-card-label">Total Refunds</div>
                            </div>
                            <div className="stats-card">
                              <div className="stats-card-value" style={{ color: '#22c55e' }}>{financialData.summary?.totalRevenue || '£0.00'}</div>
                              <div className="stats-card-label">Final Revenue</div>
                            </div>
                          </div>
                        </div>
    
                        {/* Revenue Chart */}
                        {financialData.chartData && (
                          <div className="booking-chart revenue-chart-section">
                            <div className="chart-controls">
                              <label>View:</label>
                              <select value={revenueChartType} onChange={e => setRevenueChartType(e.target.value)}>
                                <option value="monthly">Monthly</option>
                                <option value="weekly">Weekly</option>
                                <option value="daily">Daily</option>
                                <option value="cumulative">Cumulative Growth</option>
                              </select>
                            </div>
    
                            <h3>
                              {revenueChartType === 'monthly' && 'Revenue by Month'}
                              {revenueChartType === 'weekly' && 'Revenue by Week'}
                              {revenueChartType === 'daily' && 'Revenue by Day'}
                              {revenueChartType === 'cumulative' && 'Cumulative Revenue Growth'}
                            </h3>
    
                            <div className="chart-container">
                              {revenueChartType === 'cumulative' ? (
                                <div className="line-chart">
                                  {financialData.chartData.cumulative?.length > 0 && (
                                    <>
                                      <div className="chart-y-axis">
                                        <span>£{Math.round(Math.max(...financialData.chartData.cumulative.map(d => d.totalPounds)))}</span>
                                        <span>£{Math.round(Math.max(...financialData.chartData.cumulative.map(d => d.totalPounds)) / 2)}</span>
                                        <span>£0</span>
                                      </div>
                                      <div className="chart-area">
                                        <svg viewBox={`0 0 ${Math.min(financialData.chartData.cumulative.length * 30, 1200)} 200`} preserveAspectRatio="none">
                                          <defs>
                                            <linearGradient id="revenueLineGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                              <stop offset="0%" stopColor="#22c55e" stopOpacity="0.3" />
                                              <stop offset="100%" stopColor="#22c55e" stopOpacity="0.05" />
                                            </linearGradient>
                                          </defs>
                                          {(() => {
                                            const data = financialData.chartData.cumulative
                                            const maxVal = Math.max(...data.map(d => d.totalPounds))
                                            const width = Math.min(data.length * 30, 1200)
                                            const points = data.map((d, i) => {
                                              const x = (i / (data.length - 1)) * width
                                              const y = 200 - ((d.totalPounds / maxVal) * 180)
                                              return `${x},${y}`
                                            }).join(' ')
                                            const areaPoints = `0,200 ${points} ${width},200`
                                            return (
                                              <>
                                                <polygon points={areaPoints} fill="url(#revenueLineGradient)" />
                                                <polyline points={points} fill="none" stroke="#22c55e" strokeWidth="2" />
                                              </>
                                            )
                                          })()}
                                        </svg>
                                      </div>
                                    </>
                                  )}
                                </div>
                              ) : revenueChartType === 'weekly' ? (
                                <div className="weekly-chart-container">
                                  {(() => {
                                    const data = financialData.chartData.weekly || []
                                    const weeksPerPage = 8
                                    const totalPages = Math.ceil(data.length / weeksPerPage)
                                    const startIdx = Math.max(0, data.length - weeksPerPage - (revenueWeeklyPageIndex * weeksPerPage))
                                    const endIdx = Math.min(data.length, startIdx + weeksPerPage)
                                    const displayData = data.slice(startIdx, endIdx)
                                    const maxRevenue = Math.max(...displayData.map(d => d.revenuePounds), 1)
                                    const BAR_STACK_PX = 150 // matches inline height below; px-based to avoid the single-child flex-column % quirk that was clipping bars to ~full height
    
                                    return (
                                      <>
                                        {totalPages > 1 && (
                                          <div className="chart-navigation">
                                            <button
                                              className="nav-btn"
                                              onClick={() => setRevenueWeeklyPageIndex(i => Math.min(i + 1, totalPages - 1))}
                                              disabled={revenueWeeklyPageIndex >= totalPages - 1}
                                            >
                                              &larr; Older
                                            </button>
                                            <span className="nav-info">
                                              Showing weeks {startIdx + 1}-{endIdx} of {data.length}
                                            </span>
                                            <button
                                              className="nav-btn"
                                              onClick={() => setRevenueWeeklyPageIndex(i => Math.max(i - 1, 0))}
                                              disabled={revenueWeeklyPageIndex <= 0}
                                            >
                                              Newer &rarr;
                                            </button>
                                          </div>
                                        )}
                                        <div className="stacked-bar-chart">
                                          {displayData.map((item, idx) => (
                                            <div key={idx} className="bar-column">
                                              <div className="bar-stack" style={{ height: `${BAR_STACK_PX}px` }}>
                                                <div
                                                  className="bar-segment bar-confirmed"
                                                  style={{ height: `${(item.revenuePounds / maxRevenue) * BAR_STACK_PX}px` }}
                                                  title={`£${item.revenuePounds.toFixed(2)}`}
                                                />
                                              </div>
                                              <div className="bar-label">{item.weekLabel?.split(' - ')[0] || item.week}</div>
                                              <div className="bar-total">£{item.revenuePounds.toFixed(0)}</div>
                                            </div>
                                          ))}
                                        </div>
                                      </>
                                    )
                                  })()}
                                </div>
                              ) : revenueChartType === 'daily' ? (
                                <div className="daily-chart-container">
                                  {(() => {
                                    const data = financialData.chartData.daily || []
                                    const monthlyGroups = {}
                                    data.forEach(item => {
                                      const monthKey = item.date?.slice(0, 7)
                                      if (monthKey) {
                                        if (!monthlyGroups[monthKey]) monthlyGroups[monthKey] = []
                                        monthlyGroups[monthKey].push(item)
                                      }
                                    })
                                    const months = Object.keys(monthlyGroups).sort().reverse()
    
                                    return months.map(monthKey => {
                                      const monthItems = monthlyGroups[monthKey]
                                      const [year, month] = monthKey.split('-')
                                      const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
                                      const monthLabel = `${monthNames[parseInt(month, 10) - 1]} ${year}`
                                      const isExpanded = expandedRevenueDailyMonths[monthKey] !== false
                                      const monthTotal = monthItems.reduce((sum, d) => sum + d.revenuePounds, 0)
                                      const maxRevenue = Math.max(...monthItems.map(d => d.revenuePounds), 1)
                                      const BAR_STACK_PX = 150
    
                                      return (
                                        <div key={monthKey} className="daily-month-group">
                                          <div
                                            className="daily-month-header"
                                            onClick={() => setExpandedRevenueDailyMonths(prev => ({
                                              ...prev,
                                              [monthKey]: !isExpanded
                                            }))}
                                          >
                                            <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                                            <span className="month-label">{monthLabel}</span>
                                            <span className="month-total">£{monthTotal.toFixed(2)}</span>
                                          </div>
                                          {isExpanded && (
                                            <div className="stacked-bar-chart daily-bar-chart">
                                              {monthItems.map((item, idx) => {
                                                const dayLabel = item.date?.slice(8, 10).replace(/^0/, '') || ''
                                                return (
                                                  <div key={idx} className="bar-column">
                                                    <div className="bar-stack" style={{ height: `${BAR_STACK_PX}px` }}>
                                                      <div
                                                        className="bar-segment bar-confirmed"
                                                        style={{ height: `${(item.revenuePounds / maxRevenue) * BAR_STACK_PX}px` }}
                                                        title={`£${item.revenuePounds.toFixed(2)}`}
                                                      />
                                                    </div>
                                                    <div className="bar-label">{dayLabel}</div>
                                                    <div className="bar-total">£{item.revenuePounds.toFixed(0)}</div>
                                                  </div>
                                                )
                                              })}
                                            </div>
                                          )}
                                        </div>
                                      )
                                    })
                                  })()}
                                </div>
                              ) : (
                                <div className="stacked-bar-chart">
                                  {(() => {
                                    const data = financialData.chartData.monthly || []
                                    const maxRevenue = Math.max(...data.map(d => d.revenuePounds), 1)
                                    const BAR_STACK_PX = 150
                                    return data.map((item, idx) => (
                                      <div key={idx} className="bar-column">
                                        <div className="bar-stack" style={{ height: `${BAR_STACK_PX}px` }}>
                                          <div
                                            className="bar-segment bar-confirmed"
                                            style={{ height: `${(item.revenuePounds / maxRevenue) * BAR_STACK_PX}px` }}
                                            title={`£${item.revenuePounds.toFixed(2)}`}
                                          />
                                        </div>
                                        <div className="bar-label">{item.monthLabel}</div>
                                        <div className="bar-total">£{item.revenuePounds.toFixed(0)}</div>
                                      </div>
                                    ))
                                  })()}
                                </div>
                              )}
                            </div>
                          </div>
                        )}
    
                        {/* Monthly Breakdown */}
                        <div className="financial-monthly-breakdown">
                          <h3>Monthly Breakdown</h3>
                          {financialData.monthlyData?.length === 0 ? (
                            <p className="admin-empty">No financial data found for the selected filters.</p>
                          ) : (
                            financialData.monthlyData?.map((month) => (
                              <div key={month.monthKey} className="financial-month-container">
                                <div
                                  className="financial-month-header"
                                  onClick={() => setExpandedFinancialMonths(prev => ({
                                    ...prev,
                                    [month.monthKey]: !prev[month.monthKey]
                                  }))}
                                >
                                  <span className="expand-icon">{expandedFinancialMonths[month.monthKey] ? '▼' : '▶'}</span>
                                  <span className="month-label">{month.monthLabel}</span>
                                  <span className="month-count">{month.bookingCount} bookings</span>
                                  <span className="month-gross">Gross: {month.totalGross}</span>
                                  <span className="month-discount">Discounts: {month.totalDiscount}</span>
                                  <span className="month-net">Paid: {month.totalNet}</span>
                                  <span className="month-refunds">Refunds: {month.totalRefunds}</span>
                                  <span className="month-revenue">Revenue: {month.totalRevenue}</span>
                                </div>
                                {expandedFinancialMonths[month.monthKey] && (
                                  <div className="financial-month-bookings">
                                    <table className="admin-table financial-table financial-table-compact">
                                      <thead>
                                        <tr>
                                          <th style={{ width: '70px' }}>Date</th>
                                          <th style={{ width: '100px' }}>Ref</th>
                                          <th style={{ width: '120px' }}>Customer</th>
                                          <th style={{ width: '40px' }}>Days</th>
                                          <th style={{ width: '60px' }}>Gross</th>
                                          <th style={{ width: '100px' }}>Promo</th>
                                          <th style={{ width: '70px' }}>Discount</th>
                                          <th style={{ width: '60px' }}>Paid</th>
                                          <th style={{ width: '60px' }}>Refund</th>
                                          <th style={{ width: '60px' }}>Revenue</th>
                                          <th style={{ width: '70px' }}>Status</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {(() => {
                                          // Bookings arrive sorted ASC by paidDateSort, so
                                          // contiguous runs of the same day form the groups.
                                          const dayGroups = []
                                          month.bookings.forEach((booking) => {
                                            const dayKey = booking.paidDateSort || booking.paidDate
                                            const last = dayGroups[dayGroups.length - 1]
                                            if (last && last.dayKey === dayKey) {
                                              last.bookings.push(booking)
                                            } else {
                                              dayGroups.push({ dayKey, label: booking.paidDate, bookings: [booking] })
                                            }
                                          })
                                          return dayGroups.map((day) => {
                                            const dayStateKey = `${month.monthKey}|${day.dayKey}`
                                            const isDayExpanded = !!expandedFinancialDays[dayStateKey]
                                            const dayNetPence = day.bookings.reduce((sum, b) => sum + (b.netPence || 0), 0)
                                            const dayRefundPence = day.bookings.reduce((sum, b) => sum + (b.refundPence || 0), 0)
                                            const dayRevenuePence = day.bookings.reduce((sum, b) => sum + (b.finalRevenuePence || 0), 0)
                                            return (
                                              <React.Fragment key={dayStateKey}>
                                                <tr
                                                  className="financial-day-row"
                                                  onClick={() => setExpandedFinancialDays(prev => ({
                                                    ...prev,
                                                    [dayStateKey]: !prev[dayStateKey]
                                                  }))}
                                                >
                                                  <td colSpan={11}>
                                                    <span className="expand-icon">{isDayExpanded ? '▼' : '▶'}</span>
                                                    <span className="day-label">{day.label}</span>
                                                    <span className="day-count">{day.bookings.length} booking{day.bookings.length !== 1 ? 's' : ''}</span>
                                                    <span className="day-net">Paid: £{(dayNetPence / 100).toFixed(2)}</span>
                                                    {dayRefundPence > 0 && (
                                                      <span className="day-refunds">Refunds: £{(dayRefundPence / 100).toFixed(2)}</span>
                                                    )}
                                                    <span className="day-revenue">Revenue: £{(dayRevenuePence / 100).toFixed(2)}</span>
                                                  </td>
                                                </tr>
                                                {isDayExpanded && day.bookings.map((booking) => (
                                          <tr key={booking.id} className={booking.needsOverride ? 'needs-override' : ''}>
                                            <td>{booking.paidDate}</td>
                                            <td>{booking.reference}</td>
                                            <td>{booking.customerName}</td>
                                            <td>{booking.tripDays || '-'}</td>
                                            {/* Gross column - editable if needs override */}
                                            <td>
                                              {editingFinancialBooking?.id === booking.id ? (
                                                <input
                                                  type="number"
                                                  step="0.01"
                                                  min="0"
                                                  className="financial-edit-input"
                                                  value={editingFinancialBooking.gross}
                                                  onChange={(e) => setEditingFinancialBooking({
                                                    ...editingFinancialBooking,
                                                    gross: e.target.value
                                                  })}
                                                  placeholder="0.00"
                                                />
                                              ) : (
                                                <>
                                                  {booking.grossPrice}
                                                  {booking.hasOverride && <span className="override-indicator" title="Manual override">*</span>}
                                                </>
                                              )}
                                            </td>
                                            <td>
                                              <span className="financial-promo-cell">
                                                {editingFinancialBooking?.id === booking.id ? (
                                                  <input
                                                    type="text"
                                                    className="financial-edit-input"
                                                    value={editingFinancialBooking.promo}
                                                    onChange={(e) => setEditingFinancialBooking({
                                                      ...editingFinancialBooking,
                                                      promo: e.target.value
                                                    })}
                                                    placeholder="Promo code"
                                                    title="Promotions-system code — clear to remove attribution"
                                                  />
                                                ) : (
                                                  <span className="financial-promo-text">
                                                    {booking.promoCode || '-'}
                                                  </span>
                                                )}
                                                {(booking.canEditFinancials ?? booking.needsOverride) && editingFinancialBooking?.id !== booking.id && (
                                                  <button
                                                    className="edit-btn-inline"
                                                    onClick={() => setEditingFinancialBooking({
                                                      id: booking.id,
                                                      gross: booking.grossPence ? (booking.grossPence / 100).toFixed(2) : '',
                                                      discount: booking.discountPence ? (booking.discountPence / 100).toFixed(2) : '',
                                                      initialGrossPence: booking.grossPence || 0,
                                                      initialDiscountPence: booking.discountPence || 0,
                                                      promo: booking.promoCode || '',
                                                      initialPromo: booking.promoCode || '',
                                                      refund: '',
                                                    })}
                                                    title="Edit financial values"
                                                  >
                                                    ✎ Edit
                                                  </button>
                                                )}
                                              </span>
                                            </td>
                                            {/* Discount column - editable if in edit mode */}
                                            <td style={{ color: booking.discountAmount ? '#f59e0b' : 'inherit' }}>
                                              {editingFinancialBooking?.id === booking.id ? (
                                                <input
                                                  type="number"
                                                  step="0.01"
                                                  min="0"
                                                  className="financial-edit-input"
                                                  value={editingFinancialBooking.discount}
                                                  onChange={(e) => setEditingFinancialBooking({
                                                    ...editingFinancialBooking,
                                                    discount: e.target.value
                                                  })}
                                                  placeholder="0.00"
                                                />
                                              ) : (
                                                booking.discountAmount || '-'
                                              )}
                                            </td>
                                            <td>{booking.netPrice}</td>
                                            <td style={{ color: booking.refundAmount ? '#ef4444' : 'inherit' }}>
                                              {editingFinancialBooking?.id === booking.id ? (
                                                <input
                                                  type="text"
                                                  className="financial-edit-input"
                                                  value={editingFinancialBooking.refund}
                                                  onChange={(e) => setEditingFinancialBooking({
                                                    ...editingFinancialBooking,
                                                    refund: e.target.value
                                                  })}
                                                  placeholder="re_… / £"
                                                  title="Paste a Stripe refund id (re_…) or payment intent (pi_…) to sync from Stripe, or type a refund amount in pounds"
                                                />
                                              ) : (
                                                <>
                                                  {booking.refundAmount || '-'}
                                                  {/* Payment-state tag: booking status alone hides refund
                                                      state (a completed trip can carry a partial refund) */}
                                                  {booking.paymentStatus === 'partially_refunded' && (
                                                    <span style={{ display: 'block', fontSize: '10px', color: '#f59e0b' }}>
                                                      Partial refund
                                                    </span>
                                                  )}
                                                  {booking.paymentStatus === 'refunded' && (
                                                    <span style={{ display: 'block', fontSize: '10px', color: '#ef4444' }}>
                                                      Refunded
                                                    </span>
                                                  )}
                                                </>
                                              )}
                                            </td>
                                            <td style={{ color: '#22c55e' }}>{booking.netRevenue}</td>
                                            <td>
                                              {editingFinancialBooking?.id === booking.id ? (
                                                <div className="edit-actions">
                                                  <button
                                                    className="save-btn-inline"
                                                    onClick={() => saveFinancialOverride(booking.id, editingFinancialBooking)}
                                                    disabled={savingFinancialOverride || !editingFinancialBooking.gross}
                                                    title="Save"
                                                  >
                                                    {savingFinancialOverride ? '...' : '✓'}
                                                  </button>
                                                  <button
                                                    className="cancel-btn-inline"
                                                    onClick={() => setEditingFinancialBooking(null)}
                                                    title="Cancel"
                                                  >
                                                    ✕
                                                  </button>
                                                  {editingFinancialBooking.error && (
                                                    <span
                                                      className="financial-edit-error"
                                                      style={{ color: '#ef4444', fontSize: '11px', display: 'block' }}
                                                      title={editingFinancialBooking.error}
                                                    >
                                                      {editingFinancialBooking.error}
                                                    </span>
                                                  )}
                                                </div>
                                              ) : (
                                                <span className={`status-badge status-${booking.status}`}>
                                                  {booking.status}
                                                </span>
                                              )}
                                            </td>
                                          </tr>
                                                ))}
                                              </React.Fragment>
                                            )
                                          })
                                        })()}
                                      </tbody>
                                    </table>
                                  </div>
                                )}
                              </div>
                            ))
                          )}
                        </div>
                      </>
                    ) : (
                      <p className="admin-empty">Click "Refresh Page" to load financial data.</p>
                    )}
                  </>
                )}
    
                {/* Session Tracking Report */}
                {reportsSubTab === 'sessions' && (
                  <>
                    <div className="reports-section-header">
                      <div className="period-selector">
                        <button
                          className={`period-btn ${sessionTrackingPeriod === 'daily' ? 'active' : ''}`}
                          onClick={() => setSessionTrackingPeriod('daily')}
                        >
                          Daily
                        </button>
                        <button
                          className={`period-btn ${sessionTrackingPeriod === 'weekly' ? 'active' : ''}`}
                          onClick={() => setSessionTrackingPeriod('weekly')}
                        >
                          Weekly
                        </button>
                        <button
                          className={`period-btn ${sessionTrackingPeriod === 'monthly' ? 'active' : ''}`}
                          onClick={() => setSessionTrackingPeriod('monthly')}
                        >
                          Monthly
                        </button>
                      </div>
                      <button
                        className="refresh-page-btn"
                        onClick={() => fetchSessionTracking(sessionTrackingPeriod, true)}
                        disabled={loadingSessionTracking}
                      >
                        {loadingSessionTracking ? 'Refreshing...' : 'Refresh Page'}
                      </button>
                    </div>
    
                    {loadingSessionTracking ? (
                      <div className="admin-loading-inline">
                        <div className="spinner-small"></div>
                        <span>Loading session tracking data...</span>
                      </div>
                    ) : sessionTrackingData ? (
                      <>
                        {/* Cumulative Funnel Summary */}
                        <div className="session-funnel-summary">
                          <h3>Booking Funnel (Cumulative)</h3>
                          <div className="funnel-cards">
                            {sessionTrackingData.stages?.map((stage, index) => {
                              const count = sessionTrackingData.cumulative?.counts?.[stage.key] || 0
                              const conversionRate = sessionTrackingData.cumulative?.conversion_rates?.[stage.key] || 0
                              const prevCount = index > 0
                                ? sessionTrackingData.cumulative?.counts?.[sessionTrackingData.stages[index - 1].key] || 0
                                : count
                              const dropOff = index > 0 && prevCount > 0
                                ? prevCount - count
                                : 0
    
                              return (
                                <div key={stage.key} className="funnel-card">
                                  <div className="funnel-card-header">
                                    <span className="funnel-step">{index + 1}</span>
                                    <span className="funnel-label">{stage.label}</span>
                                  </div>
                                  <div className="funnel-card-value">{count.toLocaleString()}</div>
                                  {index > 0 && (
                                    <div className="funnel-card-meta">
                                      <span className={`conversion-rate ${conversionRate >= 50 ? 'good' : conversionRate >= 25 ? 'medium' : 'poor'}`}>
                                        {conversionRate}% conversion
                                      </span>
                                      {dropOff > 0 && (
                                        <span className="drop-off">-{dropOff} dropped</span>
                                      )}
                                    </div>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                          <div className="overall-conversion">
                            <strong>Overall Conversion Rate:</strong>{' '}
                            <span className={`conversion-rate ${(sessionTrackingData.cumulative?.overall_conversion || 0) >= 10 ? 'good' : 'medium'}`}>
                              {sessionTrackingData.cumulative?.overall_conversion || 0}%
                            </span>
                            <span className="conversion-label">(Dates Selected → Booking Confirmed)</span>
                          </div>
                        </div>
    
                        {/* Period-by-Period Breakdown */}
                        <div className="session-period-table">
                          <h3>
                            {sessionTrackingPeriod === 'daily' && 'Daily Breakdown (Last 30 Days)'}
                            {sessionTrackingPeriod === 'weekly' && 'Weekly Breakdown (Last 12 Weeks)'}
                            {sessionTrackingPeriod === 'monthly' && 'Monthly Breakdown (Last 12 Months)'}
                          </h3>
                          {sessionTrackingData.periods?.length > 0 ? (
                            <table className="admin-table">
                              <thead>
                                <tr>
                                  <th>Period</th>
                                  {sessionTrackingData.stages?.map(stage => (
                                    <th key={stage.key}>{stage.label}</th>
                                  ))}
                                  <th>Manual</th>
                                  <th>Free</th>
                                </tr>
                              </thead>
                              <tbody>
                                {sessionTrackingData.periods?.slice().reverse().map(period => (
                                  <tr key={period.period}>
                                    <td><strong>{period.label}</strong></td>
                                    {sessionTrackingData.stages?.map(stage => (
                                      <td key={stage.key}>
                                        {period.counts?.[stage.key] || 0}
                                      </td>
                                    ))}
                                    <td className="manual-booking-cell">
                                      {period.manual_bookings > 0 ? `+${period.manual_bookings}` : '-'}
                                    </td>
                                    <td className="free-booking-cell">
                                      {period.free_bookings > 0 ? `+${period.free_bookings}` : '-'}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : (
                            <p className="admin-empty">No session data available for this period.</p>
                          )}
                          {(sessionTrackingData.cumulative?.manual_bookings > 0 || sessionTrackingData.cumulative?.free_bookings > 0) && (
                            <p className="manual-bookings-note">
                              {sessionTrackingData.cumulative?.manual_bookings > 0 && (
                                <>* Manual: {sessionTrackingData.cumulative.manual_bookings} booking{sessionTrackingData.cumulative.manual_bookings !== 1 ? 's' : ''} via Admin (phone/walk-in). </>
                              )}
                              {sessionTrackingData.cumulative?.free_bookings > 0 && (
                                <>* Free: {sessionTrackingData.cumulative.free_bookings} booking{sessionTrackingData.cumulative.free_bookings !== 1 ? 's' : ''} with 100% promo code. </>
                              )}
                              These bypass the payment step.
                            </p>
                          )}
                        </div>
                      </>
                    ) : (
                      <p className="admin-empty">Click "Refresh Page" to load session tracking data.</p>
                    )}
                  </>
                )}
    
                {/* Abandoned Carts Analytics */}
                {reportsSubTab === 'analytics' && (
                  <>
                    <div className="reports-section-header">
                      <div className="period-selector">
                        <button
                          className={`period-btn ${abandonedCartsPeriod === 'daily' ? 'active' : ''}`}
                          onClick={() => { setAbandonedCartsPeriod('daily'); fetchAbandonedCarts('daily'); }}
                        >
                          Daily
                        </button>
                        <button
                          className={`period-btn ${abandonedCartsPeriod === 'weekly' ? 'active' : ''}`}
                          onClick={() => { setAbandonedCartsPeriod('weekly'); fetchAbandonedCarts('weekly'); }}
                        >
                          Weekly
                        </button>
                        <button
                          className={`period-btn ${abandonedCartsPeriod === 'monthly' ? 'active' : ''}`}
                          onClick={() => { setAbandonedCartsPeriod('monthly'); fetchAbandonedCarts('monthly'); }}
                        >
                          Monthly
                        </button>
                      </div>
                      <button
                        className="refresh-page-btn"
                        onClick={() => fetchAbandonedCarts(abandonedCartsPeriod, true)}
                        disabled={loadingAbandonedCarts}
                      >
                        {loadingAbandonedCarts ? 'Refreshing...' : 'Refresh Data'}
                      </button>
                    </div>
    
                    {loadingAbandonedCarts ? (
                      <div className="admin-loading-inline">
                        <div className="spinner-small"></div>
                        <span>Loading abandoned carts data...</span>
                      </div>
                    ) : abandonedCartsData ? (
                      <>
                        {/* Cumulative Summary */}
                        <div className="abandoned-carts-summary">
                          <div className="stats-summary-cards">
                            <div className="stats-card">
                              <div className="stats-card-value">{abandonedCartsData.cumulative?.total_abandoned || 0}</div>
                              <div className="stats-card-label">Total Abandoned</div>
                            </div>
                          </div>
    
                          {/* Top Destinations */}
                          <div className="abandoned-analytics-grid">
                            <div className="abandoned-analytics-card">
                              <h4>Top Destinations (Abandoned)</h4>
                              {abandonedCartsData.cumulative?.top_destinations?.length > 0 ? (
                                <table className="admin-table compact">
                                  <thead>
                                    <tr>
                                      <th>Destination</th>
                                      <th>Count</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {abandonedCartsData.cumulative.top_destinations.map((item, idx) => (
                                      <tr key={idx}>
                                        <td>{item.destination}</td>
                                        <td>{item.count}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              ) : (
                                <p className="admin-empty">No destination data</p>
                              )}
                            </div>
    
                            <div className="abandoned-analytics-card">
                              <h4>Top Trip Lengths (Abandoned)</h4>
                              {abandonedCartsData.cumulative?.top_days?.length > 0 ? (
                                <table className="admin-table compact">
                                  <thead>
                                    <tr>
                                      <th>Days</th>
                                      <th>Count</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {abandonedCartsData.cumulative.top_days.map((item, idx) => (
                                      <tr key={idx}>
                                        <td>{item.days} days</td>
                                        <td>{item.count}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              ) : (
                                <p className="admin-empty">No trip length data</p>
                              )}
                            </div>
                          </div>
                        </div>
    
                        {/* Period-by-Period Breakdown */}
                        <div className="abandoned-period-table">
                          <h3>
                            {abandonedCartsPeriod === 'daily' && 'Daily Breakdown'}
                            {abandonedCartsPeriod === 'weekly' && 'Weekly Breakdown'}
                            {abandonedCartsPeriod === 'monthly' && 'Monthly Breakdown'}
                          </h3>
                          {abandonedCartsData.periods?.length > 0 ? (
                            <table className="admin-table">
                              <thead>
                                <tr>
                                  <th>Period</th>
                                  <th>Abandoned Sessions</th>
                                </tr>
                              </thead>
                              <tbody>
                                {abandonedCartsData.periods?.slice().reverse().map(period => (
                                  <tr key={period.period}>
                                    <td><strong>{period.label}</strong></td>
                                    <td>{period.abandoned_count}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : (
                            <p className="admin-empty">No abandoned cart data available for this period.</p>
                          )}
                        </div>
    
                        {/* Recent Abandoned Carts */}
                        <div className="abandoned-recent-table">
                          <h3>Recent Abandoned Carts (with flight details)</h3>
                          {abandonedCartsData.recent_abandoned?.length > 0 ? (
                            <div className="sql-results-table-wrapper">
                              <table className="admin-table">
                                <thead>
                                  <tr>
                                    <th>Date/Time</th>
                                    <th>Drop-off</th>
                                    <th>Departure</th>
                                    <th>Pick-up</th>
                                    <th>Arrival</th>
                                    <th>Destination</th>
                                    <th>Days</th>
                                    <th>Airline</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {abandonedCartsData.recent_abandoned.map((item, idx) => (
                                    <tr key={idx}>
                                      <td>{new Date(item.created_at).toLocaleString('en-GB', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/London' })}</td>
                                      <td>{item.dropoff_date}</td>
                                      <td>{item.departure_time}</td>
                                      <td>{item.pickup_date}</td>
                                      <td>{item.arrival_time}</td>
                                      <td>{item.destination}</td>
                                      <td>{item.days}</td>
                                      <td>{item.airline}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          ) : (
                            <p className="admin-empty">No recent abandoned carts with flight details.</p>
                          )}
                        </div>
                      </>
                    ) : (
                      <p className="admin-empty">Click "Refresh Page" to load abandoned carts data.</p>
                    )}
                  </>
                )}
    
                {/* Bookings Forecast */}
                {reportsSubTab === 'forecast' && (
                  <>
                    <div className="forecast-header">
                      <button
                        className="admin-refresh"
                        onClick={() => fetchBookingsForecast(true)}
                        disabled={loadingForecast}
                      >
                        {loadingForecast ? 'Loading...' : 'Refresh'}
                      </button>
                    </div>
    
                    {loadingForecast ? (
                      <div className="admin-loading-inline">
                        <div className="spinner-small"></div>
                        <span>Loading forecast data...</span>
                      </div>
                    ) : forecastData ? (
                      <>
                        {/* Data Range Info */}
                        <div className="forecast-info">
                          <p>Based on <strong>{forecastData.data_range?.total_bookings_analyzed || 0}</strong> bookings (last 6 months) and <strong>{forecastData.data_range?.total_abandoned_sessions || 0}</strong> abandoned searches (last 30 days)</p>
                        </div>
    
                        {/* Multi-Model Destination Predictions */}
                        <div className="forecast-section full-width">
                          <h4>Destination Predictions (3 Models)</h4>
                          <p className="forecast-subtitle">
                            <strong>Balanced:</strong> 60% bookings + 40% searches |
                            <strong> Momentum:</strong> 30% bookings + 70% searches (emerging trends) |
                            <strong> Established:</strong> 80% bookings + 20% searches (proven demand)
                          </p>
                          {forecastData.destinations?.length > 0 ? (
                            <table className="forecast-table multi-model">
                              <thead>
                                <tr>
                                  <th>Destination</th>
                                  <th>Bookings</th>
                                  <th>Searches</th>
                                  <th>Balanced</th>
                                  <th>Momentum</th>
                                  <th>Established</th>
                                  <th>Confidence</th>
                                  <th>Trend</th>
                                  <th>Best Day</th>
                                </tr>
                              </thead>
                              <tbody>
                                {forecastData.destinations.slice(0, 15).map((item, idx) => (
                                  <tr key={idx} className={item.status === 'high_demand' ? 'row-highlight' : ''}>
                                    <td><strong>{item.destination}</strong></td>
                                    <td>{item.bookings_6m}</td>
                                    <td>{item.searches_30d}</td>
                                    <td>
                                      <span className={`model-score balanced ${item.status}`}>
                                        {item.score_balanced}
                                      </span>
                                    </td>
                                    <td>
                                      <span className={`model-score momentum ${item.score_momentum > item.score_balanced ? 'higher' : ''}`}>
                                        {item.score_momentum}
                                      </span>
                                    </td>
                                    <td>
                                      <span className={`model-score established ${item.score_established > item.score_balanced ? 'higher' : ''}`}>
                                        {item.score_established}
                                      </span>
                                    </td>
                                    <td>
                                      <span className={`confidence-badge ${item.confidence}`}>
                                        {item.confidence_icon}
                                      </span>
                                    </td>
                                    <td>
                                      <span className={`trend-badge ${item.trend}`}>
                                        {item.trend === 'rising' ? '📈' : item.trend === 'stable' ? '📊' : '➖'}
                                      </span>
                                    </td>
                                    <td>{item.best_day || '-'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : (
                            <p className="admin-empty">No destination data available</p>
                          )}
                          <div className="model-legend">
                            <span><strong>Confidence:</strong> ✓✓✓ High (models agree) | ✓✓ Medium | ⚠️ Low (investigate)</span>
                            <span><strong>Trend:</strong> 📈 Rising (momentum {'>'} established) | 📊 Stable | ➖ Neutral</span>
                          </div>
                        </div>
    
                        {/* Summary Cards */}
                        <div className="forecast-grid">
    
                          {/* Day of Week Analysis - Drop-offs */}
                          <div className="forecast-card">
                            <h4>Busiest Days of Week</h4>
                            <p className="forecast-subtitle">When do customers drop off?</p>
                            {forecastData.day_of_week?.length > 0 ? (
                              <div className="dow-chart">
                                {forecastData.day_of_week.map((day, idx) => (
                                  <div key={idx} className="dow-bar-container">
                                    <span className="dow-label">{day.day_short}</span>
                                    <div className="dow-bar-wrapper">
                                      <div
                                        className="dow-bar"
                                        style={{ width: `${Math.min(day.percentage * 5, 100)}%` }}
                                      ></div>
                                    </div>
                                    <span className="dow-value">{day.bookings} ({day.percentage}%)</span>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="admin-empty">No day-of-week data available</p>
                            )}
                          </div>
    
                          {/* Day of Week Analysis - Pick-ups */}
                          <div className="forecast-card">
                            <h4>Busiest Pickup Days</h4>
                            <p className="forecast-subtitle">When do customers pick up?</p>
                            {forecastData.pickup_day_of_week?.length > 0 ? (
                              <div className="dow-chart">
                                {forecastData.pickup_day_of_week.map((day, idx) => (
                                  <div key={idx} className="dow-bar-container">
                                    <span className="dow-label">{day.day_short}</span>
                                    <div className="dow-bar-wrapper">
                                      <div
                                        className="dow-bar pickup"
                                        style={{ width: `${Math.min(day.percentage * 5, 100)}%` }}
                                      ></div>
                                    </div>
                                    <span className="dow-value">{day.bookings} ({day.percentage}%)</span>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="admin-empty">No pickup day data available</p>
                            )}
                          </div>
    
                          {/* Combined Seasonality - Booking, Travel & Abandoned Month */}
                          <div className="forecast-card wide">
                            <h4>Monthly Patterns</h4>
                            <p className="forecast-subtitle">Booked (green) · Traveled (blue) · Abandoned (red)</p>
                            {forecastData.seasonality_travel?.length > 0 ? (
                              <div className="monthly-patterns-chart">
                                {(() => {
                                  const maxTravel = Math.max(...forecastData.seasonality_travel.map(m => m.bookings)) || 1;
                                  const maxBooking = Math.max(...(forecastData.seasonality_booking || []).map(m => m.bookings)) || 1;
                                  const maxAbandoned = Math.max(...(forecastData.seasonality_abandoned || []).map(m => m.count)) || 1;
                                  const maxAll = Math.max(maxTravel, maxBooking, maxAbandoned);
                                  return forecastData.seasonality_travel.map((travelMonth, idx) => {
                                    const bookingMonth = forecastData.seasonality_booking?.[idx] || { bookings: 0 };
                                    const abandonedMonth = forecastData.seasonality_abandoned?.[idx] || { count: 0 };
      return (
                                      <div key={idx} className="monthly-column">
                                        <div className="monthly-bars">
                                          <div className="monthly-bar-group">
                                            <div
                                              className="monthly-bar booking"
                                              style={{ height: `${(bookingMonth.bookings / maxAll) * 100}%` }}
                                              title={`Booked: ${bookingMonth.bookings}`}
                                            ></div>
                                            <div
                                              className="monthly-bar travel"
                                              style={{ height: `${(travelMonth.bookings / maxAll) * 100}%` }}
                                              title={`Traveled: ${travelMonth.bookings}`}
                                            ></div>
                                            <div
                                              className="monthly-bar abandoned"
                                              style={{ height: `${(abandonedMonth.count / maxAll) * 100}%` }}
                                              title={`Abandoned: ${abandonedMonth.count}`}
                                            ></div>
                                          </div>
                                        </div>
                                        <span className="monthly-label">{travelMonth.month}</span>
                                      </div>
                                    );
                                  });
                                })()}
                                <div className="combined-legend">
                                  <span className="legend-item"><span className="legend-color booking"></span> Booked</span>
                                  <span className="legend-item"><span className="legend-color travel"></span> Traveled</span>
                                  <span className="legend-item"><span className="legend-color abandoned"></span> Abandoned</span>
                                </div>
                              </div>
                            ) : (
                              <p className="admin-empty">No data available</p>
                            )}
                          </div>
    
                          {/* Departure Times */}
                          <div className="forecast-card">
                            <h4>Departure Times</h4>
                            <p className="forecast-subtitle">Most popular flight departure times</p>
                            {forecastData.departure_times?.length > 0 ? (
                              <div className="departure-time-chart">
                                {(() => {
                                  const maxBookings = Math.max(...forecastData.departure_times.map(t => t.bookings)) || 1;
                                  return forecastData.departure_times.map((slot, idx) => (
                                    <div key={idx} className="time-bar-container">
                                      <span className="time-label">{slot.time}</span>
                                      <div className="time-bar-wrapper">
                                        <div
                                          className="time-bar"
                                          style={{ width: `${(slot.bookings / maxBookings) * 100}%` }}
                                        ></div>
                                      </div>
                                      <span className="time-value">{slot.bookings}</span>
                                    </div>
                                  ));
                                })()}
                              </div>
                            ) : (
                              <p className="admin-empty">No departure time data available</p>
                            )}
                          </div>
    
                          {/* Arrival Times */}
                          <div className="forecast-card">
                            <h4>Arrival Times</h4>
                            <p className="forecast-subtitle">Most popular flight arrival times</p>
                            {forecastData.arrival_times?.length > 0 ? (
                              <div className="departure-time-chart">
                                {(() => {
                                  const maxBookings = Math.max(...forecastData.arrival_times.map(t => t.bookings)) || 1;
                                  return forecastData.arrival_times.map((slot, idx) => (
                                    <div key={idx} className="time-bar-container">
                                      <span className="time-label">{slot.time}</span>
                                      <div className="time-bar-wrapper">
                                        <div
                                          className="time-bar arrival"
                                          style={{ width: `${(slot.bookings / maxBookings) * 100}%` }}
                                        ></div>
                                      </div>
                                      <span className="time-value">{slot.bookings}</span>
                                    </div>
                                  ));
                                })()}
                              </div>
                            ) : (
                              <p className="admin-empty">No arrival time data available</p>
                            )}
                          </div>
    
                          {/* Top Airlines */}
                          <div className="forecast-card">
                            <h4>Top Airlines</h4>
                            <p className="forecast-subtitle">Most popular carriers</p>
                            {forecastData.airlines?.length > 0 ? (
                              <table className="forecast-table compact">
                                <thead>
                                  <tr>
                                    <th>Airline</th>
                                    <th>Bookings</th>
                                    <th>Searches</th>
                                    <th>%</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {forecastData.airlines.map((item, idx) => (
                                    <tr key={idx}>
                                      <td>{item.airline}</td>
                                      <td>{item.bookings_6m}</td>
                                      <td>{item.searches_30d}</td>
                                      <td>{item.percentage}%</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            ) : (
                              <p className="admin-empty">No airline data available</p>
                            )}
                          </div>
                        </div>
    
                        {/* Predicted Dates */}
                        {forecastData.predicted_dates?.length > 0 && (
                          <div className="forecast-section">
                            <h4>Predicted Busy Dates</h4>
                            <p className="forecast-subtitle">Next 30 days ranked by likelihood of bookings</p>
                            <div className="predicted-dates-grid">
                              {forecastData.predicted_dates.slice(0, 10).map((item, idx) => (
                                <div key={idx} className={`predicted-date-card ${item.likelihood}`}>
                                  <div className="predicted-date">{item.display_date}</div>
                                  <div className="predicted-day">{item.day_of_week}</div>
                                  <div className="predicted-score">Score: {item.prediction_score}</div>
                                  {item.searches > 0 && (
                                    <div className="predicted-searches">{item.searches} active searches</div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
    
                        {/* Opportunity Gaps */}
                        {forecastData.opportunity_gaps?.length > 0 && (
                          <div className="forecast-section">
                            <h4>Opportunity Gaps</h4>
                            <p className="forecast-subtitle">High search interest but low conversion - potential untapped demand</p>
                            <table className="forecast-table">
                              <thead>
                                <tr>
                                  <th>Destination</th>
                                  <th>Searches (30d)</th>
                                  <th>Bookings (6m)</th>
                                  <th>Gap Score</th>
                                </tr>
                              </thead>
                              <tbody>
                                {forecastData.opportunity_gaps.map((item, idx) => (
                                  <tr key={idx}>
                                    <td><strong>{item.destination}</strong></td>
                                    <td>{item.searches}</td>
                                    <td>{item.bookings}</td>
                                    <td>
                                      <span className="opportunity-score">{item.gap_score.toFixed(1)}</span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
    
                        {/* Upcoming Demand */}
                        {forecastData.upcoming_demand?.length > 0 && (
                          <div className="forecast-section">
                            <h4>Upcoming Dates with Search Interest</h4>
                            <p className="forecast-subtitle">Dates people are searching for in the next 30 days</p>
                            <div className="upcoming-demand-grid">
                              {forecastData.upcoming_demand.map((item, idx) => (
                                <div key={idx} className="upcoming-demand-card">
                                  <div className="upcoming-date">{item.display_date}</div>
                                  <div className="upcoming-day">{item.day_of_week}</div>
                                  <div className="upcoming-searches">{item.searches} searches</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    ) : (
                      <p className="admin-empty">No forecast data available. Click Refresh to load.</p>
                    )}
                  </>
                )}
              </div>
  )
}

export default ReportsSectionPage
