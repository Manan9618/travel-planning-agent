import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { PdfPreview } from './PdfPreview'

const { fetchPdfBlobUrl } = vi.hoisted(() => ({ fetchPdfBlobUrl: vi.fn() }))
vi.mock('@/lib/api', () => ({ fetchPdfBlobUrl }))

describe('PdfPreview', () => {
  it('shows a message when no PDF is available, without fetching', () => {
    render(<PdfPreview sessionId="s1" available={false} />)
    expect(screen.getByText(/not generated/)).toBeInTheDocument()
    expect(fetchPdfBlobUrl).not.toHaveBeenCalled()
  })

  it('shows a loading state then the iframe once the blob URL resolves', async () => {
    fetchPdfBlobUrl.mockResolvedValueOnce('blob:mock-url')
    render(<PdfPreview sessionId="s1" available={true} />)
    expect(screen.getByText(/Loading PDF/)).toBeInTheDocument()

    await waitFor(() => expect(screen.getByTitle('Itinerary PDF preview')).toBeInTheDocument())
    expect(screen.getByTitle('Itinerary PDF preview')).toHaveAttribute('src', 'blob:mock-url')
  })

  it('shows an error message when the fetch fails', async () => {
    fetchPdfBlobUrl.mockRejectedValueOnce(new Error('404 Not Found'))
    render(<PdfPreview sessionId="s1" available={true} />)
    await waitFor(() => expect(screen.getByText(/404 Not Found/)).toBeInTheDocument())
  })
})
