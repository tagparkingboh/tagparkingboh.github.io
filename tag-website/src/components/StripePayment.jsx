import { useState, useEffect } from 'react'
import { loadStripe } from '@stripe/stripe-js'
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from '@stripe/react-stripe-js'

// API base URL - adjust for production
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Convert country name to ISO 2-letter code for Stripe
const getCountryCode = (countryName) => {
  const countryMap = {
    'United Kingdom': 'GB',
    'Ireland': 'IE',
    'Austria': 'AT',
    'Belgium': 'BE',
    'Croatia': 'HR',
    'Cyprus': 'CY',
    'Czech Republic': 'CZ',
    'Denmark': 'DK',
    'Estonia': 'EE',
    'Finland': 'FI',
    'France': 'FR',
    'Germany': 'DE',
    'Greece': 'GR',
    'Hungary': 'HU',
    'Iceland': 'IS',
    'Italy': 'IT',
    'Latvia': 'LV',
    'Lithuania': 'LT',
    'Luxembourg': 'LU',
    'Malta': 'MT',
    'Netherlands': 'NL',
    'Norway': 'NO',
    'Poland': 'PL',
    'Portugal': 'PT',
    'Romania': 'RO',
    'Slovakia': 'SK',
    'Slovenia': 'SI',
    'Spain': 'ES',
    'Sweden': 'SE',
    'Switzerland': 'CH',
    'Turkey': 'TR',
    'Australia': 'AU',
    'Canada': 'CA',
    'New Zealand': 'NZ',
    'United States': 'US',
  }
  return countryMap[countryName] || 'GB'
}

// Stripe promise - loaded once
let stripePromise = null

