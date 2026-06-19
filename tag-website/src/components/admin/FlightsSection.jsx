const FlightsSection = ({
  fetchFlights,
  exportFlights,
  loadingFlights,
  exportingFlights,
  flightsMessage,
  flightsSubTab,
  setFlightsSubTab,
  setEditingFlightId,
  flightAirlineFilter,
  setFlightAirlineFilter,
  flightFilters,
  flightNumberFilter,
  setFlightNumberFilter,
  departures,
  arrivals,
  flightDestFilter,
  setFlightDestFilter,
  flightOriginFilter,
  setFlightOriginFilter,
  flightMonthFilter,
  setFlightMonthFilter,
  flightsSortAsc,
  setFlightsSortAsc,
  departuresByMonth,
  arrivalsByMonth,
  collapsedFlightMonths,
  toggleFlightMonth,
  editingFlightId,
  setEditFlightForm,
  editFlightForm,
  savingFlight,
  saveFlightEdit,
  cancelEditFlight,
  startEditFlight,
  confirmDeleteFlight,
  showAddFlightModal,
  setShowAddFlightModal,
  addFlightForm,
  setAddFlightForm,
  resetAddFlightForm,
  handleAddFlight,
  addingFlight,
  showDeleteFlightModal,
  flightToDelete,
  setShowDeleteFlightModal,
  setFlightToDelete,
  handleDeleteFlight,
  deletingFlightId,
}) => {
  return (
    <div className="admin-section">
      <div className="flights-header">
        <h2>Flight Schedule</h2>
        <div className="flights-header-actions">
          <button
            className="btn-secondary"
            onClick={() => fetchFlights()}
            disabled={loadingFlights}
          >
            ↻ Refresh
          </button>
          <button
            className="btn-primary"
            onClick={exportFlights}
            disabled={exportingFlights}
          >
            {exportingFlights ? 'Exporting...' : '↓ Export JSON'}
          </button>
          <button
            className="btn-primary"
            onClick={() => setShowAddFlightModal(true)}
          >
            + Add Flight
          </button>
        </div>
      </div>

      {flightsMessage && (
        <div className={`flights-message ${flightsMessage.includes('Error') || flightsMessage.includes('Warning') ? 'warning' : 'success'}`}>
          {flightsMessage}
        </div>
      )}

      {/* Sub-tabs */}
      <div className="flights-subtabs">
        <button
          className={`flights-subtab ${flightsSubTab === 'departures' ? 'active' : ''}`}
          onClick={() => { setEditingFlightId(null); setFlightsSubTab('departures') }}
        >
          Departures ({departures.length})
        </button>
        <button
          className={`flights-subtab ${flightsSubTab === 'arrivals' ? 'active' : ''}`}
          onClick={() => { setEditingFlightId(null); setFlightsSubTab('arrivals') }}
        >
          Arrivals ({arrivals.length})
        </button>
      </div>

      {/* Filters */}
      <div className="flights-filters">
        <div className="flight-filter-group">
          <label>Airline:</label>
          <select
            value={flightAirlineFilter}
            onChange={(e) => setFlightAirlineFilter(e.target.value)}
          >
            <option value="">All Airlines</option>
            {flightFilters.airlines?.map(a => (
              <option key={a.code} value={a.code}>{a.code} - {a.name}</option>
            ))}
          </select>
        </div>

        <div className="flight-filter-group">
          <label>Flight #:</label>
          <input
            type="text"
            value={flightNumberFilter}
            onChange={(e) => setFlightNumberFilter(e.target.value.toUpperCase())}
            placeholder="e.g. BA123"
            className="flight-number-input"
          />
        </div>

        {flightsSubTab === 'departures' ? (
          <div className="flight-filter-group">
            <label>Destination:</label>
            <select
              value={flightDestFilter}
              onChange={(e) => setFlightDestFilter(e.target.value)}
            >
              <option value="">All Destinations</option>
              {flightFilters.destinations?.map(d => (
                <option key={d.code} value={d.code}>{d.code} - {d.name}</option>
              ))}
            </select>
          </div>
        ) : (
          <div className="flight-filter-group">
            <label>Origin:</label>
            <select
              value={flightOriginFilter}
              onChange={(e) => setFlightOriginFilter(e.target.value)}
            >
              <option value="">All Origins</option>
              {flightFilters.origins?.map(o => (
                <option key={o.code} value={o.code}>{o.code} - {o.name}</option>
              ))}
            </select>
          </div>
        )}

        <div className="flight-filter-group">
          <label>Month:</label>
          <select
            value={flightMonthFilter}
            onChange={(e) => setFlightMonthFilter(e.target.value)}
          >
            <option value="">All Months</option>
            {flightFilters.months?.map(m => (
              <option key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}>{m.label}</option>
            ))}
          </select>
        </div>

        <button
          className="sort-toggle-btn"
          onClick={() => setFlightsSortAsc(!flightsSortAsc)}
          title={flightsSortAsc ? 'Sorted oldest first' : 'Sorted newest first'}
        >
          Date {flightsSortAsc ? '↑' : '↓'}
        </button>
      </div>

      {/* Data Table - Month Containers */}
      {loadingFlights ? (
        <p className="loading-text">Loading flights...</p>
      ) : flightsSubTab === 'departures' ? (
        <div className="flights-by-month">
          {Object.keys(departuresByMonth).length === 0 ? (
            <p className="no-data">No departures found</p>
          ) : (
            Object.entries(departuresByMonth).map(([monthKey, monthData]) => (
              <div key={monthKey} className="flight-month-section">
                <div
                  className="flight-month-header"
                  onClick={() => toggleFlightMonth(monthKey)}
                >
                  <span className="collapse-icon">{collapsedFlightMonths[monthKey] ? '▶' : '▼'}</span>
                  <span className="month-label">{monthData.label}</span>
                  <span className="flight-count">({monthData.flights.length} flights)</span>
                </div>
                {!collapsedFlightMonths[monthKey] && (
                  <div className="flights-table-wrapper">
                    <table className="flights-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Airline</th>
                          <th>Flight #</th>
                          <th>Departure Time</th>
                          <th>Destination</th>
                          <th>Capacity Tier</th>
                          <th>Early</th>
                          <th>Late</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {monthData.flights.map(d => (
                          <tr key={d.id} className={editingFlightId === d.id ? 'editing' : ''}>
                            {editingFlightId === d.id ? (
                              <>
                                <td>{d.date ? d.date.split('-').reverse().join('/') : ''}</td>
                                <td>{d.airline_name}</td>
                                <td>
                                  <input
                                    type="text"
                                    value={editFlightForm.flight_number || ''}
                                    onChange={(e) => setEditFlightForm({ ...editFlightForm, flight_number: e.target.value })}
                                    className="flight-edit-input small"
                                  />
                                </td>
                                <td>
                                  <input
                                    type="text"
                                    pattern="[0-2][0-9]:[0-5][0-9]"
                                    placeholder="HH:MM"
                                    value={editFlightForm.departure_time || ''}
                                    onChange={(e) => setEditFlightForm({ ...editFlightForm, departure_time: e.target.value })}
                                    className="flight-edit-input time-24h"
                                  />
                                </td>
                                <td>{d.destination_name}</td>
                                <td>
                                  <select
                                    value={editFlightForm.capacity_tier ?? ''}
                                    onChange={(e) => setEditFlightForm({ ...editFlightForm, capacity_tier: parseInt(e.target.value) })}
                                    className="flight-edit-input"
                                  >
                                    <option value="0">0 (Call Us)</option>
                                    <option value="2">2 (1+1)</option>
                                    <option value="4">4 (2+2)</option>
                                    <option value="6">6 (3+3)</option>
                                    <option value="8">8 (4+4)</option>
                                  </select>
                                </td>
                                <td>
                                  <span className="slots-display">
                                    {d.slots_booked_early}/{d.max_slots_per_time}
                                  </span>
                                </td>
                                <td>
                                  <span className="slots-display">
                                    {d.slots_booked_late}/{d.max_slots_per_time}
                                  </span>
                                </td>
                                <td className="flight-actions">
                                  <button className="btn-save" onClick={saveFlightEdit} disabled={savingFlight}>
                                    {savingFlight ? '...' : '✓'}
                                  </button>
                                  <button className="btn-cancel" onClick={cancelEditFlight}>✕</button>
                                </td>
                              </>
                            ) : (
                              <>
                                <td>{d.date ? d.date.split('-').reverse().join('/') : ''}</td>
                                <td>{d.airline_name}</td>
                                <td>{d.flight_number}</td>
                                <td>{d.departure_time}</td>
                                <td>{d.destination_name}</td>
                                <td>
                                  <span className={`capacity-badge tier-${d.capacity_tier}`}>
                                    {d.capacity_tier === 0 ? 'Call' : d.capacity_tier}
                                  </span>
                                </td>
                                <td>
                                  <span className="slots-display">
                                    {d.slots_booked_early}/{d.max_slots_per_time}
                                  </span>
                                </td>
                                <td>
                                  <span className="slots-display">
                                    {d.slots_booked_late}/{d.max_slots_per_time}
                                  </span>
                                </td>
                                <td className="flight-actions">
                                  <button className="btn-edit" onClick={() => startEditFlight(d)}>Edit</button>
                                  <button className="btn-delete" onClick={() => confirmDeleteFlight(d)}>Delete</button>
                                </td>
                              </>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="flights-by-month">
          {Object.keys(arrivalsByMonth).length === 0 ? (
            <p className="no-data">No arrivals found</p>
          ) : (
            Object.entries(arrivalsByMonth).map(([monthKey, monthData]) => (
              <div key={monthKey} className="flight-month-section">
                <div
                  className="flight-month-header"
                  onClick={() => toggleFlightMonth(monthKey)}
                >
                  <span className="collapse-icon">{collapsedFlightMonths[monthKey] ? '▶' : '▼'}</span>
                  <span className="month-label">{monthData.label}</span>
                  <span className="flight-count">({monthData.flights.length} flights)</span>
                </div>
                {!collapsedFlightMonths[monthKey] && (
                  <div className="flights-table-wrapper">
                    <table className="flights-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Airline</th>
                          <th>Flight #</th>
                          <th>Origin</th>
                          <th>Arrival Time</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {monthData.flights.map(a => (
                          <tr key={a.id} className={editingFlightId === a.id ? 'editing' : ''}>
                            {editingFlightId === a.id ? (
                              <>
                                <td>{a.date ? a.date.split('-').reverse().join('/') : ''}</td>
                                <td>{a.airline_name}</td>
                                <td>
                                  <input
                                    type="text"
                                    value={editFlightForm.flight_number || ''}
                                    onChange={(e) => setEditFlightForm({ ...editFlightForm, flight_number: e.target.value })}
                                    className="flight-edit-input small"
                                  />
                                </td>
                                <td>{a.origin_name}</td>
                                <td>
                                  <input
                                    type="text"
                                    pattern="[0-2][0-9]:[0-5][0-9]"
                                    placeholder="HH:MM"
                                    value={editFlightForm.arrival_time || ''}
                                    onChange={(e) => setEditFlightForm({ ...editFlightForm, arrival_time: e.target.value })}
                                    className="flight-edit-input time-24h"
                                  />
                                </td>
                                <td className="flight-actions">
                                  <button className="btn-save" onClick={saveFlightEdit} disabled={savingFlight}>
                                    {savingFlight ? '...' : '✓'}
                                  </button>
                                  <button className="btn-cancel" onClick={cancelEditFlight}>✕</button>
                                </td>
                              </>
                            ) : (
                              <>
                                <td>{a.date ? a.date.split('-').reverse().join('/') : ''}</td>
                                <td>{a.airline_name}</td>
                                <td>{a.flight_number}</td>
                                <td>{a.origin_name}</td>
                                <td>{a.arrival_time}{a.departure_time && parseInt(a.departure_time.split(':')[0]) >= 18 && parseInt(a.arrival_time.split(':')[0]) < 6 ? ' +1' : ''}</td>
                                <td className="flight-actions">
                                  <button className="btn-edit" onClick={() => startEditFlight(a)}>Edit</button>
                                  <button className="btn-delete" onClick={() => confirmDeleteFlight(a)}>Delete</button>
                                </td>
                              </>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Add Flight Modal */}
      {showAddFlightModal && (
        <div className="modal-overlay" onClick={() => { setShowAddFlightModal(false); resetAddFlightForm() }}>
          <div className="modal-content add-flight-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Add New {flightsSubTab === 'departures' ? 'Departure' : 'Arrival'}</h3>
            <div className="add-flight-form">
              <div className="form-row">
                <label>Date:</label>
                <input
                  type="date"
                  value={addFlightForm.date}
                  onChange={(e) => setAddFlightForm({ ...addFlightForm, date: e.target.value })}
                  min="2026-01-01"
                />
              </div>
              <div className="form-row">
                <label>Flight Number:</label>
                <input
                  type="text"
                  value={addFlightForm.flight_number}
                  onChange={(e) => setAddFlightForm({ ...addFlightForm, flight_number: e.target.value.toUpperCase() })}
                  placeholder="e.g. FR1234"
                />
              </div>
              <div className="form-row">
                <label>Airline Code:</label>
                <input
                  type="text"
                  value={addFlightForm.airline_code}
                  onChange={(e) => setAddFlightForm({ ...addFlightForm, airline_code: e.target.value.toUpperCase() })}
                  placeholder="e.g. FR"
                  maxLength={3}
                />
              </div>
              <div className="form-row">
                <label>Airline Name:</label>
                <input
                  type="text"
                  value={addFlightForm.airline_name}
                  onChange={(e) => setAddFlightForm({ ...addFlightForm, airline_name: e.target.value })}
                  placeholder="e.g. Ryanair"
                />
              </div>
              <div className="form-row">
                <label>{flightsSubTab === 'departures' ? 'Departure' : 'Arrival'} Time:</label>
                <input
                  type="text"
                  value={addFlightForm.time}
                  onChange={(e) => setAddFlightForm({ ...addFlightForm, time: e.target.value })}
                  placeholder="HH:MM (24hr)"
                  pattern="[0-2][0-9]:[0-5][0-9]"
                />
              </div>
              {flightsSubTab === 'departures' ? (
                <>
                  <div className="form-row">
                    <label>Destination Code:</label>
                    <input
                      type="text"
                      value={addFlightForm.destination_code}
                      onChange={(e) => setAddFlightForm({ ...addFlightForm, destination_code: e.target.value.toUpperCase() })}
                      placeholder="e.g. AGP"
                      maxLength={3}
                    />
                  </div>
                  <div className="form-row">
                    <label>Destination Name:</label>
                    <input
                      type="text"
                      value={addFlightForm.destination_name}
                      onChange={(e) => setAddFlightForm({ ...addFlightForm, destination_name: e.target.value })}
                      placeholder="e.g. Malaga (optional)"
                    />
                  </div>
                  <div className="form-row">
                    <label>Capacity Tier:</label>
                    <select
                      value={addFlightForm.capacity_tier}
                      onChange={(e) => setAddFlightForm({ ...addFlightForm, capacity_tier: parseInt(e.target.value) })}
                    >
                      <option value="0">0 (Call Us only)</option>
                      <option value="2">2 (1+1)</option>
                      <option value="4">4 (2+2)</option>
                      <option value="6">6 (3+3)</option>
                      <option value="8">8 (4+4)</option>
                    </select>
                  </div>
                </>
              ) : (
                <>
                  <div className="form-row">
                    <label>Origin Code:</label>
                    <input
                      type="text"
                      value={addFlightForm.origin_code}
                      onChange={(e) => setAddFlightForm({ ...addFlightForm, origin_code: e.target.value.toUpperCase() })}
                      placeholder="e.g. AGP"
                      maxLength={3}
                    />
                  </div>
                  <div className="form-row">
                    <label>Origin Name:</label>
                    <input
                      type="text"
                      value={addFlightForm.origin_name}
                      onChange={(e) => setAddFlightForm({ ...addFlightForm, origin_name: e.target.value })}
                      placeholder="e.g. Malaga (optional)"
                    />
                  </div>
                  <div className="form-row">
                    <label>Departure Time (from origin):</label>
                    <input
                      type="text"
                      value={addFlightForm.departure_time}
                      onChange={(e) => setAddFlightForm({ ...addFlightForm, departure_time: e.target.value })}
                      placeholder="HH:MM (optional)"
                      pattern="[0-2][0-9]:[0-5][0-9]"
                    />
                  </div>
                </>
              )}
            </div>
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => { setShowAddFlightModal(false); resetAddFlightForm() }}>Cancel</button>
              <button
                className="modal-btn modal-btn-primary"
                onClick={handleAddFlight}
                disabled={addingFlight || !addFlightForm.date || !addFlightForm.flight_number || !addFlightForm.airline_code || !addFlightForm.airline_name || !addFlightForm.time || (flightsSubTab === 'departures' ? !addFlightForm.destination_code : !addFlightForm.origin_code)}
              >
                {addingFlight ? 'Adding...' : 'Add Flight'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Flight Confirmation Modal */}
      {showDeleteFlightModal && flightToDelete && (
        <div className="modal-overlay" onClick={() => { setShowDeleteFlightModal(false); setFlightToDelete(null) }}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h3>Delete Flight</h3>
            <p>Are you sure you want to delete flight <strong>{flightToDelete.flight_number}</strong> on {flightToDelete.date ? flightToDelete.date.split('-').reverse().join('/') : ''}?</p>
            <p className="warning-text">This action cannot be undone.</p>
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => { setShowDeleteFlightModal(false); setFlightToDelete(null) }}>Cancel</button>
              <button className="modal-btn modal-btn-danger" onClick={handleDeleteFlight} disabled={deletingFlightId}>
                {deletingFlightId ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default FlightsSection
