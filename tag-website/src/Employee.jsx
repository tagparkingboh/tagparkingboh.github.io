import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from './AuthContext'
import RosterCalendar from './components/RosterCalendar'
import EmployeePayroll from './components/EmployeePayroll'
import SignaturePad from './components/SignaturePad'
import './Employee.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const PHOTO_SLOTS = [
  { key: 'front', label: 'Front', required: true },
  { key: 'rear', label: 'Rear', required: true },
  { key: 'driver_side', label: 'Driver Side', required: true },
  { key: 'passenger_side', label: 'Passenger Side', required: true },
  { key: 'additional_1', label: 'Additional 1', required: false },
  { key: 'additional_2', label: 'Additional 2', required: false },
]

const REQUIRED_PHOTO_KEYS = PHOTO_SLOTS.filter(s => s.required).map(s => s.key)

// Helper to format date as dd/mm/yyyy for display
const formatDateUK = (isoDate) => {
  if (!isoDate) return ''
  const parts = isoDate.split('-')
  if (parts.length !== 3) return isoDate
  return `${parts[2]}/${parts[1]}/${parts[0]}`
}

// Helper to format an ISO datetime as HH:MM (24h) in Europe/London. Used to
// show when an inspection was first saved — drives the read-only Time field
// next to the Date input. Returns '' if the timestamp is missing/malformed.
const formatTimeUK = (isoDateTime) => {
  if (!isoDateTime) return ''
  const d = new Date(isoDateTime)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('en-GB', {
    timeZone: 'Europe/London',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

// Helper to parse UK date (dd/mm/yyyy) to ISO (yyyy-mm-dd)
const parseUKDate = (ukDate) => {
  if (!ukDate) return ''
  const parts = ukDate.split('/')
  if (parts.length !== 3) return ukDate
  return `${parts[2]}-${parts[1]}-${parts[0]}`
}

// Rotate image by 90 degrees
const rotateImage = (base64, degrees) => {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')

      // Swap width/height for 90 or 270 degree rotation
      if (degrees === 90 || degrees === 270) {
        canvas.width = img.height
        canvas.height = img.width
      } else {
        canvas.width = img.width
        canvas.height = img.height
      }

      ctx.translate(canvas.width / 2, canvas.height / 2)
      ctx.rotate((degrees * Math.PI) / 180)
      ctx.drawImage(img, -img.width / 2, -img.height / 2)

      // Get the format from the base64 string
      const format = base64.includes('image/png') ? 'image/png' : 'image/jpeg'
      resolve(canvas.toDataURL(format, 0.9))
    }
    img.src = base64
  })
}

