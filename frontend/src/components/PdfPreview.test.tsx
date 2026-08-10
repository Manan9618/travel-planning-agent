import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { PdfPreview } from './PdfPreview'

describe('PdfPreview', () => {
  it('shows a message when no PDF is available, without fetching', () => {
    const fetchUrl = vi.fn()
    render(<PdfPreview cacheKey="s1" fetchUrl={fetchUrl} available={false} />)
    expect(screen.getByText(/not generated/)).toBeInTheDocument()
    expect(fetchUrl).not.toHaveBeenCalled()
  })

  it('shows a loading state then the iframe once the blob URL resolves', async () => {
    const fetchUrl = vi.fn().mockResolvedValueOnce('blob:mock-url')
    render(<PdfPreview cacheKey="s1" fetchUrl={fetchUrl} available={true} />)
    expect(screen.getByText(/Loading PDF/)).toBeInTheDocument()

    await waitFor(() => expect(screen.getByTitle('Itinerary PDF preview')).toBeInTheDocument())
    expect(screen.getByTitle('Itinerary PDF preview')).toHaveAttribute('src', 'blob:mock-url')
  })

  it('shows an error message when the fetch fails', async () => {
    const fetchUrl = vi.fn().mockRejectedValueOnce(new Error('404 Not Found'))
    render(<PdfPreview cacheKey="s1" fetchUrl={fetchUrl} available={true} />)
    await waitFor(() => expect(screen.getByText(/404 Not Found/)).toBeInTheDocument())
  })

  it('refetches when cacheKey changes even though available stays true', async () => {
    const fetchUrl = vi.fn().mockResolvedValueOnce('blob:first').mockResolvedValueOnce('blob:second')
    const { rerender } = render(<PdfPreview cacheKey="s1" fetchUrl={fetchUrl} available={true} />)
    await waitFor(() => expect(screen.getByTitle('Itinerary PDF preview')).toHaveAttribute(
      'src',
      'blob:first',
    ))

    rerender(<PdfPreview cacheKey="s2" fetchUrl={fetchUrl} available={true} />)
    await waitFor(() => expect(screen.getByTitle('Itinerary PDF preview')).toHaveAttribute(
      'src',
      'blob:second',
    ))
    expect(fetchUrl).toHaveBeenCalledTimes(2)
  })

  it('does not refetch on a re-render with a new fetchUrl closure but the same cacheKey', async () => {
    const fetchUrl1 = vi.fn().mockResolvedValueOnce('blob:mock-url')
    const { rerender } = render(<PdfPreview cacheKey="s1" fetchUrl={fetchUrl1} available={true} />)
    await waitFor(() => expect(screen.getByTitle('Itinerary PDF preview')).toBeInTheDocument())

    const fetchUrl2 = vi.fn()
    rerender(<PdfPreview cacheKey="s1" fetchUrl={fetchUrl2} available={true} />)
    expect(fetchUrl2).not.toHaveBeenCalled()
  })
})
