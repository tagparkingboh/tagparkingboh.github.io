/**
 * Render tests for the admin inspection photo viewer (Actions tab).
 *
 * Covers the expand + rotate + zoom controls added to the
 * View Drop-off / View Return Inspection modals in AdminModals.jsx:
 *  - per-photo Rotate + Expand buttons
 *  - Expand opens the fullscreen viewer with zoom/rotate controls
 *  - zoom in scales the image, zoom out clamps back to 1x
 *  - rotate cycles the expanded image by 90deg
 *  - close removes the viewer
 */
import { describe, it, expect, afterEach } from 'vitest'
import { render, fireEvent, cleanup } from '@testing-library/react'
import AdminModals from '../components/admin/AdminModals'

const inspection = {
  customer_name: 'John Doe',
  signed_date: '2026-03-15',
  mileage: 45000,
  notes: 'ok',
  vehicle_inspection_read: true,
  created_at: '2026-03-15T09:45:00Z',
  photos: {
    front: 'data:image/png;base64,FRONT',
    rear: 'data:image/png;base64,REAR',
  },
  signature: null,
}

function renderModals() {
  return render(
    <AdminModals
      showDropoffInspectionModal={true}
      closeDropoffInspectionModal={() => {}}
      bookingForDropoffInspection={{ id: 1, reference: 'TAG-1' }}
      loadingDropoffInspection={false}
      dropoffInspectionData={inspection}
      formatDateTimeUK={(d) => String(d)}
    />
  )
}

describe('Admin inspection photo viewer — expand / rotate / zoom', () => {
  afterEach(cleanup)

  it('renders Expand + Rotate controls on each photo', () => {
    const { getAllByText } = renderModals()
    expect(getAllByText(/Expand/).length).toBe(2) // front + rear
    expect(getAllByText(/Rotate/).length).toBe(2)
  })

  it('Expand opens the fullscreen viewer with the photo + zoom/rotate controls', () => {
    const { getAllByText, container } = renderModals()
    expect(container.querySelector('.image-viewer-overlay')).toBeNull()

    fireEvent.click(getAllByText(/Expand/)[0])

    expect(container.querySelector('.image-viewer-overlay')).not.toBeNull()
    const img = container.querySelector('.image-viewer-img')
    expect(img).not.toBeNull()
    expect(img.getAttribute('src')).toBe('data:image/png;base64,FRONT')
    expect(container.querySelector('.image-viewer-controls')).not.toBeNull()
    expect(container.querySelectorAll('.image-viewer-btn').length).toBe(3) // − + ↻
  })

  it('zoom in scales the image; zoom out clamps back to 1x', () => {
    const { getAllByText, container } = renderModals()
    fireEvent.click(getAllByText(/Expand/)[0])
    const img = () => container.querySelector('.image-viewer-img')
    const [zoomOut, zoomIn] = container.querySelectorAll('.image-viewer-btn')

    expect(img().style.transform).toContain('scale(1)')
    fireEvent.click(zoomIn)
    expect(img().style.transform).toContain('scale(1.5)')
    fireEvent.click(zoomIn)
    expect(img().style.transform).toContain('scale(2)')
    // three zoom-outs from 2x must clamp at 1x, never below
    fireEvent.click(zoomOut)
    fireEvent.click(zoomOut)
    fireEvent.click(zoomOut)
    expect(img().style.transform).toContain('scale(1)')
  })

  it('rotate cycles the expanded image by 90deg', () => {
    const { getAllByText, container } = renderModals()
    fireEvent.click(getAllByText(/Expand/)[0])
    const img = () => container.querySelector('.image-viewer-img')
    const rotateBtn = container.querySelectorAll('.image-viewer-btn')[2]

    expect(img().style.transform).toContain('rotate(0deg)')
    fireEvent.click(rotateBtn)
    expect(img().style.transform).toContain('rotate(90deg)')
    fireEvent.click(rotateBtn)
    expect(img().style.transform).toContain('rotate(180deg)')
  })

  it('close button removes the viewer', () => {
    const { getAllByText, container } = renderModals()
    fireEvent.click(getAllByText(/Expand/)[0])
    expect(container.querySelector('.image-viewer-overlay')).not.toBeNull()
    fireEvent.click(container.querySelector('.image-viewer-close'))
    expect(container.querySelector('.image-viewer-overlay')).toBeNull()
  })
})
