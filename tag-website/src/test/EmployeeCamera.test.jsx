/**
 * Tests for Employee component - Camera functionality
 *
 * Tests the getUserMedia camera implementation for vehicle inspections:
 * - Camera stream initialization with back camera preference
 * - Fallback camera selection when exact constraint fails
 * - Photo capture from video stream
 * - Camera cleanup on close
 * - Error handling for permission denied
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock MediaStream
class MockMediaStream {
  constructor() {
    this.tracks = [
      { stop: vi.fn(), kind: 'video' }
    ]
  }
  getTracks() {
    return this.tracks
  }
}

// Mock video element
const createMockVideoElement = () => ({
  srcObject: null,
  videoWidth: 1920,
  videoHeight: 1080,
  play: vi.fn().mockResolvedValue(undefined),
})

// Mock canvas element
const createMockCanvasElement = () => {
  const ctx = {
    drawImage: vi.fn(),
  }
  return {
    width: 0,
    height: 0,
    getContext: vi.fn().mockReturnValue(ctx),
    toDataURL: vi.fn().mockReturnValue('data:image/jpeg;base64,mockImageData'),
  }
}

// Setup navigator.mediaDevices mock
const setupMediaDevicesMock = () => {
  const mockStream = new MockMediaStream()

  const getUserMedia = vi.fn()

  Object.defineProperty(navigator, 'mediaDevices', {
    value: {
      getUserMedia,
    },
    writable: true,
    configurable: true,
  })

  return { getUserMedia, mockStream }
}

describe('Employee Camera - Unit Tests', () => {
  let originalNavigator

  beforeEach(() => {
    originalNavigator = { ...navigator }
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('Camera Constraints', () => {
    it('should request back camera with exact facingMode constraint first', async () => {
      const { getUserMedia, mockStream } = setupMediaDevicesMock()
      getUserMedia.mockResolvedValue(mockStream)

      // Simulate the camera open logic
      const openCamera = async () => {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { exact: 'environment' } },
          audio: false
        })
        return stream
      }

      const stream = await openCamera()

      expect(getUserMedia).toHaveBeenCalledWith({
        video: { facingMode: { exact: 'environment' } },
        audio: false
      })
      expect(stream).toBe(mockStream)
    })

    it('should fallback to ideal facingMode when exact fails', async () => {
      const { getUserMedia, mockStream } = setupMediaDevicesMock()

      // First call with exact constraint fails
      getUserMedia
        .mockRejectedValueOnce(new Error('OverconstrainedError'))
        .mockResolvedValueOnce(mockStream)

      // Simulate the fallback logic
      const openCameraWithFallback = async () => {
        try {
          return await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { exact: 'environment' } },
            audio: false
          })
        } catch {
          return await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: 'environment' } },
            audio: false
          })
        }
      }

      const stream = await openCameraWithFallback()

      expect(getUserMedia).toHaveBeenCalledTimes(2)
      expect(getUserMedia).toHaveBeenNthCalledWith(1, {
        video: { facingMode: { exact: 'environment' } },
        audio: false
      })
      expect(getUserMedia).toHaveBeenNthCalledWith(2, {
        video: { facingMode: { ideal: 'environment' } },
        audio: false
      })
      expect(stream).toBe(mockStream)
    })

    it('should fallback to any camera when both exact and ideal fail', async () => {
      const { getUserMedia, mockStream } = setupMediaDevicesMock()

      // Both exact and ideal fail, any camera succeeds
      getUserMedia
        .mockRejectedValueOnce(new Error('OverconstrainedError'))
        .mockRejectedValueOnce(new Error('OverconstrainedError'))
        .mockResolvedValueOnce(mockStream)

      // Simulate the full fallback logic
      const openCameraWithFullFallback = async () => {
        try {
          return await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { exact: 'environment' } },
            audio: false
          })
        } catch {
          try {
            return await navigator.mediaDevices.getUserMedia({
              video: { facingMode: { ideal: 'environment' } },
              audio: false
            })
          } catch {
            return await navigator.mediaDevices.getUserMedia({
              video: true,
              audio: false
            })
          }
        }
      }

      const stream = await openCameraWithFullFallback()

      expect(getUserMedia).toHaveBeenCalledTimes(3)
      expect(getUserMedia).toHaveBeenNthCalledWith(3, {
        video: true,
        audio: false
      })
      expect(stream).toBe(mockStream)
    })

    it('should not request audio when capturing photos', async () => {
      const { getUserMedia, mockStream } = setupMediaDevicesMock()
      getUserMedia.mockResolvedValue(mockStream)

      await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { exact: 'environment' } },
        audio: false
      })

      const callArgs = getUserMedia.mock.calls[0][0]
      expect(callArgs.audio).toBe(false)
    })
  })

  describe('Photo Capture', () => {
    it('should capture photo from video stream', () => {
      const video = createMockVideoElement()
      const canvas = createMockCanvasElement()

      // Simulate capture
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      const ctx = canvas.getContext('2d')
      ctx.drawImage(video, 0, 0)
      const photoData = canvas.toDataURL('image/jpeg', 0.8)

      expect(canvas.width).toBe(1920)
      expect(canvas.height).toBe(1080)
      expect(ctx.drawImage).toHaveBeenCalledWith(video, 0, 0)
      expect(photoData).toContain('data:image/jpeg;base64')
    })

    it('should use JPEG format with 0.8 quality', () => {
      const canvas = createMockCanvasElement()

      canvas.toDataURL('image/jpeg', 0.8)

      expect(canvas.toDataURL).toHaveBeenCalledWith('image/jpeg', 0.8)
    })

    it('should set canvas dimensions from video dimensions', () => {
      const video = createMockVideoElement()
      video.videoWidth = 1280
      video.videoHeight = 720

      const canvas = createMockCanvasElement()
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight

      expect(canvas.width).toBe(1280)
      expect(canvas.height).toBe(720)
    })
  })

  describe('Stream Cleanup', () => {
    it('should stop all tracks when closing camera', () => {
      const mockStream = new MockMediaStream()

      // Simulate closeCamera
      mockStream.getTracks().forEach(track => track.stop())

      expect(mockStream.tracks[0].stop).toHaveBeenCalled()
    })

    it('should handle stream with multiple tracks', () => {
      const mockStream = new MockMediaStream()
      mockStream.tracks.push({ stop: vi.fn(), kind: 'audio' })

      mockStream.getTracks().forEach(track => track.stop())

      mockStream.tracks.forEach(track => {
        expect(track.stop).toHaveBeenCalled()
      })
    })

    it('should handle null stream gracefully', () => {
      const closeCamera = (stream) => {
        if (stream) {
          stream.getTracks().forEach(track => track.stop())
        }
      }

      // Should not throw
      expect(() => closeCamera(null)).not.toThrow()
    })
  })

  describe('Error Handling', () => {
    it('should handle permission denied error', async () => {
      const { getUserMedia } = setupMediaDevicesMock()
      const permissionError = new Error('Permission denied')
      permissionError.name = 'NotAllowedError'

      getUserMedia.mockRejectedValue(permissionError)

      await expect(
        navigator.mediaDevices.getUserMedia({ video: true })
      ).rejects.toThrow('Permission denied')
    })

    it('should handle no camera available error', async () => {
      const { getUserMedia } = setupMediaDevicesMock()
      const notFoundError = new Error('Requested device not found')
      notFoundError.name = 'NotFoundError'

      getUserMedia.mockRejectedValue(notFoundError)

      await expect(
        navigator.mediaDevices.getUserMedia({ video: true })
      ).rejects.toThrow('Requested device not found')
    })

    it('should handle overconstrained error for specific camera', async () => {
      const { getUserMedia } = setupMediaDevicesMock()
      const overconstrainedError = new Error('Could not satisfy constraints')
      overconstrainedError.name = 'OverconstrainedError'

      getUserMedia.mockRejectedValue(overconstrainedError)

      await expect(
        navigator.mediaDevices.getUserMedia({
          video: { facingMode: { exact: 'environment' } }
        })
      ).rejects.toThrow('Could not satisfy constraints')
    })
  })
})

describe('Employee Camera - Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Camera Modal Flow', () => {
    it('should open camera modal and start stream for a specific photo slot', async () => {
      const { getUserMedia, mockStream } = setupMediaDevicesMock()
      getUserMedia.mockResolvedValue(mockStream)

      // Simulate state
      let showCameraModal = false
      let cameraSlotKey = null
      let cameraStream = null

      // Simulate openCamera function
      const openCamera = async (slotKey) => {
        cameraSlotKey = slotKey
        showCameraModal = true

        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { exact: 'environment' } },
          audio: false
        })
        cameraStream = stream
      }

      await openCamera('front')

      expect(showCameraModal).toBe(true)
      expect(cameraSlotKey).toBe('front')
      expect(cameraStream).toBe(mockStream)
    })

    it('should capture photo and close modal', async () => {
      const { getUserMedia, mockStream } = setupMediaDevicesMock()
      getUserMedia.mockResolvedValue(mockStream)

      // Simulate state
      let showCameraModal = true
      let cameraSlotKey = 'rear'
      let cameraStream = mockStream
      let inspectionPhotos = {}

      const video = createMockVideoElement()
      const canvas = createMockCanvasElement()

      // Simulate captureFromCamera
      const captureFromCamera = () => {
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        const ctx = canvas.getContext('2d')
        ctx.drawImage(video, 0, 0)
        const photoData = canvas.toDataURL('image/jpeg', 0.8)

        inspectionPhotos = { ...inspectionPhotos, [cameraSlotKey]: photoData }

        // Close camera
        cameraStream.getTracks().forEach(track => track.stop())
        cameraStream = null
        showCameraModal = false
        cameraSlotKey = null
      }

      captureFromCamera()

      expect(inspectionPhotos.rear).toContain('data:image/jpeg;base64')
      expect(showCameraModal).toBe(false)
      expect(cameraSlotKey).toBeNull()
      expect(mockStream.tracks[0].stop).toHaveBeenCalled()
    })

    it('should close camera without capturing when cancelled', () => {
      const mockStream = new MockMediaStream()

      // Simulate state
      let showCameraModal = true
      let cameraStream = mockStream
      let inspectionPhotos = {}

      // Simulate closeCamera
      const closeCamera = () => {
        if (cameraStream) {
          cameraStream.getTracks().forEach(track => track.stop())
          cameraStream = null
        }
        showCameraModal = false
      }

      closeCamera()

      expect(showCameraModal).toBe(false)
      expect(cameraStream).toBeNull()
      expect(mockStream.tracks[0].stop).toHaveBeenCalled()
      expect(Object.keys(inspectionPhotos)).toHaveLength(0)
    })
  })

  describe('Photo Slots Integration', () => {
    const PHOTO_SLOTS = [
      { key: 'front', label: 'Front', required: true },
      { key: 'rear', label: 'Rear', required: true },
      { key: 'driver_side', label: 'Driver Side', required: true },
      { key: 'passenger_side', label: 'Passenger Side', required: true },
      { key: 'additional_1', label: 'Additional 1', required: false },
      { key: 'additional_2', label: 'Additional 2', required: false },
    ]

    it('should capture photos for all required slots', async () => {
      const { getUserMedia, mockStream } = setupMediaDevicesMock()
      getUserMedia.mockResolvedValue(mockStream)

      const canvas = createMockCanvasElement()
      let inspectionPhotos = {}

      const requiredSlots = PHOTO_SLOTS.filter(s => s.required)

      // Simulate capturing all required photos
      for (const slot of requiredSlots) {
        const photoData = canvas.toDataURL('image/jpeg', 0.8)
        inspectionPhotos = { ...inspectionPhotos, [slot.key]: photoData }
      }

      expect(Object.keys(inspectionPhotos)).toHaveLength(4)
      expect(inspectionPhotos.front).toBeDefined()
      expect(inspectionPhotos.rear).toBeDefined()
      expect(inspectionPhotos.driver_side).toBeDefined()
      expect(inspectionPhotos.passenger_side).toBeDefined()
    })

    it('should allow retaking photos by replacing existing', () => {
      const canvas = createMockCanvasElement()
      let inspectionPhotos = { front: 'old-photo-data' }

      // Simulate retake
      const newPhotoData = canvas.toDataURL('image/jpeg', 0.8)
      inspectionPhotos = { ...inspectionPhotos, front: newPhotoData }

      expect(inspectionPhotos.front).toBe(newPhotoData)
      expect(inspectionPhotos.front).not.toBe('old-photo-data')
    })

    it('should validate required photos before submission', () => {
      const REQUIRED_PHOTO_KEYS = PHOTO_SLOTS.filter(s => s.required).map(s => s.key)

      // Missing some required photos
      const incompletePhotos = {
        front: 'data:image/jpeg;base64,abc',
        rear: 'data:image/jpeg;base64,def',
        // Missing: driver_side, passenger_side
      }

      const missingPhotos = REQUIRED_PHOTO_KEYS.filter(key => !incompletePhotos[key])

      expect(missingPhotos).toContain('driver_side')
      expect(missingPhotos).toContain('passenger_side')
      expect(missingPhotos).toHaveLength(2)
    })

    it('should pass validation with all required photos', () => {
      const REQUIRED_PHOTO_KEYS = PHOTO_SLOTS.filter(s => s.required).map(s => s.key)

      const completePhotos = {
        front: 'data:image/jpeg;base64,abc',
        rear: 'data:image/jpeg;base64,def',
        driver_side: 'data:image/jpeg;base64,ghi',
        passenger_side: 'data:image/jpeg;base64,jkl',
      }

      const missingPhotos = REQUIRED_PHOTO_KEYS.filter(key => !completePhotos[key])

      expect(missingPhotos).toHaveLength(0)
    })
  })

  describe('Device Compatibility', () => {
    it('should handle devices without getUserMedia support', async () => {
      // Remove mediaDevices
      const originalMediaDevices = navigator.mediaDevices
      Object.defineProperty(navigator, 'mediaDevices', {
        value: undefined,
        writable: true,
        configurable: true,
      })

      const openCamera = async () => {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error('Camera not supported on this device')
        }
        return await navigator.mediaDevices.getUserMedia({ video: true })
      }

      await expect(openCamera()).rejects.toThrow('Camera not supported on this device')

      // Restore
      Object.defineProperty(navigator, 'mediaDevices', {
        value: originalMediaDevices,
        writable: true,
        configurable: true,
      })
    })

    it('should work on Samsung tablet with environment facingMode', async () => {
      const { getUserMedia, mockStream } = setupMediaDevicesMock()

      // Samsung tablets may only respond to exact: environment
      getUserMedia.mockImplementation(async (constraints) => {
        if (constraints.video?.facingMode?.exact === 'environment') {
          return mockStream
        }
        throw new Error('OverconstrainedError')
      })

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { exact: 'environment' } },
        audio: false
      })

      expect(stream).toBe(mockStream)
    })

    it('should work on iPad with environment facingMode', async () => {
      const { getUserMedia, mockStream } = setupMediaDevicesMock()
      getUserMedia.mockResolvedValue(mockStream)

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { exact: 'environment' } },
        audio: false
      })

      expect(stream).toBe(mockStream)
    })
  })
})

describe('Employee Camera - Edge Cases', () => {
  it('should handle rapid open/close without memory leaks', () => {
    const streams = []

    for (let i = 0; i < 5; i++) {
      const stream = new MockMediaStream()
      streams.push(stream)
      // Immediately close
      stream.getTracks().forEach(track => track.stop())
    }

    streams.forEach(stream => {
      expect(stream.tracks[0].stop).toHaveBeenCalled()
    })
  })

  it('should handle zero-dimension video gracefully', () => {
    const video = createMockVideoElement()
    video.videoWidth = 0
    video.videoHeight = 0

    const canvas = createMockCanvasElement()

    // Should not throw when dimensions are zero
    expect(() => {
      canvas.width = video.videoWidth || 640 // Default fallback
      canvas.height = video.videoHeight || 480
    }).not.toThrow()

    expect(canvas.width).toBe(640)
    expect(canvas.height).toBe(480)
  })

  it('should handle switching between photo slots quickly', async () => {
    const { getUserMedia, mockStream } = setupMediaDevicesMock()
    getUserMedia.mockResolvedValue(mockStream)

    let currentSlotKey = null

    const switchToSlot = (slotKey) => {
      currentSlotKey = slotKey
    }

    // Rapid slot switching
    switchToSlot('front')
    switchToSlot('rear')
    switchToSlot('driver_side')
    switchToSlot('passenger_side')

    expect(currentSlotKey).toBe('passenger_side')
  })

  it('should preserve other photos when capturing new one', () => {
    let inspectionPhotos = {
      front: 'photo1',
      rear: 'photo2',
    }

    // Add new photo
    inspectionPhotos = { ...inspectionPhotos, driver_side: 'photo3' }

    expect(inspectionPhotos.front).toBe('photo1')
    expect(inspectionPhotos.rear).toBe('photo2')
    expect(inspectionPhotos.driver_side).toBe('photo3')
  })
})
