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

// Format date as YYYY-MM-DD in local timezone (avoids UTC conversion issues)
const formatDateLocal = (date) => {
  if (!date) return ''
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

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
  const [paymentSucceeded, setPaymentSucceeded] = useState(false)
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

    // Prevent double-clicks
    if (isProcessing || paymentSucceeded) {
      console.log('Payment already in progress or succeeded, ignoring click')
      return
    }

    // Track "continue_to_payment" event when Pay button is clicked
    if (window.gtag) {
      window.gtag('event', 'continue_to_payment', {
        event_category: 'booking_flow',
        event_label: 'pay_button_click'
      })
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
        setIsProcessing(false) // Allow retry on error
        onError?.(error)
      } else if (paymentIntent && paymentIntent.status === 'succeeded') {
        console.log('Payment succeeded!')
        setPaymentSucceeded(true) // Keep button disabled permanently
        // Track "pay" event on successful payment
        if (window.gtag) {
          window.gtag('event', 'pay', {
            event_category: 'booking_flow',
            event_label: 'payment_success',
            value: paymentIntent.amount / 100
          })
        }
        onSuccess?.(paymentIntent, bookingReference)
      } else {
        // Unexpected state - allow retry
        setIsProcessing(false)
      }
    } catch (err) {
      console.error('Unexpected error:', err)
      setErrorMessage('An unexpected error occurred.')
      setIsProcessing(false) // Allow retry on error
      onError?.(err)
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
        disabled={!stripe || isProcessing || paymentSucceeded}
        className="stripe-pay-btn"
      >
        {paymentSucceeded ? 'Payment Complete' : isProcessing ? 'Processing...' : `Pay ${amount}`}
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
  promoCodeDiscount = 0,
  pricingInfo,
  onPaymentSuccess,
  onPaymentError,
}) {
  const [clientSecret, setClientSecret] = useState('')
  const [bookingReference, setBookingReference] = useState('')
  const [amount, setAmount] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [stripeLoaded, setStripeLoaded] = useState(null)
  const [isFreeBooking, setIsFreeBooking] = useState(false)
  const [originalAmount, setOriginalAmount] = useState('')
  const [discountAmount, setDiscountAmount] = useState('')
  const [isProcessingFreeBooking, setIsProcessingFreeBooking] = useState(false)

  // Calculate display amounts for free booking preview (1-week + 100% promo only)
  const calculateAmounts = () => {
    const pricePounds = pricingInfo ? pricingInfo.price : 0
    return {
      original: `£${pricePounds.toFixed(2)}`,
      discount: `£${pricePounds.toFixed(2)}`,
    }
  }

  // Create payment intent API call - extracted so it can be called on demand
  const createPaymentIntent = async () => {
    console.log('[PAYMENT] Creating payment intent with promo code:', promoCode)
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
        flight_date: formatDateLocal(formData.dropoffDate),
        drop_off_date: formatDateLocal(formData.dropoffDate),
        pickup_date: formatDateLocal(formData.pickupDate),
        drop_off_slot: formData.dropoffSlot || null,
        departure_id: selectedFlight?.id || null,
        // Return flight details (destination/origin names are looked up from flight tables on backend)
        pickup_flight_time: selectedArrivalFlight?.time || null,
        pickup_flight_number: selectedArrivalFlight?.flightNumber || null,
        // Promo code (if applied)
        promo_code: promoCode || null,
      }),
    })

    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.detail || 'Failed to initialize payment')
    }

    return await response.json()
  }

  // Track the promo code that was used to create the current payment intent
  const [initializedWithPromo, setInitializedWithPromo] = useState(undefined)

  useEffect(() => {
    const isFree = promoCodeDiscount === 100 && formData.package === 'quick'

    // For FREE bookings (1-week + 100% promo), show free booking UI
    if (isFree) {
      const amounts = calculateAmounts()
      setOriginalAmount(amounts.original)
      setDiscountAmount(amounts.discount)
      setIsFreeBooking(true)
      setLoading(false)
      setClientSecret('') // Clear any existing payment intent
      return
    }

    // Skip if we already created a payment intent with the same promo code
    if (initializedWithPromo !== undefined && initializedWithPromo === (promoCode || null)) {
      return
    }

    // For PAID bookings, load Stripe and create payment intent
    const initPayment = async () => {
      setLoading(true)
      setError('')
      setIsFreeBooking(false)

      try {
        // Load Stripe
        const stripe = await getStripe()
        if (!stripe) {
          setError('Payment system unavailable. Please try again later.')
          setLoading(false)
          return
        }
        setStripeLoaded(stripe)

        const data = await createPaymentIntent()
        setInitializedWithPromo(promoCode || null) // Track which promo was used

        // Handle response
        if (data.is_free_booking) {
          setBookingReference(data.booking_reference)
          setAmount(data.amount_display)
          setIsFreeBooking(true)
          setOriginalAmount(data.original_amount_display)
          setDiscountAmount(data.discount_amount_display)
        } else {
          setClientSecret(data.client_secret)
          setBookingReference(data.booking_reference)
          setAmount(data.amount_display)
          if (data.discount_amount_display) {
            setOriginalAmount(data.original_amount_display)
            setDiscountAmount(data.discount_amount_display)
          }
        }
      } catch (err) {
        console.error('Payment init error:', err)
        setError(err.message || 'Failed to initialize payment. Please try again.')
      } finally {
        setLoading(false)
      }
    }

    initPayment()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [promoCode, promoCodeDiscount]) // Re-run when promo code changes

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

  // Handle free booking confirmation (no Stripe needed)
  const handleFreeBookingConfirm = async () => {
    // Track "continue_to_payment" event when Confirm button is clicked
    if (window.gtag) {
      window.gtag('event', 'continue_to_payment', {
        event_category: 'booking_flow',
        event_label: 'free_booking_confirm_click'
      })
    }

    setIsProcessingFreeBooking(true)
    setError('')

    try {
      // NOW call the API to create and confirm the free booking
      const data = await createPaymentIntent()

      if (data.is_free_booking) {
        // Track "pay" event for free booking
        if (window.gtag) {
          window.gtag('event', 'pay', {
            event_category: 'booking_flow',
            event_label: 'free_booking_success',
            value: 0
          })
        }
        // Success - notify parent with booking details
        onPaymentSuccess?.({
          paymentIntentId: data.payment_intent_id,
          bookingReference: data.booking_reference,
          amount: 0,
        })
      } else {
        // Unexpected - should be free booking
        setError('Unexpected error. Please try again.')
      }
    } catch (err) {
      console.error('Free booking error:', err)
      setError(err.message || 'Failed to complete booking. Please try again.')
      onPaymentError?.(err)
    } finally {
      setIsProcessingFreeBooking(false)
    }
  }

  if (loading) {
    return (
      <div className="stripe-loading">
        <div className="spinner"></div>
        <p>{promoCode ? 'Applying promo code...' : 'Initializing secure payment...'}</p>
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

  // Free booking - show confirmation button instead of Stripe form
  if (isFreeBooking) {
    return (
      <div className="stripe-payment-container free-booking">
        <div className="free-booking-summary">
          <div className="free-booking-badge">1 WEEK FREE</div>
          <h3>Your booking is free!</h3>
          <div className="price-breakdown">
            <div className="price-row original">
              <span>Original price:</span>
              <span className="strikethrough">{originalAmount}</span>
            </div>
            <div className="price-row discount">
              <span>Promo discount:</span>
              <span className="discount-amount">-{discountAmount}</span>
            </div>
            <div className="price-row total">
              <span>Total to pay:</span>
              <span className="free-amount">£0.00</span>
            </div>
          </div>
        </div>

        {error && (
          <div className="stripe-error">
            {error}
          </div>
        )}

        <button
          type="button"
          onClick={handleFreeBookingConfirm}
          disabled={isProcessingFreeBooking}
          className="stripe-pay-btn free-booking-btn"
        >
          {isProcessingFreeBooking ? 'Processing...' : 'Complete Free Booking'}
        </button>

        <div className="stripe-security-note">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/>
          </svg>
          <span>Promo code: {promoCode}</span>
        </div>
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