function Employee() {
  const { user, token, loading, isAuthenticated, logout } = useAuth()
  const navigate = useNavigate()

  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [inspectionStatus, setInspectionStatus] = useState({}) // { bookingId: [lightweight status] } - NO photos
  const pendingBookingIdsRef = useRef(new Set()) // Collect booking IDs for batch fetch
  const batchFetchTimerRef = useRef(null) // Timer for debounced batch fetch
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  // Inspection modal state
  const [showInspectionModal, setShowInspectionModal] = useState(false)
  const [inspectionBooking, setInspectionBooking] = useState(null)
  const [inspectionType, setInspectionType] = useState(null) // 'dropoff' or 'pickup'
  const [editingInspection, setEditingInspection] = useState(null)
  const [inspectionNotes, setInspectionNotes] = useState('')
  const [inspectionPhotos, setInspectionPhotos] = useState({}) // { front: 'base64...', ... }
  const [customerName, setCustomerName] = useState('')
  const [signedDate, setSignedDate] = useState('')
  const [savingInspection, setSavingInspection] = useState(false)
  const [inspectionPage, setInspectionPage] = useState(1) // 1 = form, 2 = view document
  const [vehicleInspectionRead, setVehicleInspectionRead] = useState(false)
  const [acknowledgementConfirmed, setAcknowledgementConfirmed] = useState(false) // For return inspections
  const [inspectionDeclined, setInspectionDeclined] = useState(false) // Customer declined return inspection
  const [signature, setSignature] = useState(null) // base64 signature image
  const [dropoffInspection, setDropoffInspection] = useState(null) // For showing original inspection during return
  const [mileage, setMileage] = useState('') // Mileage reading at inspection

  // Complete modal state
  const [showCompleteModal, setShowCompleteModal] = useState(false)
  const [completingBooking, setCompletingBooking] = useState(null)
  const [completing, setCompleting] = useState(false)

  // Expanded image viewer state
  const [expandedImage, setExpandedImage] = useState(null) // { src: 'base64...', label: 'Front' }
  const imageViewerRef = useRef(null)

  // Draft restoration modal
  const [showDraftModal, setShowDraftModal] = useState(false)
  const [pendingDraft, setPendingDraft] = useState(null)

  // Close confirmation modal
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)

  // Camera modal state
  const [showCameraModal, setShowCameraModal] = useState(false)
  const [cameraSlotKey, setCameraSlotKey] = useState(null)
  const [cameraStream, setCameraStream] = useState(null)
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const fileInputRef = useRef(null)
  const [fileInputSlotKey, setFileInputSlotKey] = useState(null)

  // Helper to get localStorage key for inspection draft
  const getDraftKey = (bookingId, type) => `inspection_draft_${bookingId}_${type}`

  // Save inspection draft to localStorage
  const saveDraft = useCallback(() => {
    if (!inspectionBooking || !inspectionType) return
    const key = getDraftKey(inspectionBooking.id, inspectionType)
    const draft = {
      notes: inspectionNotes,
      photos: inspectionPhotos,
      customerName,
      signedDate,
      vehicleInspectionRead,
      acknowledgementConfirmed,
      signature,
      mileage,
      savedAt: new Date().toISOString(),
    }
    try {
      localStorage.setItem(key, JSON.stringify(draft))
    } catch (e) {
      // localStorage might be full - silently fail
      console.warn('Could not save draft to localStorage:', e)
    }
  }, [inspectionBooking, inspectionType, inspectionNotes, inspectionPhotos, customerName, signedDate, vehicleInspectionRead, acknowledgementConfirmed, signature, mileage])

  // Clear draft from localStorage
  const clearDraft = (bookingId, type) => {
    const key = getDraftKey(bookingId, type)
    localStorage.removeItem(key)
  }

  // Check for existing draft
  const checkForDraft = (bookingId, type) => {
    const key = getDraftKey(bookingId, type)
    try {
      const saved = localStorage.getItem(key)
      if (saved) {
        return JSON.parse(saved)
      }
    } catch (e) {
      // Corrupted data - remove it
      localStorage.removeItem(key)
    }
    return null
  }

  // Auto-save draft when inspection data changes
  useEffect(() => {
    if (showInspectionModal && inspectionBooking && !editingInspection) {
      // Only auto-save for new inspections, not when editing
      const hasData = Object.keys(inspectionPhotos).length > 0 || inspectionNotes || signature
      if (hasData) {
        saveDraft()
      }
    }
  }, [showInspectionModal, inspectionBooking, editingInspection, inspectionPhotos, inspectionNotes, signature, saveDraft])

  // Request real browser fullscreen for the image viewer so the address bar
  // hides on iPad / Samsung tablets in landscape. iPhone Safari doesn't support
  // fullscreen on non-video elements; the dvh-sized overlay is the fallback.
  useEffect(() => {
    if (!expandedImage) return
    const el = imageViewerRef.current
    if (!el) return

    const req = el.requestFullscreen || el.webkitRequestFullscreen
    if (req) {
      Promise.resolve(req.call(el)).catch(() => {})
    }

    const onFsChange = () => {
      const fsEl = document.fullscreenElement || document.webkitFullscreenElement
      if (!fsEl) setExpandedImage(null)
    }
    document.addEventListener('fullscreenchange', onFsChange)
    document.addEventListener('webkitfullscreenchange', onFsChange)

    return () => {
      document.removeEventListener('fullscreenchange', onFsChange)
      document.removeEventListener('webkitfullscreenchange', onFsChange)
      const fsEl = document.fullscreenElement || document.webkitFullscreenElement
      if (fsEl) {
        const exit = document.exitFullscreen || document.webkitExitFullscreen
        if (exit) Promise.resolve(exit.call(document)).catch(() => {})
      }
    }
  }, [expandedImage])

  // Check if there's unsaved inspection data
  const hasUnsavedData = showInspectionModal && (Object.keys(inspectionPhotos).length > 0 || inspectionNotes || signature)

  // Handle attempt to close inspection modal
  const handleCloseInspection = () => {
    if (savingInspection) return // Don't allow close while saving

    const hasData = Object.keys(inspectionPhotos).length > 0 || inspectionNotes || signature
    if (hasData && !editingInspection) {
      // Show confirmation for new inspections with data
      setShowCloseConfirm(true)
    } else {
      // Close directly for existing inspections or empty new ones
      setShowInspectionModal(false)
    }
  }

  // Confirm close and discard data
  const confirmCloseInspection = () => {
    setShowCloseConfirm(false)
    setShowInspectionModal(false)
    // Note: draft is already saved to localStorage, so user can restore later
  }

  // Warn before leaving page with unsaved inspection data (browser navigation)
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (hasUnsavedData) {
        e.preventDefault()
        e.returnValue = ''
        return ''
      }
    }

    if (hasUnsavedData) {
      window.addEventListener('beforeunload', handleBeforeUnload)
    }

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }, [hasUnsavedData])

  // Redirect if not authenticated
  useEffect(() => {
    if (!loading && !isAuthenticated) {
      navigate('/login?redirect=/employee', { replace: true })
    }
  }, [loading, isAuthenticated, navigate])

  // Cleanup batch fetch timer on unmount
  useEffect(() => {
    return () => {
      if (batchFetchTimerRef.current) {
        clearTimeout(batchFetchTimerRef.current)
      }
    }
  }, [])

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const triggerRefresh = () => setRefreshTrigger(prev => prev + 1)

  // Batch fetch lightweight inspection STATUS for multiple bookings (NO photos/signatures)
  // This is used for calendar display to show if inspections exist
  const fetchInspectionStatusBatch = useCallback(async (bookingIds) => {
    if (!bookingIds || bookingIds.length === 0) return

    try {
      const response = await fetch(`${API_URL}/api/employee/inspections/status`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ booking_ids: bookingIds }),
      })
      if (response.ok) {
        const data = await response.json()
        // Merge batch results into state
        setInspectionStatus(prev => ({
          ...prev,
          ...Object.fromEntries(
            Object.entries(data.inspections || {}).map(([id, insp]) => [parseInt(id), insp])
          )
        }))
      }
    } catch (err) {
      // Silently fail - inspections just won't show status
      console.warn('Failed to fetch inspection status batch:', err)
    }
  }, [token])

  // Queue a booking ID for batch status fetching (called when rendering booking actions)
  const queueInspectionStatusFetch = useCallback((bookingId) => {
    // Skip if we already have status for this booking
    if (inspectionStatus[bookingId] !== undefined) return

    // Add to pending set
    pendingBookingIdsRef.current.add(bookingId)

    // Debounce: wait 100ms for more booking IDs to accumulate, then batch fetch
    if (batchFetchTimerRef.current) {
      clearTimeout(batchFetchTimerRef.current)
    }
    batchFetchTimerRef.current = setTimeout(() => {
      const ids = Array.from(pendingBookingIdsRef.current)
      pendingBookingIdsRef.current.clear()
      if (ids.length > 0) {
        fetchInspectionStatusBatch(ids)
      }
    }, 100)
  }, [inspectionStatus, fetchInspectionStatusBatch])

  // Fetch FULL inspection data for a single booking (used when opening modal or after saving)
  // This includes photos and signatures - only called when needed
  const fetchFullInspection = useCallback(async (bookingId) => {
    try {
      const response = await fetch(`${API_URL}/api/employee/inspections/${bookingId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        return data.inspections || []
      }
    } catch (err) {
      console.warn('Failed to fetch full inspection:', err)
    }
    return []
  }, [token])

  // Update inspection status after saving (lightweight refresh)
  const refreshInspectionStatus = useCallback(async (bookingId) => {
    try {
      const response = await fetch(`${API_URL}/api/employee/inspections/status`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ booking_ids: [bookingId] }),
      })
      if (response.ok) {
        const data = await response.json()
        setInspectionStatus(prev => ({
          ...prev,
          [bookingId]: data.inspections?.[String(bookingId)] || []
        }))
      }
    } catch (err) {
      // Silently fail
    }
  }, [token])

  // Restore draft data
  const restoreDraft = (draft) => {
    setInspectionNotes(draft.notes || '')
    setInspectionPhotos(draft.photos || {})
    setCustomerName(draft.customerName || '')
    setSignedDate(draft.signedDate || new Date().toISOString().split('T')[0])
    setVehicleInspectionRead(draft.vehicleInspectionRead || false)
    setAcknowledgementConfirmed(draft.acknowledgementConfirmed || false)
    setSignature(draft.signature || null)
    setMileage(draft.mileage || '')
    setShowDraftModal(false)
    setPendingDraft(null)
    setInspectionPage(1)
    setShowInspectionModal(true)
  }

  // Discard draft and start fresh
  const discardDraft = () => {
    if (pendingDraft && inspectionBooking) {
      clearDraft(inspectionBooking.id, inspectionType)
    }
    setInspectionNotes('')
    setInspectionPhotos({})
    setCustomerName('')
    setSignedDate(new Date().toISOString().split('T')[0])
    setVehicleInspectionRead(false)
    setAcknowledgementConfirmed(false)
    setSignature(null)
    setMileage('')
    setShowDraftModal(false)
    setPendingDraft(null)
    setInspectionPage(1)
    setShowInspectionModal(true)
  }

  // Open inspection modal - fetches full inspection data (with photos) only when needed
  const openInspection = async (booking, type) => {
    // Check lightweight status to see if inspection exists
    const statusList = inspectionStatus[booking.id] || []
    const existingStatus = statusList.find(i => i.inspection_type === type)

    setInspectionBooking(booking)
    setInspectionType(type)

    if (existingStatus) {
      // Existing inspection - fetch FULL data including photos
      const fullInspections = await fetchFullInspection(booking.id)
      const existing = fullInspections.find(i => i.inspection_type === type)

      // For return/pickup inspections, find the original drop-off inspection for comparison
      if (type === 'pickup') {
        const originalDropoff = fullInspections.find(i => i.inspection_type === 'dropoff')
        setDropoffInspection(originalDropoff || null)
      } else {
        setDropoffInspection(null)
      }

      if (existing) {
        // Editing existing inspection - load from database
        setEditingInspection(existing)
        setInspectionNotes(existing.notes || '')
        // Handle both old array format and new object format
        const photos = existing.photos || {}
        setInspectionPhotos(Array.isArray(photos) ? {} : photos)
        setCustomerName(existing.customer_name || '')
        setSignedDate(existing.signed_date || '')
        setVehicleInspectionRead(existing.vehicle_inspection_read || false)
        setAcknowledgementConfirmed(existing.acknowledgement_confirmed || false)
        setInspectionDeclined(existing.declined || false)
        setSignature(existing.signature || null)
        setMileage(existing.mileage?.toString() || '')
        setInspectionPage(1)
        setShowInspectionModal(true)
      }
    } else {
      // New inspection - fetch dropoff data if this is a return inspection
      if (type === 'pickup') {
        const fullInspections = await fetchFullInspection(booking.id)
        const originalDropoff = fullInspections.find(i => i.inspection_type === 'dropoff')
        setDropoffInspection(originalDropoff || null)
      } else {
        setDropoffInspection(null)
      }

      // Check for draft
      setEditingInspection(null)
      const draft = checkForDraft(booking.id, type)
      if (draft && (Object.keys(draft.photos || {}).length > 0 || draft.notes || draft.signature)) {
        // Found draft with data - ask user
        setPendingDraft(draft)
        setShowDraftModal(true)
      } else {
        // No draft - start fresh
        setInspectionNotes('')
        setInspectionPhotos({})
        setCustomerName('')
        setSignedDate(new Date().toISOString().split('T')[0])
        setVehicleInspectionRead(false)
        setAcknowledgementConfirmed(false)
        setInspectionDeclined(false)
        setSignature(null)
        setMileage('')
        setInspectionPage(1)
        setShowInspectionModal(true)
      }
    }
  }

  // Handle photo capture for a specific slot
  const handlePhotoCapture = (slotKey, e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onloadend = () => {
      setInspectionPhotos(prev => ({ ...prev, [slotKey]: reader.result }))
    }
    reader.readAsDataURL(file)
    e.target.value = '' // Reset input so same slot can retake
  }

  const removePhoto = (slotKey) => {
    setInspectionPhotos(prev => {
      const updated = { ...prev }
      delete updated[slotKey]
      return updated
    })
  }

  // Handle photo rotation
  const handleRotatePhoto = async (slotKey, degrees) => {
    const currentPhoto = inspectionPhotos[slotKey]
    if (!currentPhoto) return
    const rotatedPhoto = await rotateImage(currentPhoto, degrees)
    setInspectionPhotos(prev => ({ ...prev, [slotKey]: rotatedPhoto }))
  }

  // Open camera modal with back camera
  const openCamera = async (slotKey) => {
    setCameraSlotKey(slotKey)
    setShowCameraModal(true)

    try {
      // Try to get back camera first with exact constraint
      let stream
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { exact: 'environment' } },
          audio: false
        })
      } catch (exactError) {
        // Fallback: try with ideal constraint (less strict)
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: 'environment' } },
            audio: false
          })
        } catch (idealError) {
          // Last fallback: just get any camera
          stream = await navigator.mediaDevices.getUserMedia({
            video: true,
            audio: false
          })
        }
      }

      setCameraStream(stream)
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        videoRef.current.play()
      }
    } catch (err) {
      console.error('Failed to access camera:', err)
      setError('Failed to access camera. Please check permissions.')
      closeCamera()
    }
  }

  // Capture photo from camera stream
  const captureFromCamera = () => {
    if (!videoRef.current || !canvasRef.current) return

    const video = videoRef.current
    const canvas = canvasRef.current
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight

    const ctx = canvas.getContext('2d')
    ctx.drawImage(video, 0, 0)

    const photoData = canvas.toDataURL('image/jpeg', 0.8)
    setInspectionPhotos(prev => ({ ...prev, [cameraSlotKey]: photoData }))
    closeCamera()
  }

  // Close camera modal and stop stream
  const closeCamera = () => {
    if (cameraStream) {
      cameraStream.getTracks().forEach(track => track.stop())
      setCameraStream(null)
    }
    setShowCameraModal(false)
    setCameraSlotKey(null)
  }

  // Open file picker for user ID 1 (laptop/desktop use)
  const openFilePicker = (slotKey) => {
    setFileInputSlotKey(slotKey)
    if (fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  // Handle file selection from local storage
  const handleFileSelect = (event) => {
    const file = event.target.files?.[0]
    if (!file || !fileInputSlotKey) return

    const reader = new FileReader()
    reader.onload = (e) => {
      const base64 = e.target.result
      setInspectionPhotos(prev => ({ ...prev, [fileInputSlotKey]: base64 }))
      setFileInputSlotKey(null)
    }
    reader.readAsDataURL(file)

    // Reset file input so same file can be selected again
    event.target.value = ''
  }

  // Check if user can use file upload (user ID 1)
  const canUseFileUpload = user?.id === 1

  // Save inspection
  const handleSaveInspection = async () => {
    // Validate required photos - only for drop-off inspections
    if (inspectionType === 'dropoff') {
      const missingPhotos = REQUIRED_PHOTO_KEYS.filter(key => !inspectionPhotos[key])
      if (missingPhotos.length > 0) {
        const labels = missingPhotos.map(key => PHOTO_SLOTS.find(s => s.key === key)?.label)
        setError(`Required photos missing: ${labels.join(', ')}`)
        return
      }
    }

    setSavingInspection(true)
    setError('')
    try {
      const url = editingInspection
        ? `${API_URL}/api/employee/inspections/${editingInspection.id}`
        : `${API_URL}/api/employee/inspections`
      const method = editingInspection ? 'PUT' : 'POST'
      const body = editingInspection
        ? { notes: inspectionNotes, photos: inspectionPhotos, customer_name: customerName, signed_date: signedDate, signature: signature, vehicle_inspection_read: vehicleInspectionRead, acknowledgement_confirmed: acknowledgementConfirmed, declined: inspectionDeclined, mileage: mileage ? parseInt(mileage, 10) : null }
        : { booking_id: inspectionBooking.id, inspection_type: inspectionType, notes: inspectionNotes, photos: inspectionPhotos, customer_name: customerName, signed_date: signedDate, signature: signature, vehicle_inspection_read: vehicleInspectionRead, acknowledgement_confirmed: acknowledgementConfirmed, declined: inspectionDeclined, mileage: mileage ? parseInt(mileage, 10) : null }

      const response = await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      })
      if (response.ok) {
        // Clear draft from localStorage on successful save
        clearDraft(inspectionBooking.id, inspectionType)
        setShowInspectionModal(false)
        setSuccessMessage(`${inspectionType === 'dropoff' ? 'Drop-off' : 'Return'} inspection saved`)
        setTimeout(() => setSuccessMessage(''), 3000)
        refreshInspectionStatus(inspectionBooking.id)
      } else if (response.status === 409) {
        // Another employee created this inspection simultaneously - close modal and refresh
        const data = await response.json()
        clearDraft(inspectionBooking.id, inspectionType)
        setShowInspectionModal(false)
        setError(data.detail || 'Another employee already created this inspection')
        setTimeout(() => setError(''), 5000)
        refreshInspectionStatus(inspectionBooking.id)
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to save inspection')
        setTimeout(() => setError(''), 5000)
      }
    } catch (err) {
      setError('Network error saving inspection')
      setTimeout(() => setError(''), 5000)
    } finally {
      setSavingInspection(false)
    }
  }

  // Complete booking
  const handleCompleteBooking = async () => {
    if (!completingBooking) return
    setCompleting(true)
    try {
      const response = await fetch(`${API_URL}/api/employee/bookings/${completingBooking.id}/complete`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setShowCompleteModal(false)
        setCompletingBooking(null)
        setSuccessMessage(`Booking ${completingBooking.reference} marked as completed`)
        setTimeout(() => setSuccessMessage(''), 3000)
        triggerRefresh()
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to complete booking')
        setTimeout(() => setError(''), 5000)
      }
    } catch (err) {
      setError('Network error completing booking')
      setTimeout(() => setError(''), 5000)
    } finally {
      setCompleting(false)
    }
  }

  // Render action buttons for each booking in the calendar
  const renderBookingActions = useCallback((booking, type) => {
    // Queue this booking for batch status fetch (batches multiple bookings into one API call)
    // Only fetches lightweight status (no photos) for calendar display
    if (inspectionStatus[booking.id] === undefined) {
      queueInspectionStatusFetch(booking.id)
    }

    const bookingInspections = inspectionStatus[booking.id] || []
    const hasInspection = bookingInspections.some(i => i.inspection_type === type)
    const isCompleted = booking.status === 'completed'

    if (type === 'dropoff') {
      return (
        <div className="booking-actions-row">
          <button
            className={`inspection-btn ${hasInspection ? 'inspection-done' : ''}`}
            onClick={(e) => { e.stopPropagation(); openInspection(booking, 'dropoff') }}
          >
            {hasInspection ? 'View/Edit Inspection' : 'Vehicle Inspection'}
          </button>
        </div>
      )
    }

    if (type === 'pickup') {
      const pickupInspection = bookingInspections.find(i => i.inspection_type === 'pickup')
      // Can complete if we have a pickup inspection (either full inspection or declined)
      const canComplete = !!pickupInspection

      return (
        <div className="booking-actions-row">
          <button
            className={`inspection-btn ${hasInspection ? 'inspection-done' : ''}`}
            onClick={(e) => { e.stopPropagation(); openInspection(booking, 'pickup') }}
          >
            {hasInspection ? (pickupInspection?.declined ? 'View Declined' : 'View/Edit Inspection') : 'Return Inspection'}
          </button>
          {isCompleted ? (
            <span className="completed-badge">Completed</span>
          ) : (
            <button
              className={`complete-btn ${!canComplete ? 'complete-btn-disabled' : ''}`}
              onClick={(e) => { e.stopPropagation(); setCompletingBooking(booking); setShowCompleteModal(true) }}
              disabled={!canComplete}
              title={!canComplete ? 'Complete the Return Inspection first' : ''}
            >
              Complete Booking
            </button>
          )}
        </div>
      )
    }

    return null
  }, [inspectionStatus, queueInspectionStatusFetch])

  if (loading) {
    return (
      <div className="employee-loading">
        <div className="spinner"></div>
        <p>Loading...</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <div className="employee-container">
      <header className="employee-header">
        <div className="employee-header-left">
          <Link to="/">
            <img src="/assets/logo.svg" alt="TAG Parking" className="employee-logo" />
          </Link>
          <h1>Employee Portal</h1>
        </div>
        <div className="employee-header-right">
          <span className="employee-user">
            {user?.first_name} {user?.last_name}
          </span>
          <button onClick={handleLogout} className="employee-logout">
            Logout
          </button>
        </div>
      </header>

      <main className="employee-content">
        {successMessage && <div className="employee-success">{successMessage}</div>}
        {error && <div className="employee-error">{error}</div>}

        <RosterCalendar
          token={token}
          isAdmin={false}
          refreshTrigger={refreshTrigger}
          renderBookingActions={renderBookingActions}
        />

        <EmployeePayroll token={token} />
      </main>

      {/* Inspection Modal */}
      {showInspectionModal && inspectionBooking && (
        <div className="modal-overlay" onClick={handleCloseInspection}>
          <div className="modal-content inspection-modal" onClick={e => e.stopPropagation()}>

            {/* Saving Overlay */}
            {savingInspection && (
              <div className="saving-overlay">
                <div className="saving-spinner"></div>
                <p>Saving inspection...</p>
                <p className="saving-subtext">Please wait, this may take a moment</p>
              </div>
            )}

            {/* Page 1: Inspection Form */}
            {inspectionPage === 1 && (
              <>
                <h3>{editingInspection ? 'Edit' : 'New'} {inspectionType === 'dropoff' ? 'Drop-off' : 'Return'} Inspection</h3>
                <div className="inspection-booking-info">
                  <span className="inspection-ref">{inspectionBooking.reference}</span>
                  <span>{inspectionBooking.customer?.first_name || inspectionBooking.customer_first_name} {inspectionBooking.customer?.last_name || inspectionBooking.customer_last_name}</span>
                  <span>{inspectionBooking.vehicle?.registration || inspectionBooking.vehicle_registration}</span>
                </div>

                {/* Show original drop-off inspection for return inspections */}
                {inspectionType === 'pickup' && dropoffInspection && (
                  <div className="dropoff-inspection-summary">
                    <h4>Original Drop-off Inspection</h4>
                    <p className="dropoff-summary-date">
                      Recorded on {formatDateUK(dropoffInspection.signed_date) || 'N/A'}
                    </p>
                    {dropoffInspection.notes && (
                      <div className="dropoff-summary-notes">
                        <strong>Notes:</strong>
                        <p>{dropoffInspection.notes}</p>
                      </div>
                    )}
                    {dropoffInspection.photos && Object.keys(dropoffInspection.photos).length > 0 && (
                      <div className="dropoff-summary-photos">
                        <strong>Photos from drop-off:</strong>
                        <div className="dropoff-photos-grid">
                          {Object.entries(dropoffInspection.photos).map(([key, src]) => (
                            <div key={key} className="dropoff-photo-item">
                              <img
                                src={src}
                                alt={key}
                                onClick={() => setExpandedImage({ src, label: `Drop-off: ${key}` })}
                                className="dropoff-photo-thumb"
                              />
                              <span className="dropoff-photo-label">{key.replace('_', ' ')}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {!dropoffInspection.notes && (!dropoffInspection.photos || Object.keys(dropoffInspection.photos).length === 0) && (
                      <p className="dropoff-summary-empty">No damage or notes recorded at drop-off.</p>
                    )}
                  </div>
                )}

                {inspectionType === 'pickup' && !dropoffInspection && (
                  <div className="dropoff-inspection-summary dropoff-inspection-missing">
                    <h4>Original Drop-off Inspection</h4>
                    <p>No drop-off inspection was recorded for this booking.</p>
                  </div>
                )}

                <div className="inspection-form">
                  {/* For return inspections, show dropoff mileage as read-only */}
                  {inspectionType === 'pickup' && dropoffInspection?.mileage && (
                    <div className="inspection-field">
                      <label>Mileage at Drop-off</label>
                      <input
                        type="text"
                        value={dropoffInspection.mileage.toLocaleString()}
                        className="mileage-input mileage-readonly"
                        readOnly
                        disabled
                      />
                    </div>
                  )}

                  <div className="inspection-field">
                    <label>{inspectionType === 'pickup' ? 'Mileage at Return' : 'Mileage'} <span className="required">*</span></label>
                    <input
                      type="number"
                      value={mileage}
                      onChange={e => setMileage(e.target.value)}
                      placeholder={inspectionType === 'pickup' ? 'Enter return mileage' : 'Enter current mileage'}
                      className="mileage-input"
                      min="0"
                    />
                  </div>

                  {/* Customer Declined Inspection - only for return/pickup inspections */}
                  {inspectionType === 'pickup' && (
                    <div className="inspection-declined-checkbox">
                      <label className="checkbox-label-inline declined-label">
                        <input
                          type="checkbox"
                          checked={inspectionDeclined}
                          onChange={e => setInspectionDeclined(e.target.checked)}
                        />
                        <span>Customer Declined Inspection</span>
                      </label>
                      {inspectionDeclined && (
                        <p className="declined-note">Customer signature and acknowledgement are not required. You can still record mileage, take photos, and add notes.</p>
                      )}
                    </div>
                  )}

                  <div className="inspection-field">
                    <label>Notes</label>
                    <textarea
                      value={inspectionNotes}
                      onChange={e => setInspectionNotes(e.target.value)}
                      placeholder="Add inspection notes..."
                      rows={4}
                    />
                  </div>

                  <div className="inspection-field">
                    <label>Vehicle Photos {inspectionType === 'pickup' && <span className="optional">(optional)</span>}</label>
                    <div className="photo-slots-grid">
                      {PHOTO_SLOTS.map(slot => {
                        // For return inspections, all photos are optional
                        const isRequired = inspectionType === 'dropoff' && slot.required
                        return (
                        <div key={slot.key} className={`photo-slot ${isRequired && !inspectionPhotos[slot.key] ? 'photo-slot-required' : ''}`}>
                          <span className="photo-slot-label">
                            {slot.label} {isRequired ? <span className="required">*</span> : <span className="optional">(optional)</span>}
                          </span>
                          {inspectionPhotos[slot.key] ? (
                            <div className="photo-slot-preview">
                              <img
                                src={inspectionPhotos[slot.key]}
                                alt={slot.label}
                                onClick={() => setExpandedImage({ src: inspectionPhotos[slot.key], label: slot.label })}
                                className="photo-slot-img-clickable"
                              />
                              <div className="photo-slot-actions">
                                <button
                                  className="photo-slot-rotate"
                                  onClick={() => handleRotatePhoto(slot.key, 270)}
                                  title="Rotate left"
                                >
                                  ↺
                                </button>
                                <button
                                  className="photo-slot-rotate"
                                  onClick={() => handleRotatePhoto(slot.key, 90)}
                                  title="Rotate right"
                                >
                                  ↻
                                </button>
                                <button
                                  className="photo-slot-retake"
                                  onClick={() => removePhoto(slot.key)}
                                >
                                  Retake
                                </button>
                              </div>
                            </div>
                          ) : canUseFileUpload ? (
                            <div className="photo-slot-options">
                              <button className="photo-slot-capture" onClick={() => openCamera(slot.key)}>
                                <span className="photo-slot-icon">&#128247;</span>
                                <span>Camera</span>
                              </button>
                              <button className="photo-slot-capture photo-slot-upload" onClick={() => openFilePicker(slot.key)}>
                                <span className="photo-slot-icon">&#128193;</span>
                                <span>Upload</span>
                              </button>
                            </div>
                          ) : (
                            <button className="photo-slot-capture" onClick={() => openCamera(slot.key)}>
                              <span className="photo-slot-icon">&#128247;</span>
                              <span>Tap to capture</span>
                            </button>
                          )}
                        </div>
                      )})}
                    </div>
                  </div>
                </div>

                {/* Customer Acknowledgement - hidden when inspection is declined */}
                {!(inspectionType === 'pickup' && inspectionDeclined) && (
                  <div className="inspection-acknowledgement">
                    <h4>Customer Acknowledgement</h4>

                    {/* Vehicle Inspection Read Checkbox - Only for drop-off */}
                    {inspectionType === 'dropoff' && (
                      <div className="vehicle-inspection-checkbox">
                        <label className="checkbox-label-inline">
                          <input
                            type="checkbox"
                            checked={vehicleInspectionRead}
                            onChange={e => setVehicleInspectionRead(e.target.checked)}
                          />
                          <span>I have read the </span>
                          <button
                            type="button"
                            className="view-document-link"
                            onClick={() => setInspectionPage(2)}
                          >
                            Vehicle Inspection Terms
                          </button>
                        </label>
                      </div>
                    )}

                    {/* Acknowledgement text for drop-off (already covered by T&C checkbox above) */}
                    {inspectionType === 'dropoff' && (
                      <p className="acknowledgement-text">
                        I confirm that I have reviewed the vehicle condition and agree with the inspection findings.
                      </p>
                    )}

                    {/* Acknowledgement checkbox for return inspections */}
                    {inspectionType === 'pickup' && (
                      <div className="vehicle-inspection-checkbox">
                        <label className="checkbox-label-inline">
                          <input
                            type="checkbox"
                            checked={acknowledgementConfirmed}
                            onChange={e => setAcknowledgementConfirmed(e.target.checked)}
                          />
                          <span>I confirm that my vehicle has been returned to me and I am satisfied with its condition.</span>
                        </label>
                      </div>
                    )}

                    <div className="acknowledgement-fields">
                      <div className="inspection-field">
                        <label>Customer Name</label>
                        <input
                          type="text"
                          value={customerName}
                          onChange={e => setCustomerName(e.target.value)}
                          placeholder="Enter full name"
                          className="acknowledgement-input"
                        />
                      </div>
                      <div className="inspection-field">
                        <label>Date (dd/mm/yyyy)</label>
                        <input
                          type="text"
                          value={formatDateUK(signedDate)}
                          onChange={e => {
                            const ukDate = e.target.value
                            // Allow typing with auto-formatting
                            const digits = ukDate.replace(/\D/g, '')
                            let formatted = ''
                            if (digits.length <= 2) formatted = digits
                            else if (digits.length <= 4) formatted = digits.slice(0, 2) + '/' + digits.slice(2)
                            else formatted = digits.slice(0, 2) + '/' + digits.slice(2, 4) + '/' + digits.slice(4, 8)
                            // Convert to ISO format for storage
                            if (formatted.length === 10) {
                              setSignedDate(parseUKDate(formatted))
                            } else {
                              // Store partial input in UK format temporarily
                              setSignedDate(parseUKDate(formatted))
                            }
                          }}
                          placeholder="dd/mm/yyyy"
                          maxLength={10}
                          className="acknowledgement-input"
                        />
                      </div>
                      <div className="inspection-field">
                        <label>Time (24h UK)</label>
                        <input
                          type="text"
                          value={formatTimeUK(editingInspection?.created_at)}
                          readOnly
                          placeholder="—"
                          className="acknowledgement-input"
                          title="When this inspection was first saved (server-recorded, Europe/London)"
                        />
                      </div>
                    </div>

                    {/* Signature Pad */}
                    <div className="inspection-field signature-field">
                      <label>Customer Signature <span className="required">*</span></label>
                      <SignaturePad
                        onSignatureChange={setSignature}
                        initialSignature={signature}
                      />
                    </div>
                  </div>
                )}

                <div className="modal-actions">
                  <button
                    className="modal-btn modal-btn-secondary"
                    onClick={handleCloseInspection}
                    disabled={savingInspection}
                  >
                    Cancel
                  </button>
                  <button
                    className="modal-btn modal-btn-primary"
                    onClick={handleSaveInspection}
                    disabled={savingInspection || !mileage || (inspectionType === 'dropoff' && (!signature || !vehicleInspectionRead || !signedDate || !customerName)) || (inspectionType === 'pickup' && !inspectionDeclined && (!signature || !acknowledgementConfirmed || !signedDate || !customerName))}
                  >
                    {savingInspection ? 'Saving...' : 'Save Inspection'}
                  </button>
                </div>
              </>
            )}

            {/* Page 2: Vehicle Inspection Document */}
            {inspectionPage === 2 && (
              <>
                <div className="inspection-document-header">
                  <button
                    type="button"
                    className="back-to-form-btn"
                    onClick={() => setInspectionPage(1)}
                  >
                    &larr; Back to Inspection
                  </button>
                  <h3>Vehicle Inspection Terms</h3>
                </div>

                <div className="inspection-document-content">
                  <div className="document-logo">
                    <img src="/assets/logo.svg" alt="TAG" />
                  </div>

                  <h2>Meet & Greet Vehicle Inspection – Terms & Conditions</h2>

                  <p className="document-intro">
                    These Terms & Conditions apply to meet and greet vehicle inspection services (the "Services") provided by TAG Parking ("we", "us") to the customer ("you"). By booking our Services, you agree to these terms.
                  </p>

                  <h4>1. Scope of Services</h4>
                  <p>1.1 We provide a visual, non-invasive inspection of a vehicle at an agreed location and time.</p>
                  <p>1.2 Inspections are limited to externally observable conditions only at the time of inspection.</p>
                  <p>1.3 The inspection is not a mechanical, diagnostic, roadworthiness, or safety test.</p>

                  <h4>2. What the Inspection Includes</h4>
                  <ul>
                    <li>Exterior condition (bodywork, paint, glass, lights, tyres).</li>
                    <li>Visual checks of easily accessible items only.</li>
                    <li>Photographs and/or a brief written summary where included in your booking.</li>
                  </ul>

                  <h4>3. What the Inspection Does Not Include</h4>
                  <ul>
                    <li>Interior inspection or assessment.</li>
                    <li>Under-bonnet, engine, gearbox, electrical, or electronic inspection.</li>
                    <li>Hidden, latent, intermittent, or future faults.</li>
                    <li>Valuation, price negotiation, or legal advice.</li>
                    <li>MOT, safety certification, or warranty validation.</li>
                  </ul>

                  <h4>4. Customer Responsibilities</h4>
                  <p>4.1 You must ensure the vehicle is accessible, safe to inspect, and available at the agreed time.</p>
                  <p>4.2 You are responsible for obtaining permission from the vehicle owner or seller.</p>
                  <p>4.3 Any delays or access issues may limit the inspection or result in cancellation.</p>

                  <h4>5. Fees, Cancellations & Refunds</h4>
                  <p>5.1 Fees are as agreed at booking and payable in advance unless otherwise stated.</p>
                  <p>5.2 Cancellations made 24 hours before the appointment may be refunded or rescheduled.</p>
                  <p>5.3 Late cancellations or no-shows may be charged in full.</p>
                  <p>5.4 Fees are non-refundable once the inspection has started.</p>

                  <h4>6. Reports & Reliance</h4>
                  <p>6.1 Any feedback or report is provided for your personal use only.</p>
                  <p>6.2 Reports reflect our opinion based on a visual inspection at a single point in time.</p>
                  <p>6.3 Vehicles may develop faults after inspection for which we are not responsible.</p>

                  <h4>7. Limitation of Liability</h4>
                  <p>7.1 To the maximum extent permitted by law, we are not liable for indirect or consequential loss, or for defects outside the stated scope.</p>
                  <p>7.2 Our total liability is limited to the fee paid for the Services.</p>

                  <h4>8. Health & Safety</h4>
                  <p>8.1 We may refuse or stop an inspection if conditions are unsafe.</p>
                  <p>8.2 We accept no responsibility for hazards at the inspection location.</p>

                  <h4>9. Data & Intellectual Property</h4>
                  <p>9.1 Inspection reports and photographs remain our intellectual property.</p>
                  <p>9.2 Personal data will be handled in accordance with applicable data protection laws.</p>

                  <h4>10. Governing Law</h4>
                  <p>10.1 These Terms & Conditions are governed by the laws of England & Wales.</p>

                  <div className="document-footer">
                    <p><strong>Business Name:</strong> TAG Parking</p>
                    <p><strong>Contact:</strong> info@tagparking.co.uk</p>
                  </div>
                </div>

                <div className="modal-actions">
                  <button
                    className="modal-btn modal-btn-primary"
                    onClick={() => setInspectionPage(1)}
                  >
                    Back to Inspection
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Complete Booking Modal */}
      {showCompleteModal && completingBooking && (
        <div className="modal-overlay" onClick={() => setShowCompleteModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h3>Complete Booking</h3>
            <p>Mark booking <strong>{completingBooking.reference}</strong> as completed?</p>
            <p className="modal-subtext">
              {completingBooking.customer?.first_name || completingBooking.customer_first_name} {completingBooking.customer?.last_name || completingBooking.customer_last_name} — {completingBooking.vehicle?.registration || completingBooking.vehicle_registration}
            </p>
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setShowCompleteModal(false)}>Cancel</button>
              <button className="modal-btn modal-btn-success" onClick={handleCompleteBooking} disabled={completing}>
                {completing ? 'Completing...' : 'Confirm Complete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Draft Restoration Modal */}
      {showDraftModal && pendingDraft && (
        <div className="modal-overlay">
          <div className="modal-content draft-modal" onClick={e => e.stopPropagation()}>
            <h3>Restore Previous Work?</h3>
            <p>You have an unsaved inspection from earlier.</p>
            <div className="draft-info">
              <p><strong>Photos:</strong> {Object.keys(pendingDraft.photos || {}).length} captured</p>
              {pendingDraft.notes && <p><strong>Notes:</strong> {pendingDraft.notes.substring(0, 50)}{pendingDraft.notes.length > 50 ? '...' : ''}</p>}
              <p className="draft-time">Saved: {new Date(pendingDraft.savedAt).toLocaleString()}</p>
            </div>
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={discardDraft}>
                Start Fresh
              </button>
              <button className="modal-btn modal-btn-primary" onClick={() => restoreDraft(pendingDraft)}>
                Restore
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Camera Modal */}
      {showCameraModal && (
        <div className="camera-modal-overlay">
          <div className="camera-modal">
            <div className="camera-header">
              <span>Take Photo: {PHOTO_SLOTS.find(s => s.key === cameraSlotKey)?.label}</span>
              <button className="camera-close" onClick={closeCamera}>&times;</button>
            </div>
            <div className="camera-viewfinder">
              <video ref={videoRef} autoPlay playsInline muted className="camera-video" />
              <canvas ref={canvasRef} style={{ display: 'none' }} />
            </div>
            <div className="camera-controls">
              <button className="camera-capture-btn" onClick={captureFromCamera}>
                <span className="camera-capture-icon"></span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Close Confirmation Modal */}
      {showCloseConfirm && (
        <div className="modal-overlay">
          <div className="modal-content draft-modal" onClick={e => e.stopPropagation()}>
            <h3>Discard Inspection?</h3>
            <p>You have unsaved photos and data. Are you sure you want to close?</p>
            <p className="draft-time">Your progress has been saved as a draft and can be restored later.</p>
            <div className="modal-actions">
              <button className="modal-btn modal-btn-secondary" onClick={() => setShowCloseConfirm(false)}>
                Continue Editing
              </button>
              <button className="modal-btn modal-btn-danger" onClick={confirmCloseInspection}>
                Discard & Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Fullscreen Image Viewer */}
      {expandedImage && (
        <div className="image-viewer-overlay" ref={imageViewerRef} onClick={() => setExpandedImage(null)}>
          <button className="image-viewer-close" onClick={() => setExpandedImage(null)}>
            &times;
          </button>
          <div className="image-viewer-label">{expandedImage.label}</div>
          <img
            src={expandedImage.src}
            alt={expandedImage.label}
            className="image-viewer-img"
            onClick={e => e.stopPropagation()}
          />
        </div>
      )}

      {/* Hidden file input for local storage uploads (user ID 1 only) */}
      <input
        type="file"
        ref={fileInputRef}
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleFileSelect}
      />
    </div>
  )
}

export default Employee
