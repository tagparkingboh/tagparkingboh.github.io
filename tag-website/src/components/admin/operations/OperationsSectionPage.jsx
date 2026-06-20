import BookingsPage from './BookingsPage'
import CalendarPage from './CalendarPage'
import ManualBookingPage from './ManualBookingPage'
import FlightsPage from './FlightsPage'
import MessagesPage from '../messages/MessagesPage'

const OperationsSectionPage = ({
  activeTab,
  bookingsPageProps,
  calendarPageProps,
  manualBookingPageProps,
  flightsPageProps,
  messagesPageProps,
}) => {
  if (activeTab === 'bookings') {
    return <BookingsPage {...bookingsPageProps} />
  }

  if (activeTab === 'calendar') {
    return <CalendarPage {...calendarPageProps} />
  }

  if (activeTab === 'manual-booking') {
    return <ManualBookingPage {...manualBookingPageProps} />
  }

  if (activeTab === 'flights') {
    return <FlightsPage {...flightsPageProps} />
  }

  if (activeTab === 'messages') {
    return <MessagesPage {...messagesPageProps} />
  }

  return null
}

export default OperationsSectionPage
