import { useRef, useEffect, useState } from 'react'

/**
 * SignaturePad component for capturing handwritten signatures on iPad/touch devices.
 * Uses HTML5 Canvas with touch and mouse support.
 */
function SignaturePad({ onSignatureChange, initialSignature = null, disabled = false }) {
  const canvasRef = useRef(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [hasSignature, setHasSignature] = useState(false)

  // Initialize canvas and load existing signature if provided
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')

    // Set canvas size to match display size
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * 2 // Higher resolution for retina
    canvas.height = rect.height * 2
    ctx.scale(2, 2)

    // Set drawing styles
    ctx.strokeStyle = '#000'
    ctx.lineWidth = 2
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    // Fill with white background
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, rect.width, rect.height)

    // Load existing signature if provided
    if (initialSignature) {
      const img = new Image()
      img.onload = () => {
        ctx.drawImage(img, 0, 0, rect.width, rect.height)
        setHasSignature(true)
      }
      img.src = initialSignature
    }
  }, [initialSignature])

  const getCoordinates = (e) => {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()

    if (e.touches && e.touches.length > 0) {
      return {
        x: e.touches[0].clientX - rect.left,
        y: e.touches[0].clientY - rect.top
      }
    }
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    }
  }

  const startDrawing = (e) => {
    if (disabled) return
    e.preventDefault()

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const { x, y } = getCoordinates(e)

    ctx.beginPath()
    ctx.moveTo(x, y)
    setIsDrawing(true)
  }

  const draw = (e) => {
    if (!isDrawing || disabled) return
    e.preventDefault()

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const { x, y } = getCoordinates(e)

    ctx.lineTo(x, y)
    ctx.stroke()
    setHasSignature(true)
  }

  const stopDrawing = (e) => {
    if (!isDrawing) return
    e?.preventDefault()

    setIsDrawing(false)

    // Save signature as base64
    const canvas = canvasRef.current
    if (canvas && hasSignature) {
      const dataUrl = canvas.toDataURL('image/png')
      onSignatureChange?.(dataUrl)
    }
  }

  const clearSignature = () => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    const rect = canvas.getBoundingClientRect()

    // Clear and fill with white
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, rect.width, rect.height)

    setHasSignature(false)
    onSignatureChange?.(null)
  }

  return (
    <div className="signature-pad-container">
      <canvas
        ref={canvasRef}
        className={`signature-pad-canvas ${disabled ? 'disabled' : ''}`}
        onMouseDown={startDrawing}
        onMouseMove={draw}
        onMouseUp={stopDrawing}
        onMouseLeave={stopDrawing}
        onTouchStart={startDrawing}
        onTouchMove={draw}
        onTouchEnd={stopDrawing}
      />
      <div className="signature-pad-actions">
        <span className="signature-pad-hint">Sign above using finger or stylus</span>
        <button
          type="button"
          className="signature-pad-clear"
          onClick={clearSignature}
          disabled={disabled || !hasSignature}
        >
          Clear
        </button>
      </div>
    </div>
  )
}

export default SignaturePad
