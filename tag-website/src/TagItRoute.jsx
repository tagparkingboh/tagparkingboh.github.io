import { useNavigate } from 'react-router-dom'
import HomePage from './HomePage.jsx'
import BookingModal from './components/BookingModal.jsx'

function TagItRoute() {
  const navigate = useNavigate()
  return (
    <>
      <HomePage />
      <BookingModal open onClose={() => navigate('/')} />
    </>
  )
}

export default TagItRoute