const getStripe = async () => {
  if (!stripePromise) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/stripe/config`)
      const { publishable_key } = await response.json()
      stripePromise = loadStripe(publishable_key)
    } catch (error) {
      console.error('Failed to load Stripe config:', error)
      return null
    }
  }
  return stripePromise
}

// The checkout form component (inside Elements provider)
function CheckoutForm({ onSuccess, onError, bookingReference, amount, billingDetails }) {
  const stripe = useStripe()
  const elements = useElements()
  const [isProcessing, setIsProcessing] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    console.log('Payment form submitted')
    console.log('Stripe loaded:', !!stripe)
    console.log('Elements loaded:', !!elements)

    if (!stripe || !elements) {
      console.error('Stripe or Elements not loaded')
      return
    }

    setIsProcessing(true)
    setErrorMessage('')

    try {
      console.log('Calling stripe.confirmPayment...')
      const { error, paymentIntent } = await stripe.confirmPayment({
        elements,
        confirmParams: {
          return_url: `${window.location.origin}/booking-confirmation`,
        },
        redirect: 'if_required',
      })

      console.log('Payment result:', { error, paymentIntent })

      if (error) {
        console.error('Payment error:', error)
        setErrorMessage(error.message)
        onError?.(error)
      } else if (paymentIntent && paymentIntent.status === 'succeeded') {
        console.log('Payment succeeded!')
        onSuccess?.(paymentIntent, bookingReference)
      }
    } catch (err) {
      console.error('Unexpected error:', err)
      setErrorMessage('An unexpected error occurred.')
      onError?.(err)
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <div className="stripe-form">
      <PaymentElement
        options={{
          layout: 'tabs',
          defaultValues: {
            billingDetails: {
              name: billingDetails.name || '',
              email: billingDetails.email || '',
              phone: billingDetails.phone || '',
              address: {
                postal_code: billingDetails.postcode || '',
                country: billingDetails.country || 'GB',
              },
            },
          },
        }}
      />

      {errorMessage && (
        <div className="stripe-error">
          {errorMessage}
        </div>
      )}

      <button
        type="button"
        onClick={handleSubmit}
        disabled={!stripe || isProcessing}
        className="stripe-pay-btn"
      >
        {isProcessing ? 'Processing...' : `Pay ${amount}`}
      </button>
    </div>
  )
}

// Main Stripe Payment component
function StripePayment({
  formData,
  selectedFlight,
  selectedArrivalFlight,
  customerId,
  vehicleId,
  sessionId,
  promoCode,
  onPaymentSuccess,
  onPaymentError,
}) {
  const [clientSecret, setClientSecret] = useState('')
  const [bookingReference, setBookingReference] = useState('')
  const [amount, setAmount] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [stripeLoaded, setStripeLoaded] = useState(null)

  useEffect(() => {
    // Load Stripe and create payment intent
    const initPayment = async () => {
      setLoading(true)
      setError('')

      try {
        // Load Stripe
        const stripe = await getStripe()
        if (!stripe) {
          setError('Payment system unavailable. Please try again later.')
          setLoading(false)
          return
        }
        setStripeLoaded(stripe)

        // Create payment intent with full booking data
        console.log('[PROMO] Creating payment intent with promo code:', promoCode)
        const response = await fetch(`${API_BASE_URL}/api/payments/create-intent`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            // IDs from incremental saves (if available)
            customer_id: customerId || null,
            vehicle_id: vehicleId || null,
            session_id: sessionId || null,
            // Customer details
            first_name: formData.firstName,
            last_name: formData.lastName,
            email: formData.email,
            phone: formData.phone,
            // Billing address
            billing_address1: formData.billingAddress1,
            billing_address2: formData.billingAddress2,
            billing_city: formData.billingCity,
            billing_county: formData.billingCounty,
            billing_postcode: formData.billingPostcode,
            billing_country: formData.billingCountry,
            // Vehicle details
            registration: formData.registration,
            make: formData.make === 'Other' ? formData.customMake : formData.make,
            model: formData.model === 'Other' ? formData.customModel : formData.model,
            colour: formData.colour,
            // Package
            package: formData.package,
            // Flight details
            flight_number: selectedFlight?.flightNumber || formData.dropoffFlight?.split('|')[1] || 'Unknown',
            flight_date: formData.dropoffDate ? formData.dropoffDate.toISOString().split('T')[0] : '',
            drop_off_date: formData.dropoffDate ? formData.dropoffDate.toISOString().split('T')[0] : '',
            pickup_date: formData.pickupDate ? formData.pickupDate.toISOString().split('T')[0] : '',
            drop_off_slot: formData.dropoffSlot || null,
            departure_id: selectedFlight?.id || null,
            // Return flight details
            pickup_flight_time: selectedArrivalFlight?.time || null,
            pickup_flight_number: selectedArrivalFlight?.flightNumber || null,
            pickup_origin: selectedArrivalFlight?.originCode || null,
            // Promo code (if applied)
            promo_code: promoCode || null,
          }),
        })

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.detail || 'Failed to initialize payment')
        }

        const data = await response.json()
        setClientSecret(data.client_secret)
        setBookingReference(data.booking_reference)
        setAmount(data.amount_display)
      } catch (err) {
        console.error('Payment init error:', err)
        setError(err.message || 'Failed to initialize payment. Please try again.')
      } finally {
        setLoading(false)
      }
    }

    initPayment()
  }, [formData, selectedFlight, selectedArrivalFlight, customerId, vehicleId, sessionId, promoCode])

  const handleSuccess = async (paymentIntent, reference) => {
    // Book the slot now that payment succeeded
    if (selectedFlight?.id && formData.dropoffSlot) {
      try {
        await fetch(
          `${API_BASE_URL}/api/flights/departures/${selectedFlight.id}/book-slot?slot_id=${formData.dropoffSlot}`,
          { method: 'POST' }
        )
      } catch (err) {
        console.error('Failed to book slot:', err)
      }
    }

    onPaymentSuccess?.({
      paymentIntentId: paymentIntent.id,
      bookingReference: reference,
      amount: paymentIntent.amount,
    })
  }

  const handleError = (err) => {
    onPaymentError?.(err)
  }

  if (loading) {
    return (
      <div className="stripe-loading">
        <div className="spinner"></div>
        <p>Initializing secure payment...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="stripe-error-container">
        <p className="error-message">{error}</p>
        <button
          onClick={() => window.location.reload()}
          className="retry-btn"
        >
          Try Again
        </button>
      </div>
    )
  }

  if (!clientSecret || !stripeLoaded) {
    return (
      <div className="stripe-error-container">
        <p>Unable to load payment form. Please refresh the page.</p>
      </div>
    )
  }

  const options = {
    clientSecret,
    appearance: {
      theme: 'night',
      variables: {
        colorPrimary: '#D9FF00',
        colorBackground: '#2a2a2a',
        colorText: '#ffffff',
        colorDanger: '#ff6b6b',
        fontFamily: 'Inter, system-ui, sans-serif',
        borderRadius: '8px',
      },
      rules: {
        '.Input': {
          backgroundColor: '#343434',
          border: '1px solid #555555',
        },
        '.Input:focus': {
          border: '1px solid #D9FF00',
          boxShadow: '0 0 0 1px #D9FF00',
        },
        '.Label': {
          color: '#cccccc',
        },
        '.Tab': {
          backgroundColor: '#343434',
          border: '1px solid #555555',
        },
        '.Tab--selected': {
          backgroundColor: '#D9FF00',
          color: '#000000',
        },
      },
    },
  }

  return (
    <div className="stripe-payment-container">
      <Elements stripe={stripeLoaded} options={options}>
        <CheckoutForm
          onSuccess={handleSuccess}
          onError={handleError}
          bookingReference={bookingReference}
          amount={amount}
          billingDetails={{
            name: `${formData.firstName} ${formData.lastName}`,
            email: formData.email,
            phone: formData.phone, // Already in E.164 format from react-phone-number-input
            postcode: formData.billingPostcode,
            country: getCountryCode(formData.billingCountry),
          }}
        />
      </Elements>

      <div className="stripe-security-note">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/>
        </svg>
        <span>Secure payment powered by Stripe</span>
      </div>
    </div>
  )
}

export default StripePayment
