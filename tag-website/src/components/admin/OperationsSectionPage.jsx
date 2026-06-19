import BookingsSection from './BookingsSection'
import CalendarSection from './CalendarSection'
import ManualBookingSection from './ManualBookingSection'
import FlightsSection from './FlightsSection'

const OperationsSectionPage = ({
  activeTab,
  bookingSectionProps,
  token,
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
  if (activeTab === 'bookings') {
    return <BookingsSection {...bookingSectionProps} />
  }

  if (activeTab === 'calendar') {
    return <CalendarSection token={token} />
  }

  if (activeTab === 'manual-booking') {
    return <ManualBookingSection token={token} />
  }

  if (activeTab === 'flights') {
    return (
      <FlightsSection
        fetchFlights={fetchFlights}
        exportFlights={exportFlights}
        loadingFlights={loadingFlights}
        exportingFlights={exportingFlights}
        flightsMessage={flightsMessage}
        flightsSubTab={flightsSubTab}
        setFlightsSubTab={setFlightsSubTab}
        setEditingFlightId={setEditingFlightId}
        flightAirlineFilter={flightAirlineFilter}
        setFlightAirlineFilter={setFlightAirlineFilter}
        flightFilters={flightFilters}
        flightNumberFilter={flightNumberFilter}
        setFlightNumberFilter={setFlightNumberFilter}
        departures={departures}
        arrivals={arrivals}
        flightDestFilter={flightDestFilter}
        setFlightDestFilter={setFlightDestFilter}
        flightOriginFilter={flightOriginFilter}
        setFlightOriginFilter={setFlightOriginFilter}
        flightMonthFilter={flightMonthFilter}
        setFlightMonthFilter={setFlightMonthFilter}
        flightsSortAsc={flightsSortAsc}
        setFlightsSortAsc={setFlightsSortAsc}
        departuresByMonth={departuresByMonth}
        arrivalsByMonth={arrivalsByMonth}
        collapsedFlightMonths={collapsedFlightMonths}
        toggleFlightMonth={toggleFlightMonth}
        editingFlightId={editingFlightId}
        setEditFlightForm={setEditFlightForm}
        editFlightForm={editFlightForm}
        savingFlight={savingFlight}
        saveFlightEdit={saveFlightEdit}
        cancelEditFlight={cancelEditFlight}
        startEditFlight={startEditFlight}
        confirmDeleteFlight={confirmDeleteFlight}
        showAddFlightModal={showAddFlightModal}
        setShowAddFlightModal={setShowAddFlightModal}
        addFlightForm={addFlightForm}
        setAddFlightForm={setAddFlightForm}
        resetAddFlightForm={resetAddFlightForm}
        handleAddFlight={handleAddFlight}
        addingFlight={addingFlight}
        showDeleteFlightModal={showDeleteFlightModal}
        flightToDelete={flightToDelete}
        setShowDeleteFlightModal={setShowDeleteFlightModal}
        setFlightToDelete={setFlightToDelete}
        handleDeleteFlight={handleDeleteFlight}
        deletingFlightId={deletingFlightId}
      />
    )
  }

  return null
}

export default OperationsSectionPage
